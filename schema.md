# DSM Database Schema — `db/dsm.sqlite`

> **Source**: OCDS Assam procurement data (FY 2020–23), loaded via `build.py`.
> **Currency**: All monetary values are in **INR**.
> **Connect**: `sqlite3.connect("db/dsm.sqlite")`

---

## Star Schema (use these for analysis)

### `fact_tenders` — 17 729 rows

| Column | Type | Notes |
|---|---|---|
| `ocid` | TEXT **PK** | OCDS release ID, join key to `fact_awards` |
| `tender_id` | TEXT | |
| `buyer_id` | INT | FK → `dim_buyer` |
| `sector_id` | INT | FK → `dim_sector` (classifier-assigned) |
| `procurement_method` | TEXT | `Open Tender · Limited · Open Limited · Global Tenders · Single` |
| `category_mechanism` | TEXT | `Item Rate · Works · Lump-sum · Supply · Turn-key · EOI · Empanelment · Percentage · Item Wise · Buy · Fixed-rate · QCBS · Piece-work · Tender cum Auction` |
| `fiscal_year` | TEXT | `2020-2021 · 2021-2022 · 2022-2023` |
| `tender_value_amount` | REAL | Estimated cost (INR). Range 0 – 20 B |
| `number_of_tenderers` | REAL | Bidders. Range 2 – 1 380; NULL if no bids |
| `has_award` | INT | 0 / 1 |
| `date_published` | TEXT | ISO date string |
| `bid_opening_date` | TEXT | ISO date string |
| `bid_opening_address` | TEXT | Street address |
| `tender_title` | TEXT | Free text |
| `tender_description` | TEXT | Free text |

**Indexes**: `buyer_id`, `fiscal_year`, `sector_id`

---

### `fact_awards` — 12 237 rows

| Column | Type | Notes |
|---|---|---|
| `award_link` | TEXT **PK** | Unique award identifier |
| `ocid` | TEXT | FK → `fact_tenders(ocid)` |
| `supplier_canonical_id` | INT | FK → `dim_supplier` |
| `award_value_amount` | REAL | Awarded amount (INR). Range 0 – 8.6 B |
| `contract_period_start_date` | TEXT | ISO date string |
| `contract_period_duration_days` | REAL | |
| `price_deviation` | REAL | `(award − tender) / tender`. Range −1 to 3 657; NULL when tender_value = 0 |

**Indexes**: `ocid`, `supplier_canonical_id`

---

### `dim_buyer` — 102 rows

| Column | Type |
|---|---|
| `buyer_id` | INT **PK** |
| `buyer_name` | TEXT UNIQUE |

### `dim_supplier` — 6 305 rows

| Column | Type |
|---|---|
| `supplier_canonical_id` | INT **PK** |
| `supplier_name` | TEXT UNIQUE |

### `dim_sector` — 10 rows

| Column | Type |
|---|---|
| `sector_id` | INT **PK** |
| `sector_name` | TEXT UNIQUE |

**Values**: `roads · bridges · buildings · schools · health · water_sanitation · electricity_power · it_computing · vehicles · other`

---

## Relationships

```
dim_buyer ──1:N──▶ fact_tenders ◀──N:1── dim_sector
                        │
                        │ ocid (1:N)
                        ▼
                   fact_awards ──N:1──▶ dim_supplier
```

---

## Staging Tables (raw XLSX sheets, kept for reference)

| Table | Rows | Join key |
|---|---|---|
| `staging_main` | 21 424 | `_link` (INT), `ocid` |
| `staging_awards` | 12 305 | `_link`, `_link_main` → main._link |
| `staging_awards_suppliers` | 12 305 | `_link_awards` → awards._link |
| `staging_bids_details` | 68 358 | `_link_main` |
| `staging_bids_details_tenderers` | 68 358 | `_link_bids_details` |
| `staging_parties` | 111 206 | `_link_main` |
| `staging_statistics` | 6 129 | `_link_main` |
| `staging_tender_amendments` | 7 839 | `_link_main` |
| `staging_tender_identifiers` | 21 424 | `_link_main` |
| `staging_tender_items` | 21 424 | `_link_main` |
| `staging_tender_items_deliveryAddresses` | 21 424 | `_link_tender_items` |
| `staging_tender_milestones` | 156 170 | `_link_main` |
| `staging_tender_participationFees` | 21 424 | `_link_main` |
| `staging_te_it_additionalClassifications` | 850 | `_link_tender_items` |

---

## Quick-Start Snippet

```python
import sqlite3, pandas as pd

conn = sqlite3.connect("db/dsm.sqlite")

# Load fact + dim tables into DataFrames
tenders = pd.read_sql("""
    SELECT ft.*, db.buyer_name, ds.sector_name
    FROM   fact_tenders ft
    LEFT JOIN dim_buyer  db ON ft.buyer_id  = db.buyer_id
    LEFT JOIN dim_sector ds ON ft.sector_id = ds.sector_id
""", conn)

awards = pd.read_sql("""
    SELECT fa.*, ds.supplier_name
    FROM   fact_awards fa
    LEFT JOIN dim_supplier ds ON fa.supplier_canonical_id = ds.supplier_canonical_id
""", conn)

# Merge for tender-award analysis
merged = tenders.merge(awards, on="ocid", how="left")
```
