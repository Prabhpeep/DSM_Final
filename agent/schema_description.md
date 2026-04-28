# Database Schema Description

This database contains public procurement data for the state of Assam (FY 2020–21 through 2022–23). It tracks tenders (calls for bids) and their associated awards (contracts given to suppliers). All monetary values are in INR (Indian Rupees).

## `fact_tenders`
The primary fact table. One row represents a single tender (contracting process).
- `ocid`: The primary identifier for the tender.
- `buyer_id`: References the procuring department in `dim_buyer`.
- `sector_id`: References the sector classification (e.g., roads, health) in `dim_sector`.
- `procurement_method`: How the tender was competed (e.g., 'Open Tender', 'Limited', 'Single').
- `category_mechanism`: Contracting mechanism (e.g., 'Item Rate', 'Turn-key').
- `fiscal_year`: The financial year (e.g., '2020-2021').
- `tender_value_amount`: The estimated cost of the tender in INR.
- `number_of_tenderers`: The number of bids received. Crucial for calculating single-bidder rates.
- `has_award`: Boolean indicating if the tender resulted in an award.
- `date_published` and `bid_opening_date`: Key process dates.
- `bid_opening_address`: Address string used for geographic analysis.
- `tender_title` and `tender_description`: Free text describing the work.

## `fact_awards`
The secondary fact table. One row represents a single contract awarded. A tender can have multiple awards.
- `award_link`: Unique identifier for the award.
- `ocid`: References the parent tender in `fact_tenders`.
- `supplier_canonical_id`: References the winning contractor in `dim_supplier`.
- `award_value_amount`: The actual contract value in INR.
- `contract_period_start_date` and `contract_period_duration_days`: Execution timeframe.
- `price_deviation`: Calculated as `(award_value_amount - tender_value_amount) / tender_value_amount`.

## `dim_buyer`
Dimension table of procuring entities.
- `buyer_id`: Primary key.
- `buyer_name`: Name of the government department (e.g., 'Public Works Roads Department').

## `dim_supplier`
Dimension table of contractors/suppliers.
- `supplier_canonical_id`: Primary key.
- `supplier_name`: The resolved name of the entity winning the contract.

## `dim_sector`
Dimension table classifying the type of work.
- `sector_id`: Primary key.
- `sector_name`: Sector categories like 'roads', 'bridges', 'buildings', 'schools', 'health', 'water_sanitation', 'electricity_power'.

### Important Analytical Notes
- To calculate **Single-Bidder Rate**, compute the percentage of tenders where `number_of_tenderers = 1`, excluding those where `procurement_method = 'Single'`.
- To calculate **Price Deviation**, use the `price_deviation` column in `fact_awards`.
- To find **Market Concentration** (Top Suppliers), sum `award_value_amount` from `fact_awards` grouped by `supplier_canonical_id`.
