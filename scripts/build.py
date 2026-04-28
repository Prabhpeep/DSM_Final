"""
Load OCDS Assam procurement Excel into a SQLite star schema (trimmed scope).

Run: `python db/build.py`
Input:  XLSX_PATH below.   Output: db/dsm.sqlite

Tables built:
  staging_*       — 14 sheets verbatim (no transforms)
  dim_buyer       — distinct buyer_name from main
  dim_supplier    — distinct name from awards_suppliers (exact-string only)
  dim_sector      — pre-populated 10 codes (sector classifier runs later)
  fact_tenders    — one row per tender, scoped to FY 2020-23
  fact_awards     — one row per award line, scoped via fact_tenders.ocid

Re-running drops and rebuilds.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
import pandas as pd

# --- Config ---
XLSX_PATH = Path("data/raw/ocds_mapped_data_fiscal_year_2016_2022_v3.xlsx")
DB_PATH = Path("db/dsm.sqlite")
TARGET_FYS = ("2020-2021", "2021-2022", "2022-2023")
SECTOR_CODES = ["roads", "bridges", "buildings", "schools", "health",
                "water_sanitation", "electricity_power", "it_computing",
                "vehicles", "other"]


def load_staging(conn):
    print(f"\n[1/4] Staging from {XLSX_PATH} ...")
    sheets = pd.read_excel(XLSX_PATH, sheet_name=None)
    for name, df in sheets.items():
        df.to_sql(f"staging_{name}", conn, if_exists="replace", index=False)
        print(f"  staging_{name:<48s} {len(df):>7,} rows")
    return sheets


def build_dims(sheets, conn):
    print("\n[2/4] Dimensions ...")
    buyers = sheets["main"]["buyer_name"].dropna().drop_duplicates().sort_values().reset_index(drop=True)
    suppliers = sheets["awards_suppliers"]["name"].dropna().drop_duplicates().sort_values().reset_index(drop=True)
    dim_buyer = pd.DataFrame({"buyer_id": range(1, len(buyers) + 1), "buyer_name": buyers})
    dim_supplier = pd.DataFrame({"supplier_canonical_id": range(1, len(suppliers) + 1),
                                 "supplier_name": suppliers})
    dim_sector = pd.DataFrame({"sector_id": range(1, len(SECTOR_CODES) + 1),
                               "sector_name": SECTOR_CODES})

    conn.executescript("""
        DROP TABLE IF EXISTS dim_buyer;
        DROP TABLE IF EXISTS dim_supplier;
        DROP TABLE IF EXISTS dim_sector;
        CREATE TABLE dim_buyer    (buyer_id INTEGER PRIMARY KEY, buyer_name TEXT NOT NULL UNIQUE);
        CREATE TABLE dim_supplier (supplier_canonical_id INTEGER PRIMARY KEY, supplier_name TEXT NOT NULL UNIQUE);
        CREATE TABLE dim_sector   (sector_id INTEGER PRIMARY KEY, sector_name TEXT NOT NULL UNIQUE);
    """)
    dim_buyer.to_sql("dim_buyer", conn, if_exists="append", index=False)
    dim_supplier.to_sql("dim_supplier", conn, if_exists="append", index=False)
    dim_sector.to_sql("dim_sector", conn, if_exists="append", index=False)
    print(f"  dim_buyer {len(dim_buyer):>5,} | dim_supplier {len(dim_supplier):>5,} | dim_sector {len(dim_sector):>3,}")
    return dim_buyer, dim_supplier


def _iso(s: pd.Series) -> pd.Series:
    """Stringify date-ish column, preserving NULL for missing values."""
    return s.astype(str).where(s.notna(), None)


def build_fact_tenders(sheets, dim_buyer, conn):
    print("\n[3/4] fact_tenders ...")
    main = sheets["main"]
    awarded_links = set(sheets["awards"]["_link_main"].unique())

    # main has its own text buyer_id — drop it so the merge yields the integer FK only
    m = (main[main["tender_fiscalYear"].isin(TARGET_FYS)]
         .drop(columns=["buyer_id"])
         .merge(dim_buyer, on="buyer_name", how="left"))

    fact_tenders = pd.DataFrame({
        "ocid":                m["ocid"],
        "tender_id":           m["tender_id"],
        "buyer_id":            m["buyer_id"],
        "sector_id":           pd.NA,                      # filled later by classifier
        "procurement_method":  m["tender_procurementMethod"],
        "category_mechanism":  m["tender_mainProcurementCategory"],
        "fiscal_year":         m["tender_fiscalYear"],
        "tender_value_amount": m["tender_value_amount"],
        "number_of_tenderers": m["tender_numberOfTenderers"],
        "has_award":           m["_link"].isin(awarded_links).astype(int),
        "date_published":      _iso(m["tender_datePublished"]),
        "bid_opening_date":    _iso(m["tender_bidOpening_date"]),
        "bid_opening_address": m["tender_bidOpening_address_streetAddress"],
        "tender_title":        m["tender_title"],
        "tender_description":  m["tender_description"],
    })

    conn.executescript("""
        DROP TABLE IF EXISTS fact_tenders;
        CREATE TABLE fact_tenders (
            ocid                 TEXT PRIMARY KEY,
            tender_id            TEXT,
            buyer_id             INTEGER REFERENCES dim_buyer(buyer_id),
            sector_id            INTEGER REFERENCES dim_sector(sector_id),
            procurement_method   TEXT,
            category_mechanism   TEXT,
            fiscal_year          TEXT,
            tender_value_amount  REAL,
            number_of_tenderers  REAL,
            has_award            INTEGER,
            date_published       TEXT,
            bid_opening_date     TEXT,
            bid_opening_address  TEXT,
            tender_title         TEXT,
            tender_description   TEXT
        );
        CREATE INDEX idx_ft_buyer  ON fact_tenders(buyer_id);
        CREATE INDEX idx_ft_fy     ON fact_tenders(fiscal_year);
        CREATE INDEX idx_ft_sector ON fact_tenders(sector_id);
    """)
    fact_tenders.to_sql("fact_tenders", conn, if_exists="append", index=False)
    print(f"  fact_tenders {len(fact_tenders):>7,} rows  (FY {', '.join(TARGET_FYS)})")
    return fact_tenders


def build_fact_awards(sheets, fact_tenders, dim_supplier, conn):
    print("\n[4/4] fact_awards ...")
    awards, awards_sup, main = sheets["awards"], sheets["awards_suppliers"], sheets["main"]

    # awards_suppliers links to awards via _link_awards -> awards._link.
    # Rename main columns explicitly so the merge doesn't collide with awards._link / _link_main.
    main_slim = (main[["_link", "ocid", "tender_value_amount"]]
                 .rename(columns={"_link": "main_link"}))
    a = (awards
         .merge(awards_sup[["_link_awards", "name"]],
                left_on="_link", right_on="_link_awards", how="left")
         .merge(main_slim, left_on="_link_main", right_on="main_link", how="left"))

    # Scope to FY 2020-23 by intersecting on fact_tenders' ocids
    a = a[a["ocid"].isin(set(fact_tenders["ocid"]))]
    a = a.merge(dim_supplier, left_on="name", right_on="supplier_name", how="left")

    # price_deviation only where tender_value_amount > 0; do NOT winsorize at load time
    tv, av = a["tender_value_amount"], a["value_amount"]
    price_dev = (av - tv) / tv
    price_dev = price_dev.where(tv > 0, other=pd.NA)

    fact_awards = pd.DataFrame({
        "award_link":                    a["_link"],
        "ocid":                          a["ocid"],
        "supplier_canonical_id":         a["supplier_canonical_id"],
        "award_value_amount":            a["value_amount"],
        "contract_period_start_date":    _iso(a["contractPeriod_startDate"]),
        "contract_period_duration_days": a["contractPeriod_durationInDays"],
        "price_deviation":               price_dev,
    })

    # Defensive cleanup: NaN PK is illegal; multi-supplier awards would duplicate award_link.
    n0 = len(fact_awards)
    fact_awards = fact_awards.dropna(subset=["award_link"])
    fact_awards = fact_awards.drop_duplicates(subset=["award_link"], keep="first")
    if len(fact_awards) != n0:
        print(f"  note: dropped {n0 - len(fact_awards)} rows (NaN or duplicate award_link)")

    # Nullable Int64 so missing supplier FKs serialize as SQL NULL (not float NaN)
    fact_awards["supplier_canonical_id"] = fact_awards["supplier_canonical_id"].astype("Int64")

    conn.executescript("""
        DROP TABLE IF EXISTS fact_awards;
        CREATE TABLE fact_awards (
            award_link                    TEXT PRIMARY KEY,
            ocid                          TEXT REFERENCES fact_tenders(ocid),
            supplier_canonical_id         INTEGER REFERENCES dim_supplier(supplier_canonical_id),
            award_value_amount            REAL,
            contract_period_start_date    TEXT,
            contract_period_duration_days REAL,
            price_deviation               REAL
        );
        CREATE INDEX idx_fa_ocid     ON fact_awards(ocid);
        CREATE INDEX idx_fa_supplier ON fact_awards(supplier_canonical_id);
    """)
    fact_awards.to_sql("fact_awards", conn, if_exists="append", index=False)
    print(f"  fact_awards  {len(fact_awards):>7,} rows  (FY {', '.join(TARGET_FYS)})")


def report(conn):
    cur = conn.cursor()
    staging = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'staging_%' ORDER BY name")]
    analytical = ["dim_buyer", "dim_supplier", "dim_sector", "fact_tenders", "fact_awards"]

    print("\n=== Staging row counts ===")
    for t in staging:
        print(f"  {t:55s} {cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>7,}")

    print("\n=== Analytical row counts ===")
    for t in analytical:
        print(f"  {t:20s} {cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>7,}")

    print("\n=== 5-row samples ===")
    with pd.option_context("display.max_colwidth", 60, "display.width", 180):
        for t in analytical:
            print(f"\n--- {t} ---")
            print(pd.read_sql(f"SELECT * FROM {t} LIMIT 5", conn).to_string(index=False))

    null_secs = cur.execute("SELECT COUNT(*) FROM fact_tenders WHERE sector_id IS NULL").fetchone()[0]
    total = cur.execute("SELECT COUNT(*) FROM fact_tenders").fetchone()[0]
    print(f"\n=== Sanity ===")
    print(f"  fact_tenders sector_id NULL: {null_secs:,} / {total:,}  (expected: equal — classifier not run yet)")


def main():
    if not XLSX_PATH.exists():
        raise SystemExit(f"Excel not found: {XLSX_PATH.resolve()}")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()  # trim spec — no idempotency, fresh build each run

    conn = sqlite3.connect(DB_PATH)
    try:
        # FKs are declared in DDL but not enforced — spec only asks for the columns,
        # and pandas to_sql can pass float-NaN for missing integers which trips enforcement.
        sheets = load_staging(conn)
        dim_buyer, dim_supplier = build_dims(sheets, conn)
        fact_tenders = build_fact_tenders(sheets, dim_buyer, conn)
        build_fact_awards(sheets, fact_tenders, dim_supplier, conn)
        conn.commit()
        report(conn)
    finally:
        conn.close()
    print(f"\nDone. DB at {DB_PATH.resolve()}")


if __name__ == "__main__":
    main()