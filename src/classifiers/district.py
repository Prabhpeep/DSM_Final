"""
Gazetteer-based district classifier for Assam OCDS tenders (FY 2020-23).

Pipeline:
  1. Load gazetteer from src/classifiers/assam_gazetteer.yaml.
  2. Load tenders (bid_opening_address, tender_title) from db/dsm.sqlite.
  3. Load procuringEntity_name from staging_main via ocid join.
  4. Multi-pass classification for Procuring District:
     Pass 1: Exact substring match in bid_opening_address.
     Pass 2: Exact substring match in tender_procuringEntity_name.
     Pass 3: State-HQ fallback (addresses mentioning state-level org
              keywords like "Assam", "NHM", "PWRD" → Kamrup Metropolitan).
     Pass 4: BTC fallback (addresses mentioning BTC/Bodoland → Kokrajhar).
     [Optional via --include-cosmetic-passes] Pass 5: PWD circle-abbrev match.
     [Optional via --include-cosmetic-passes] Pass 6: rapidfuzz on address.
     [Optional via --include-cosmetic-passes] Pass 7: rapidfuzz on entity.
     Unmatched -> "Unclassified".
  5. Exact match classification for Execution District on tender_title.
  6. Write dim_district_derived, update fact_tenders (district_procuring_id,
     district_execution_id), create v_district_best view.
  7. Write CSV + print eyeball report.

Run from project root: `python3 src/classifiers/district.py`
"""
from __future__ import annotations

import argparse
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
    if not text:
        return None, None

    best_name: str | None = None
    best_alias: str | None = None
    best_len = 0

    for dist in districts:
        for alias, pat in dist.patterns:
            if len(alias) <= best_len:
                continue
            if pat.search(text):
                best_name = dist.name
                best_alias = alias
                best_len = len(alias)

    return best_name, best_alias


def _circle_match(text: str, gaz: Gazetteer) -> str | None:
    if not text:
        return None
    for abbrev, (district_name, pat) in gaz._circle_pats.items():
        if pat.search(text):
            return district_name
    return None


def _btc_fallback(text: str, gaz: Gazetteer) -> bool:
    if not text:
        return False
    return any(pat.search(text) for pat in gaz._btc_pats)


def _state_hq_fallback(text: str, gaz: Gazetteer) -> bool:
    if not text:
        return False
    return any(pat.search(text) for pat in gaz._state_hq_pats)


def _fuzzy_match(text: str, districts: list[District],
                 threshold: int = FUZZY_THRESHOLD) -> tuple[str | None, int]:
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
             gaz: Gazetteer,
             include_cosmetic: bool = False) -> tuple[str, str]:
    """
    Multi-pass classification for Procuring District.
    """
    districts = gaz.districts

    name, _ = _exact_substring_match(address, districts)
    if name: return name, "address"

    name, _ = _exact_substring_match(entity_name, districts)
    if name: return name, "entity_name"

    if _state_hq_fallback(address, gaz) or _state_hq_fallback(entity_name, gaz):
        return "Kamrup Metropolitan", "state_hq"

    if _btc_fallback(address, gaz) or _btc_fallback(entity_name, gaz):
        return "Kokrajhar", "btc_fallback"

    if include_cosmetic:
        name = _circle_match(address, gaz) or _circle_match(entity_name, gaz)
        if name: return name, "circle"

        name, score = _fuzzy_match(address, districts)
        if name: return name, "fuzzy_address"

        name, score = _fuzzy_match(entity_name, districts)
        if name: return name, "fuzzy_entity"

    return "Unclassified", "unclassified"


def classify_execution(title: str | None, gaz: Gazetteer) -> str | None:
    """
    Find the execution district from the tender_title using exact substring
    matching only (no fallbacks).
    """
    if not title:
        return None
    name, _ = _exact_substring_match(title, gaz.districts)
    return name


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #
def load_tenders() -> list[tuple[str, str | None, str | None, str | None]]:
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


def write_csv(labels: list[tuple[str, str, str, str | None]]) -> None:
    LABELS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with LABELS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ocid", "district_procuring", "matched_via", "district_execution"])
        w.writerows(labels)
    print(f"Wrote {LABELS_CSV} ({len(labels):,} rows).")


def update_db(labels: list[tuple[str, str, str, str | None]],
              gaz: Gazetteer) -> None:
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

    # ---- Ensure district_procuring_id and district_execution_id exist ----
    cols = {row[1] for row in cur.execute("PRAGMA table_info(fact_tenders)")}
    
    # We might have an old district_id column to handle or rename
    if "district_id" in cols and "district_procuring_id" not in cols:
        try:
            cur.execute("ALTER TABLE fact_tenders RENAME COLUMN district_id TO district_procuring_id")
            cols.add("district_procuring_id")
        except sqlite3.OperationalError:
            pass
            
    if "district_procuring_id" not in cols:
        cur.execute("""
            ALTER TABLE fact_tenders
            ADD COLUMN district_procuring_id INTEGER REFERENCES dim_district_derived(district_id)
        """)
        try:
            cur.execute("CREATE INDEX idx_ft_district_procuring ON fact_tenders(district_procuring_id)")
        except sqlite3.OperationalError:
            pass

    if "district_execution_id" not in cols:
        cur.execute("""
            ALTER TABLE fact_tenders
            ADD COLUMN district_execution_id INTEGER REFERENCES dim_district_derived(district_id)
        """)
        try:
            cur.execute("CREATE INDEX idx_ft_district_execution ON fact_tenders(district_execution_id)")
        except sqlite3.OperationalError:
            pass

    # ---- UPDATE fact_tenders ----
    payload = []
    for ocid, d_proc, _, d_exec in labels:
        proc_id = name_to_id[d_proc]
        exec_id = name_to_id[d_exec] if d_exec else None
        payload.append((proc_id, exec_id, ocid))

    cur.executemany(
        "UPDATE fact_tenders SET district_procuring_id = ?, district_execution_id = ? WHERE ocid = ?", payload
    )
    
    # ---- CREATE VIEW v_district_best ----
    cur.execute("DROP VIEW IF EXISTS v_district_best")
    cur.execute("""
        CREATE VIEW v_district_best AS
        SELECT 
            ocid,
            COALESCE(district_execution_id, district_procuring_id) AS district_best_id,
            CASE 
                WHEN district_execution_id IS NOT NULL THEN 'execution' 
                ELSE 'procuring_fallback' 
            END AS district_best_source
        FROM fact_tenders
    """)
    
    conn.commit()
    updated = cur.rowcount
    print(f"Created dim_district_derived ({len(dim_rows)} rows).")
    print(f"Updated {updated:,} rows in fact_tenders (procuring & execution ids).")
    print("Created view v_district_best.")
    conn.close()


# --------------------------------------------------------------------------- #
# Eyeball report
# --------------------------------------------------------------------------- #
def eyeball(rows: list[tuple[str, str | None, str | None, str | None]],
            labels: list[tuple[str, str, str, str | None]]) -> None:
    rng = random.Random(RANDOM_SEED)
    total = len(labels)

    by_district = Counter(dname for _, dname, _, _ in labels)
    by_method = Counter(method for _, _, method, _ in labels)

    print("\n" + "=" * 72)
    print("PROCURING DISTRICT DISTRIBUTION")
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
    print(f"\n  Unmatched procuring rate: {unmatched:,} / {total:,} = "
          f"{100*unmatched/total:.1f}%")

    mismatch_count = sum(1 for _, d_proc, _, d_exec in labels 
                         if d_exec is not None and d_exec != d_proc and d_proc != "Unclassified")
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
        for ocid, d_proc, method, d_exec in sample:
            addr, ent, title = by_ocid.get(ocid, ("?", "?", "?"))
            is_mismatch = d_exec is not None and d_exec != d_proc and d_proc != "Unclassified"
            print(f"  - {ocid}  [{method}]"
                  f"{'  ⚠MISMATCH→' + (d_exec or '') if is_mismatch else ''}")
            print(f"      addr: {(addr or '')[:90]}")
            print(f"      ent:  {(ent or '')[:70]}")
            print(f"      exec: {d_exec or 'None'}")

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

    mismatch_samples = [l for l in labels 
                        if l[3] is not None and l[3] != l[1] and l[1] != "Unclassified"]
    if mismatch_samples:
        print("\n" + "=" * 72)
        print(f"10 RANDOM TITLE-DISTRICT MISMATCHES (of {len(mismatch_samples):,})")
        print("=" * 72)
        sample = rng.sample(mismatch_samples,
                            min(10, len(mismatch_samples)))
        for ocid, d_proc, method, d_exec in sample:
            addr, ent, title = by_ocid.get(ocid, ("?", "?", "?"))
            print(f"  procuring→{d_proc}  execution→{d_exec}")
            print(f"    addr:  {(addr or '')[:80]}")
            print(f"    title: {(title or '')[:140]}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="District classifier")
    parser.add_argument("--include-cosmetic-passes", action="store_true",
                        help="Include slow/low-yield fuzzy and circle mapping passes")
    args = parser.parse_args()

    gaz = load_gazetteer()
    print(f"Loaded gazetteer: {len(gaz.districts)} districts, "
          f"{sum(len(d.aliases) for d in gaz.districts)} total aliases, "
          f"{len(gaz.state_hq_keywords)} state-HQ keywords, "
          f"{len(gaz.btc_keywords)} BTC keywords, "
          f"{len(gaz.circle_map)} circle abbreviations.")

    rows = load_tenders()

    labels: list[tuple[str, str, str, str | None]] = []
    for ocid, address, entity_name, title in rows:
        d_proc, matched_via = classify(address, entity_name, gaz, args.include_cosmetic_passes)
        d_exec = classify_execution(title, gaz)
        labels.append((ocid, d_proc, matched_via, d_exec))

    write_csv(labels)
    update_db(labels, gaz)
    eyeball(rows, labels)


if __name__ == "__main__":
    main()
