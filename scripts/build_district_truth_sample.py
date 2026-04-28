"""
Create a 50-row ground truth validation sample for district classification.
- 4 rows each from the top 10 classified districts (by procuring district).
- 10 rows from the "Unclassified" bucket.
"""
import csv
import random
import sqlite3
from pathlib import Path

DB_PATH = Path("db/dsm.sqlite")
OUT_CSV = Path("outputs/district_truth_blank.csv")
RANDOM_SEED = 42

def main():
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    query = """
        SELECT 
            ft.ocid,
            b.buyer_name,
            ft.tender_title,
            ft.bid_opening_address,
            dp.district_name AS district_procuring,
            de.district_name AS district_execution
        FROM fact_tenders ft
        LEFT JOIN dim_buyer b ON ft.buyer_id = b.buyer_id
        LEFT JOIN dim_district_derived dp ON ft.district_procuring_id = dp.district_id
        LEFT JOIN dim_district_derived de ON ft.district_execution_id = de.district_id
        WHERE ft.fiscal_year IN ('2020-2021', '2021-2022', '2022-2023')
    """
    rows = conn.execute(query).fetchall()
    conn.close()

    by_procuring = {}
    unclassified_rows = []
    
    for r in rows:
        d_proc = r["district_procuring"]
        if not d_proc:
            continue
        if d_proc == "Unclassified":
            unclassified_rows.append(r)
        else:
            by_procuring.setdefault(d_proc, []).append(r)

    sorted_districts = sorted(by_procuring.keys(), key=lambda d: len(by_procuring[d]), reverse=True)
    top_10 = sorted_districts[:10]

    rng = random.Random(RANDOM_SEED)
    
    sample = []
    for dist in top_10:
        candidates = by_procuring[dist]
        sampled = rng.sample(candidates, min(4, len(candidates)))
        sample.extend(sampled)
        
    sampled_unclassified = rng.sample(unclassified_rows, min(10, len(unclassified_rows)))
    sample.extend(sampled_unclassified)
    
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ocid", "buyer_name", "tender_title", "bid_opening_address", 
            "district_procuring", "district_execution", "true_district"
        ])
        for r in sample:
            writer.writerow([
                r["ocid"], r["buyer_name"], r["tender_title"], r["bid_opening_address"],
                r["district_procuring"], r["district_execution"], ""
            ])
            
    print(f"Wrote {len(sample)} rows to {OUT_CSV}")

if __name__ == "__main__":
    main()
