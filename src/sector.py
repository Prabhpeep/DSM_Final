"""
Hybrid sector classifier for Assam OCDS tenders (FY 2020-23).

Pipeline:
  1. Read fact_tenders + dim_buyer from db/dsm.sqlite (fallback: Excel 'main').
  2. Apply word-boundary keyword regex per sector to tender_title; count hits.
  3. If keyword counts are decisive -> 'keyword'.
     If tied -> use BUYER_MAP to break -> 'hybrid'.
     If no keyword hits but BUYER_MAP has buyer -> 'buyer'.
     Otherwise -> 'default_other' (sector = 'other').
  4. Write src/sector_labels.csv (ocid, sector_name, classification_method).
  5. UPDATE fact_tenders.sector_id in dsm.sqlite (single transaction).
  6. Print eyeball stats: sector dist, method dist, 5 random per sector,
     10 random from 'other'.

Run from project root: `python src/sector.py`.
"""
from __future__ import annotations
import csv
import random
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

DB_PATH      = Path("db/dsm.sqlite")
EXCEL_PATH   = Path("data/raw/ocds_mapped_data_fiscal_year_2016_2022_v3.xlsx")
LABELS_CSV   = Path("src/sector_labels.csv")
FY_INCLUDE   = {"2020-2021", "2021-2022", "2022-2023"}
RANDOM_SEED  = 42

# --------------------------------------------------------------------------- #
# KEYWORD MAP — case-insensitive, word-boundary. Multi-word phrases use
# literal spaces (compiled to \s+). Tuned by eyeballing ~30 random titles
# and probing high-frequency loanwords (Ali, Path, NHM, ABHIM, PMGSY, etc.).
# --------------------------------------------------------------------------- #
KEYWORDS: dict[str, list[str]] = {
    "roads": [
        "road", "roads", "highway", "carriageway", "byelane", "bypass", "byepass",
        "blacktopping", "blacktopped", "BT road", "WBM", "metalling", "metalled",
        "PMGSY", "MMPPNA", "MMPNA", "Mukhya Mantrir Paki Path", "NH", "SH",
        "Ali", "Path", "rasta", "sadak", "approach road",
    ],
    "bridges": [
        "bridge", "RCC bridge", "footbridge", "foot bridge", "foot over bridge",
        "FOB", "pul", "culvert",
    ],
    "buildings": [
        "building", "hostel", "quarters", "staff quarter", "boundary wall",
        "auditorium", "office building", "guest house", "convention centre",
        "community hall", "cultural centre", "DC office", "Deputy Commissioner",
        "Integrated Office", "complex", "circuit house",
    ],
    "schools": [
        "school", "schools", "classroom", "college", "ITI", "university",
        "anganwadi", "AWC", "education department", "kendriya vidyalaya",
        "training centre", "knowledge centre", "training hall",
    ],
    "health": [
        "hospital", "health centre", "PHC", "CHC", "SHC", "dispensary",
        "medical", "BMW", "NHM", "ABHIM", "sub-centre", "sub centre",
        "sub-Health Centre", "sub Health Centre", "Buildingless Sub Health",
        "HWC", "AYUSH", "bedded ward", "labour room",
    ],
    "water_sanitation": [
        "water supply", "drinking water", "tubewell", "tube well", "borewell",
        "MDTW", "drain", "drains", "sewerage", "sewer", "sanitation", "toilet",
        "latrine", "PHE", "PHED", "PWS", "embankment", "dyke", "bund", "bundh",
        "irrigation", "pukhuri", "beel", "pond", "pumping station",
        "water treatment", "WTP",
    ],
    "electricity_power": [
        "electrification", "transformer", "HT line", "LT line", "sub-station",
        "substation", "electric", "electrical", "illumination", "street light",
        "feeder", "11 KV", "33 KV", "66 KV", "132 KV", "220 KV", "KV line",
        "solar", "APDCL", "AEGCL", "APGCL",
    ],
    "it_computing": [
        "computer", "software", "hardware", "server", "printer", "laptop",
        "desktop", "router", "network equipment", "network switch",
        "cyber", "IT infrastructure", "data centre", "cctv",
    ],
    "vehicles": [
        "vehicle", "vehicles", "ambulance", "car", "jeep", "truck", "bus",
        "motorcycle", "hire of vehicle", "vehicle hire", "boat", "ferry",
        "bus body",
    ],
}

# --------------------------------------------------------------------------- #
# BUYER MAP — top buyers by tender count. Covers the high-confidence
# departmental specialisations; the rest fall through to 'other'.
# --------------------------------------------------------------------------- #
BUYER_MAP: dict[str, str] = {
    # roads
    "Public Works Roads Department":                                "roads",
    "Public Works Roads Department-Externally Aided Project":       "roads",
    "Bodoland Territorial Council-PWD":                             "roads",
    # buildings
    "Public Works Building and NH Department":                      "buildings",
    "Assam Police Housing Corporation Ltd":                         "buildings",
    # health
    "National Health Mission":                                      "health",
    "Health and Family Welfare Department":                         "health",
    "ASSAM CANCER CARE FOUNDATION":                                 "health",
    # water_sanitation
    "Department of Water Resources":                                "water_sanitation",
    "Department of Water Resources-Externally Aided Project":       "water_sanitation",
    "Water Resources Department- World Bank Tenders":               "water_sanitation",
    "Bodoland Territorial Council-WRD":                             "water_sanitation",
    "Public Health Engineering Department":                         "water_sanitation",
    "Irrigation Department":                                        "water_sanitation",
    # electricity_power
    "Assam Power Distribution Company Ltd":                         "electricity_power",
    "Assam Power Distribution Company Limited- Externally Aided Project": "electricity_power",
    "Assam Electricity Grid Corporation Ltd":                       "electricity_power",
    "Assam Electricity Grid Corporation Ltd. - Externally Funded Projects": "electricity_power",
    "Assam Power Generation Company Limited":                       "electricity_power",
    "Assam Power Generation Company Limited APGCL - ADB":           "electricity_power",
    # schools
    "Axom Sarba Siksha Abhijan Mission":                            "schools",
    "Rashtriya Madhyamik Siksha Abhijan":                           "schools",
    "Elementary Education Department":                              "schools",
    "SECONDARY EDUCATION DEPARTMENT ASSAM":                         "schools",
    "Department of Higher Education":                               "schools",
    "Higher Education (Technical) Department":                      "schools",
    "Skill Employment and Entrepreneurship Department":             "schools",
    "Dibrugarh University":                                         "schools",
    "Gauhati University":                                           "schools",
    "Cotton University":                                            "schools",
    "Assam Agricultural University":                                "schools",
    "BODOLAND UNIVERSITY":                                          "schools",
    "Assam Science and Technology University":                      "schools",
    # vehicles
    "Inland Water Transport":                                       "vehicles",
    "Assam Inland Water Transport Development Society":             "vehicles",
    "Assam State Transport Corporation":                            "vehicles",
    "Transport Department":                                         "vehicles",
    "Transport Department- Externally Funded Projects":             "vehicles",
    # it_computing
    "Principal Secretary-Department of Information Technology":     "it_computing",
}
BUYER_MAP_NORM = {k.lower().strip(): v for k, v in BUYER_MAP.items()}

# --------------------------------------------------------------------------- #
# Compile patterns
# --------------------------------------------------------------------------- #
def _compile(patterns: dict[str, list[str]]) -> dict[str, list[re.Pattern]]:
    out: dict[str, list[re.Pattern]] = {}
    for sector, kws in patterns.items():
        compiled = []
        for kw in kws:
            esc = re.escape(kw).replace(r"\ ", r"\s+")
            compiled.append(re.compile(rf"\b{esc}\b", re.IGNORECASE))
        out[sector] = compiled
    return out

PATS = _compile(KEYWORDS)


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def title_counts(title: str | None) -> Counter:
    """Return Counter of {sector: total match count} from tender title."""
    c: Counter = Counter()
    if not title:
        return c
    for sector, pats in PATS.items():
        n = sum(len(p.findall(title)) for p in pats)
        if n:
            c[sector] = n
    return c


def classify(title: str | None, buyer_name: str | None) -> tuple[str, str]:
    """Return (sector_name, classification_method)."""
    counts = title_counts(title)
    buyer_sector = BUYER_MAP_NORM.get((buyer_name or "").lower().strip())

    if not counts:
        if buyer_sector:
            return buyer_sector, "buyer"
        return "other", "default_other"

    top = counts.most_common()
    if len(top) == 1 or top[0][1] > top[1][1]:
        return top[0][0], "keyword"

    # tie
    if buyer_sector:
        return buyer_sector, "hybrid"
    return "other", "default_other"


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #
def load_tenders() -> list[tuple[str, str | None, str | None]]:
    """Return list of (ocid, buyer_name, tender_title) for FY 2020-23."""
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            """
            SELECT ft.ocid, b.buyer_name, ft.tender_title
            FROM fact_tenders ft
            LEFT JOIN dim_buyer b ON ft.buyer_id = b.buyer_id
            WHERE ft.fiscal_year IN (?,?,?)
            """,
            tuple(sorted(FY_INCLUDE)),
        ).fetchall()
        conn.close()
        print(f"Loaded {len(rows):,} tenders from SQLite.")
        return rows

    print("SQLite not found; falling back to Excel.", file=sys.stderr)
    import pandas as pd
    df = pd.read_excel(EXCEL_PATH, sheet_name="main")
    df = df[df["tender_fiscalYear"].isin(FY_INCLUDE)]
    out = list(df[["ocid", "buyer_name", "tender_title"]].itertuples(index=False, name=None))
    print(f"Loaded {len(out):,} tenders from Excel fallback.")
    return out


def write_csv(labels: list[tuple[str, str, str]]) -> None:
    LABELS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with LABELS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ocid", "sector_name", "classification_method"])
        w.writerows(labels)
    print(f"Wrote {LABELS_CSV} ({len(labels):,} rows).")


def update_db(labels: list[tuple[str, str, str]]) -> None:
    if not DB_PATH.exists():
        print("SQLite not found; skipping DB update.", file=sys.stderr)
        return
    conn = sqlite3.connect(DB_PATH)
    sector_to_id = dict(conn.execute("SELECT sector_name, sector_id FROM dim_sector").fetchall())
    missing = {s for _, s, _ in labels} - set(sector_to_id)
    if missing:
        raise RuntimeError(f"dim_sector missing rows for: {missing}")
    payload = [(sector_to_id[s], ocid) for ocid, s, _ in labels]
    cur = conn.cursor()
    cur.execute("BEGIN")
    cur.executemany("UPDATE fact_tenders SET sector_id = ? WHERE ocid = ?", payload)
    conn.commit()
    print(f"Updated {cur.rowcount:,} rows in fact_tenders.sector_id.")
    conn.close()


# --------------------------------------------------------------------------- #
# Eyeball report
# --------------------------------------------------------------------------- #
def eyeball(rows: list[tuple[str, str | None, str | None]],
            labels: list[tuple[str, str, str]]) -> None:
    rng = random.Random(RANDOM_SEED)
    total = len(labels)

    by_sector = Counter(s for _, s, _ in labels)
    by_method = Counter(m for _, _, m in labels)

    print("\n" + "=" * 64)
    print("SECTOR DISTRIBUTION")
    print("=" * 64)
    for sec, _ in sorted(by_sector.items(), key=lambda x: -x[1]):
        n = by_sector[sec]
        print(f"  {sec:20s} {n:6,d}  ({100*n/total:5.1f}%)")

    print("\n" + "=" * 64)
    print("CLASSIFICATION METHOD DISTRIBUTION")
    print("=" * 64)
    for m, _ in sorted(by_method.items(), key=lambda x: -x[1]):
        n = by_method[m]
        print(f"  {m:20s} {n:6,d}  ({100*n/total:5.1f}%)")

    by_ocid = {ocid: (buyer, title) for ocid, buyer, title in rows}
    by_sec_idx: dict[str, list[tuple[str, str, str]]] = {}
    for ocid, sec, method in labels:
        by_sec_idx.setdefault(sec, []).append((ocid, sec, method))

    print("\n" + "=" * 64)
    print("5 RANDOM SAMPLES PER SECTOR")
    print("=" * 64)
    for sec in sorted(by_sec_idx):
        sample = rng.sample(by_sec_idx[sec], min(5, len(by_sec_idx[sec])))
        print(f"\n[{sec}]  (n={len(by_sec_idx[sec])})")
        for ocid, _, method in sample:
            buyer, title = by_ocid[ocid]
            print(f"  - {ocid}  [{(buyer or '?')[:35]:35s}]  ({method})")
            print(f"      {(title or '')[:140]}")

    print("\n" + "=" * 64)
    print("10 RANDOM ROWS FROM 'other' (eyeball for misclassification)")
    print("=" * 64)
    others = by_sec_idx.get("other", [])
    sample = rng.sample(others, min(10, len(others)))
    for ocid, _, method in sample:
        buyer, title = by_ocid[ocid]
        print(f"  - [{(buyer or '?')[:35]:35s}]  ({method})")
        print(f"      {(title or '')[:160]}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    rows = load_tenders()
    labels: list[tuple[str, str, str]] = []
    for ocid, buyer_name, title in rows:
        sector, method = classify(title, buyer_name)
        labels.append((ocid, sector, method))
    write_csv(labels)
    update_db(labels)
    eyeball(rows, labels)


if __name__ == "__main__":
    main()