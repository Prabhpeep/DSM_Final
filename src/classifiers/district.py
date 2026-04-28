"""
Gazetteer-based district classifier for Assam OCDS tenders (FY 2020-23).

Pipeline:
  1. Load gazetteer from src/classifiers/assam_gazetteer.yaml.
  2. Load tenders (bid_opening_address, tender_title) from db/dsm.sqlite.
  3. Load procuringEntity_name from staging_main via ocid join.
  4. Multi-pass classification:
     Pass 1: Exact substring match in bid_opening_address.
     Pass 2: Exact substring match in tender_procuringEntity_name.
     Pass 3: PWD circle-abbreviation match in address or entity.
     Pass 4: BTC fallback (addresses mentioning BTC/Bodoland → Kokrajhar).
     Pass 5: State-HQ fallback (addresses mentioning state-level org
              keywords like "Assam", "NHM", "PWRD" → Kamrup Metropolitan).
     Pass 6: rapidfuzz partial_ratio on address (threshold >= 90).
     Pass 7: rapidfuzz partial_ratio on entity_name (threshold >= 90).
     Unmatched -> "Unclassified".
  5. Title-district mismatch detection: flag tenders where the title
     mentions a different district than the one assigned by address.
  6. Write dim_district_derived + update fact_tenders.district_id.
  7. Write CSV + print eyeball report.

Run from project root: `python3 src/classifiers/district.py`.
"""
from __future__ import annotations

import csv
import random
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import yaml
from rapidfuzz import fuzz

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
DB_PATH        = Path("db/dsm.sqlite")
GAZETTEER_PATH = Path("src/classifiers/assam_gazetteer.yaml")
LABELS_CSV     = Path("src/classifiers/district_labels.csv")
FY_INCLUDE     = {"2020-2021", "2021-2022", "2022-2023"}
RANDOM_SEED    = 42
FUZZY_THRESHOLD = 90


# --------------------------------------------------------------------------- #
# Gazetteer loading
# --------------------------------------------------------------------------- #
class District:
    """One Census district with aliases for matching."""
    __slots__ = ("name", "census_code", "aliases", "patterns")

    def __init__(self, name: str, census_code: str, aliases: list[str]):
        self.name = name
        self.census_code = census_code
        self.aliases = sorted(aliases, key=len, reverse=True)  # longest first
        # Word-boundary regex for each alias
        self.patterns: list[tuple[str, re.Pattern]] = []
        for alias in self.aliases:
            esc = re.escape(alias)
            if alias[0].isalnum():
                esc = r"\b" + esc
            if alias[-1].isalnum():
                esc = esc + r"\b"
            self.patterns.append((alias, re.compile(esc, re.IGNORECASE)))


class Gazetteer:
    """Complete gazetteer including districts + fallback rules."""
    __slots__ = ("districts", "state_hq_keywords", "btc_keywords",
                 "circle_map", "_state_hq_pats", "_btc_pats",
                 "_circle_pats")

    def __init__(self, districts: list[District],
                 state_hq_keywords: list[str],
                 btc_keywords: list[str],
                 circle_map: dict[str, str]):
        self.districts = districts
        self.state_hq_keywords = state_hq_keywords
        self.btc_keywords = btc_keywords
        self.circle_map = circle_map

        # Pre-compile fallback patterns
        self._state_hq_pats = [
            re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
            for kw in state_hq_keywords
        ]
        self._btc_pats = [
            re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
            for kw in btc_keywords
        ]
        self._circle_pats = {
            abbrev: (district_name,
                     re.compile(r"\b" + re.escape(abbrev) + r"\b",
                                re.IGNORECASE))
            for abbrev, district_name in circle_map.items()
        }


def load_gazetteer(path: Path | None = None) -> Gazetteer:
    """Parse YAML gazetteer into a Gazetteer object."""
    path = path or GAZETTEER_PATH
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    districts: list[District] = []
    for entry in data["districts"]:
        aliases = list(entry.get("aliases", []))
        if entry["name"] not in aliases:
            aliases.insert(0, entry["name"])
        districts.append(District(
            name=entry["name"],
            census_code=entry.get("census_code", ""),
            aliases=aliases,
        ))

    return Gazetteer(
        districts=districts,
        state_hq_keywords=data.get("state_hq_keywords", []),
        btc_keywords=data.get("btc_keywords", []),
        circle_map=data.get("circle_map", {}),
    )


# --------------------------------------------------------------------------- #
# Matching helpers
# --------------------------------------------------------------------------- #
def _exact_substring_match(text: str,
                           districts: list[District]
                           ) -> tuple[str | None, str | None]:
    """
    Scan text for the longest matching alias across all districts.
    Returns (district_name, matched_alias) or (None, None).
    """
    if not text:
        return None, None

    best_name: str | None = None
    best_alias: str | None = None
    best_len = 0

    for dist in districts:
        for alias, pat in dist.patterns:
            if len(alias) <= best_len:
                continue  # can't beat current best
            if pat.search(text):
                best_name = dist.name
                best_alias = alias
                best_len = len(alias)

    return best_name, best_alias


def _circle_match(text: str,
                  gaz: Gazetteer) -> str | None:
    """Check for PWD circle abbreviations in text."""
    if not text:
        return None
    for abbrev, (district_name, pat) in gaz._circle_pats.items():
        if pat.search(text):
            return district_name
    return None


def _btc_fallback(text: str, gaz: Gazetteer) -> bool:
    """Check if text mentions BTC/Bodoland (without a more specific district)."""
    if not text:
        return False
    return any(pat.search(text) for pat in gaz._btc_pats)


def _state_hq_fallback(text: str, gaz: Gazetteer) -> bool:
    """Check if text mentions state-level organization keywords."""
    if not text:
        return False
    return any(pat.search(text) for pat in gaz._state_hq_pats)


def _fuzzy_match(text: str, districts: list[District],
                 threshold: int = FUZZY_THRESHOLD) -> tuple[str | None, int]:
    """
    Use rapidfuzz partial_ratio to find best matching district.
    Only tries aliases with length >= 5 to avoid false positives.
    Returns (district_name, score) or (None, 0).
    """
    if not text:
        return None, 0

    text_lower = text.lower()
    best_name: str | None = None
    best_score = 0

    for dist in districts:
        candidates = [a for a in dist.aliases if len(a) >= 5]
        for alias in candidates:
            score = fuzz.partial_ratio(alias.lower(), text_lower)
            if score > best_score and score >= threshold:
                best_score = score
                best_name = dist.name

    return best_name, best_score


# --------------------------------------------------------------------------- #
# Main classifier
# --------------------------------------------------------------------------- #
def classify(address: str | None,
             entity_name: str | None,
             gaz: Gazetteer) -> tuple[str, str]:
    """
    Multi-pass classification. Returns (district_name, matched_via).

    matched_via values:
        address         – exact substring in bid_opening_address
        entity_name     – exact substring in procuringEntity_name
        circle          – PWD circle abbreviation match
        btc_fallback    – BTC/Bodoland keyword → Kokrajhar
        state_hq        – state-level org keyword → Kamrup Metropolitan
        fuzzy_address   – rapidfuzz on address
        fuzzy_entity    – rapidfuzz on entity name
        unclassified    – no match found
    """
    districts = gaz.districts

    # Pass 1: exact substring in address
    name, _ = _exact_substring_match(address, districts)
    if name:
        return name, "address"

    # Pass 2: exact substring in entity name
    name, _ = _exact_substring_match(entity_name, districts)
    if name:
        return name, "entity_name"

    # Pass 3: PWD circle abbreviation in address or entity
    name = _circle_match(address, gaz) or _circle_match(entity_name, gaz)
    if name:
        return name, "circle"

    # Pass 4: BTC fallback → Kokrajhar
    if _btc_fallback(address, gaz) or _btc_fallback(entity_name, gaz):
        return "Kokrajhar", "btc_fallback"

    # Pass 5: State-HQ fallback → Kamrup Metropolitan
    if _state_hq_fallback(address, gaz) or _state_hq_fallback(entity_name, gaz):
        return "Kamrup Metropolitan", "state_hq"

    # Pass 6: fuzzy match on address
    name, score = _fuzzy_match(address, districts)
    if name:
        return name, "fuzzy_address"

    # Pass 7: fuzzy match on entity name
    name, score = _fuzzy_match(entity_name, districts)
    if name:
        return name, "fuzzy_entity"

    return "Unclassified", "unclassified"


def detect_title_mismatch(title: str | None,
                          assigned_district: str,
                          districts: list[District]
                          ) -> tuple[bool, str | None]:
    """
    Check if tender_title mentions a district different from the
    address-assigned one. Returns (has_mismatch, title_district_name).
    """
    if not title or assigned_district == "Unclassified":
        return False, None

    title_district, _ = _exact_substring_match(title, districts)
    if title_district and title_district != assigned_district:
        return True, title_district

    return False, None


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #
def load_tenders() -> list[tuple[str, str | None, str | None, str | None]]:
    """
    Return list of (ocid, bid_opening_address, entity_name, tender_title).
    Joins fact_tenders with staging_main to get procuringEntity_name.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH.resolve()}")

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT ft.ocid,
               ft.bid_opening_address,
               sm.tender_procuringEntity_name,
               ft.tender_title
        FROM fact_tenders ft
        LEFT JOIN staging_main sm ON ft.ocid = sm.ocid
        WHERE ft.fiscal_year IN (?,?,?)
    """, tuple(sorted(FY_INCLUDE))).fetchall()
    conn.close()
    print(f"Loaded {len(rows):,} tenders from SQLite.")
    return rows


def write_csv(labels: list[tuple[str, str, str, bool, str | None]]) -> None:
    """Write classification results to CSV."""
    LABELS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with LABELS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ocid", "district_name", "matched_via",
                     "title_district_mismatch", "title_district_name"])
        w.writerows(labels)
    print(f"Wrote {LABELS_CSV} ({len(labels):,} rows).")


def update_db(labels: list[tuple[str, str, str, bool, str | None]],
              gaz: Gazetteer) -> None:
    """
    Create dim_district_derived (idempotent), add district_id column
    to fact_tenders if missing, and UPDATE fact_tenders.district_id.
    """
    if not DB_PATH.exists():
        print("SQLite not found; skipping DB update.", file=sys.stderr)
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ---- dim_district_derived ----
    cur.execute("DROP TABLE IF EXISTS dim_district_derived")
    cur.execute("""
        CREATE TABLE dim_district_derived (
            district_id   INTEGER PRIMARY KEY,
            district_name TEXT NOT NULL UNIQUE,
            census_code   TEXT
        )
    """)

    dim_rows: list[tuple[int, str, str | None]] = []
    for i, d in enumerate(gaz.districts, start=1):
        dim_rows.append((i, d.name, d.census_code or None))
    unclassified_id = len(gaz.districts) + 1
    dim_rows.append((unclassified_id, "Unclassified", None))

    cur.executemany(
        "INSERT INTO dim_district_derived VALUES (?, ?, ?)", dim_rows
    )

    name_to_id = {row[1]: row[0] for row in dim_rows}

    # ---- Add district_id column to fact_tenders if not present ----
    cols = {row[1] for row in cur.execute("PRAGMA table_info(fact_tenders)")}
    if "district_id" not in cols:
        cur.execute("""
            ALTER TABLE fact_tenders
            ADD COLUMN district_id INTEGER REFERENCES dim_district_derived(district_id)
        """)
        try:
            cur.execute(
                "CREATE INDEX idx_ft_district ON fact_tenders(district_id)"
            )
        except sqlite3.OperationalError:
            pass

    # ---- UPDATE fact_tenders ----
    payload = [(name_to_id[dname], ocid) for ocid, dname, _, _, _ in labels]
    cur.executemany(
        "UPDATE fact_tenders SET district_id = ? WHERE ocid = ?", payload
    )
    conn.commit()
    updated = cur.rowcount
    print(f"Created dim_district_derived ({len(dim_rows)} rows).")
    print(f"Updated {updated:,} rows in fact_tenders.district_id.")
    conn.close()


# --------------------------------------------------------------------------- #
# Eyeball report
# --------------------------------------------------------------------------- #
def eyeball(rows: list[tuple[str, str | None, str | None, str | None]],
            labels: list[tuple[str, str, str, bool, str | None]]) -> None:
    rng = random.Random(RANDOM_SEED)
    total = len(labels)

    by_district = Counter(dname for _, dname, _, _, _ in labels)
    by_method = Counter(method for _, _, method, _, _ in labels)

    print("\n" + "=" * 72)
    print("DISTRICT DISTRIBUTION")
    print("=" * 72)
    for dist, _ in sorted(by_district.items(), key=lambda x: -x[1]):
        n = by_district[dist]
        print(f"  {dist:30s} {n:6,d}  ({100*n/total:5.1f}%)")

    print("\n" + "=" * 72)
    print("CLASSIFICATION METHOD DISTRIBUTION")
    print("=" * 72)
    for m, _ in sorted(by_method.items(), key=lambda x: -x[1]):
        n = by_method[m]
        print(f"  {m:20s} {n:6,d}  ({100*n/total:5.1f}%)")

    unmatched = by_district.get("Unclassified", 0)
    print(f"\n  Unmatched rate: {unmatched:,} / {total:,} = "
          f"{100*unmatched/total:.1f}%")

    mismatch_count = sum(1 for _, _, _, mm, _ in labels if mm)
    print(f"  Title-district mismatches: {mismatch_count:,} / {total:,} = "
          f"{100*mismatch_count/total:.1f}%")

    by_ocid = {ocid: (addr, ent, title) for ocid, addr, ent, title in rows}
    by_dist_idx: dict[str, list[tuple]] = {}
    for label_row in labels:
        by_dist_idx.setdefault(label_row[1], []).append(label_row)

    print("\n" + "=" * 72)
    print("5 RANDOM SAMPLES PER DISTRICT")
    print("=" * 72)
    for dist in sorted(by_dist_idx):
        sample = rng.sample(by_dist_idx[dist],
                            min(5, len(by_dist_idx[dist])))
        print(f"\n[{dist}]  (n={len(by_dist_idx[dist])})")
        for ocid, dname, method, mm, td in sample:
            addr, ent, title = by_ocid.get(ocid, ("?", "?", "?"))
            print(f"  - {ocid}  [{method}]"
                  f"{'  ⚠MISMATCH→' + (td or '') if mm else ''}")
            print(f"      addr: {(addr or '')[:90]}")
            print(f"      ent:  {(ent or '')[:70]}")

    if unmatched:
        print("\n" + "=" * 72)
        print("TOP 20 UNMATCHED ADDRESSES (for gazetteer iteration)")
        print("=" * 72)
        unmatched_addrs: Counter = Counter()
        for label_row in labels:
            if label_row[1] == "Unclassified":
                ocid = label_row[0]
                addr = by_ocid.get(ocid, ("?",))[0]
                unmatched_addrs[addr or "NULL"] += 1
        for addr, cnt in unmatched_addrs.most_common(20):
            print(f"  {cnt:4d}  {addr[:100]}")

    mismatch_samples = [l for l in labels if l[3]]
    if mismatch_samples:
        print("\n" + "=" * 72)
        print(f"10 RANDOM TITLE-DISTRICT MISMATCHES (of {len(mismatch_samples):,})")
        print("=" * 72)
        sample = rng.sample(mismatch_samples,
                            min(10, len(mismatch_samples)))
        for ocid, dname, method, mm, td in sample:
            addr, ent, title = by_ocid.get(ocid, ("?", "?", "?"))
            print(f"  address→{dname}  title→{td}")
            print(f"    addr:  {(addr or '')[:80]}")
            print(f"    title: {(title or '')[:140]}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    gaz = load_gazetteer()
    print(f"Loaded gazetteer: {len(gaz.districts)} districts, "
          f"{sum(len(d.aliases) for d in gaz.districts)} total aliases, "
          f"{len(gaz.state_hq_keywords)} state-HQ keywords, "
          f"{len(gaz.btc_keywords)} BTC keywords, "
          f"{len(gaz.circle_map)} circle abbreviations.")

    rows = load_tenders()

    labels: list[tuple[str, str, str, bool, str | None]] = []
    for ocid, address, entity_name, title in rows:
        district_name, matched_via = classify(address, entity_name, gaz)
        has_mismatch, title_district = detect_title_mismatch(
            title, district_name, gaz.districts
        )
        labels.append((ocid, district_name, matched_via,
                        has_mismatch, title_district))

    write_csv(labels)
    update_db(labels, gaz)
    eyeball(rows, labels)


if __name__ == "__main__":
    main()
