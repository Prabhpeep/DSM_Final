# Pre-commitment Data Quality Checks — Assam OCDS Procurement Dataset

**Dataset:** `ocds_mapped_data_fiscal_year_2016_2022_v3.xlsx`  
**Scope:** FY 2016–2022 · 21,424 tenders · 14 sheets  
**Date:** 2026-04-24  
**Purpose:** Determine whether the dataset supports (a) contractor concentration analysis and (b) structural integrity/red-flag indicators per Fazekas/GTI methodology.

> [!NOTE]
> All output tables are saved as CSVs in `dq_outputs/`. The script that produced all results is [dq_checks.py](file:///Users/prabhpreet16/Downloads/DSM_FP/dq_checks.py).

---

## Check 1: Awards Join Integrity

**Goal:** Confirm that `awards` joins cleanly to `main` and understand the structure of the join.

### Code

```python
# Join awards to main on awards._link_main = main._link
merged = main.merge(awards, left_on='_link', right_on='_link_main',
                    how='left', suffixes=('', '_aw'))

# Count awards per tender
awards_per_tender = awards.groupby('_link_main').size().reset_index(name='award_count')
main_with_counts  = main.merge(awards_per_tender, left_on='_link',
                               right_on='_link_main', how='left')
main_with_counts['award_count'] = main_with_counts['award_count'].fillna(0).astype(int)

# Orphan check
orphan_links = set(awards['_link_main'].unique()) - set(main['_link'].unique())
```

### 1a. Join Statistics

| Metric | Value |
|---|---|
| Total rows in `main` | 21,424 |
| Total rows in `awards` | 12,305 |
| Main tenders with ≥1 award | **6,129** |
| Main tenders with 0 awards | **15,295 (71.4%)** |
| Orphan award rows | **0** |

**Award-count distribution:**

| Awards per tender | Count of tenders |
|---|---|
| 0 | 15,295 |
| 1 | 5,869 |
| 2 | 146 |
| 3 | 45 |
| 4 | 17 |
| 5+ | 52 |

> [!IMPORTANT]
> **71.4% of tenders have no matching award row.** Zero orphans — the join itself is referentially clean. The missing awards are the concern.

### 1b. No-Award Breakdown

**By procurement method:**

| Method | No-award count | Total | % without award |
|---|---|---|---|
| Open Tender | 15,048 | 21,057 | 71.5% |
| Limited | 152 | 235 | 64.7% |
| Open Limited | 66 | 94 | 70.2% |
| Global Tenders | 16 | 21 | 76.2% |
| Single | 11 | 15 | 73.3% |
| Auction | 2 | 2 | 100.0% |

The no-award rate is **roughly uniform across methods** (64–76%). This is not concentrated in cancelled or limited tenders — it is a blanket data-availability issue.

**By fiscal year:**

| Fiscal Year | No-award count | Total | % without award |
|---|---|---|---|
| 2016-2017 | 43 | 43 | **100.0%** |
| 2017-2018 | 430 | 430 | **100.0%** |
| 2018-2019 | 1,291 | 1,301 | **99.2%** |
| 2019-2020 | 1,876 | 1,919 | **97.8%** |
| 2020-2021 | 2,681 | 4,367 | 61.4% |
| 2021-2022 | 3,186 | 5,121 | 62.2% |
| 2022-2023 | 5,786 | 8,241 | 70.2% |
| 2023-2024 | 2 | 2 | 100.0% |

> [!WARNING]
> **FY 2016–17 through 2019–20 have essentially zero award data** (97–100% missing). Award-linked analysis is only viable for FY 2020–21 onward. Even then, ~62–70% of tenders lack awards, suggesting the `awards` sheet captures only successfully concluded procurements.

### 1c. Multi-Award Tender Examples (10 random)

| ocid | Title (truncated) | # Awards | Award values (INR) |
|---|---|---|---|
| `2021_HB_21724_1` | Supply of Dietry Article Group A | 4 | 7.4M, 8.0M, 9.9M, 7.2M |
| `2022_ICD_24499_1` | Construction of 150Nos Sanitary Toilets Under CSR DNPL | 3 | 0.93M × 3 |
| `2022_PWBNH_27232_9` | Construction of 4 nos Additional Class room, Lab... | 3 | 5.5M, 5.5M, 5.7M |
| `2022_ICD_26063_1` | Procurement of Assorted Pipes and Flanges | 3 | 0.07M, 5.0M, 0.04M |
| `2022_PHED_24340_1` | Empanelment for supply of ISI marked Ferric Alum | 3 | 1, 1, 1 |
| `2023_PWD_29303_1` | Construction of RCC slab culvert | 2 | 4.5M, 0.45M |
| `2022_HFWD_24509_1` | Supply of Surgical and Consumables | 4 | 1.6M, 2.1M, 0.2M, 1.0M |
| `2022_BoTC_27838_1` | Different works of ERM, Sukla Irrigation | 2 | 9.0M, 9.0M |
| `2021_AAU_22718_1` | Procurement of Post-Harvest machineries | 8 | 1.9M to 6.2M |
| `2022_HFWD_26831_1` | Supply of Hospital Furniture and Fixtures | 4 | 1, 1, 1, 1 |

Multi-award tenders are a mix of **lot-based procurements** (different lot values), **multi-supplier supply contracts** (similar values), and **placeholder/rate-contract entries** (value = ₹1). The ₹1 values in empanelment/rate contracts are data artefacts, not real financial amounts.

### 1d. Sanity-Check Joined Rows (5 random)

| ocid | tender_value | award_value | buyer |
|---|---|---|---|
| `2021_PHED_20968_8` | 0 | 0 | Public Health Engineering Department |
| `2021_PHED_20968_2` | 0 | 0 | Public Health Engineering Department |
| `2022_BTC_24818_1` | ₹95.2L | ₹89.5L | Bodoland Territorial Council-PWD |
| `2022_PWBNH_26543_6` | ₹87.1L | ₹82.4L | Public Works Building and NH Department |
| `2023_BTC_29569_1` | ₹34.6L | ₹34.6L | Bodoland Territorial Council-PWD |

The join is **semantically meaningful** — award values are ≤ tender estimates where expected (typical competitive discount), and buyer names correspond to the procuring entities. The PHED zero-value rows are rate-contract empanelments.

### Interpretation

The awards join is referentially clean (zero orphans), but **only 28.6% of tenders have award data**. This is strongly year-dependent: FY 2016–2020 is essentially empty for awards. For FY 2020-21 onward, about 35–39% of tenders have awards, likely representing completed/concluded procurements. Multi-award tenders are structurally genuine (lots, multi-supplier supply) with ~260 cases. The unit of analysis for concentration/integrity work should be the **award line** (not the tender), since lot-based tenders split value across multiple winners. We must document (and potentially test for selection bias in) the systematic gap between tendered and awarded populations.

---

## Check 2: Price Deviation Distribution

**Goal:** Compute the distribution of `(award_value − tender_estimate) / tender_estimate`.

### Code

```python
# Filter to rows with both values present and tender_value > 0
both_nonnull = inner[
    inner['tender_value_amount'].notna() &
    inner['value_amount'].notna() &
    (inner['tender_value_amount'] > 0)
].copy()

both_nonnull['price_deviation'] = (
    both_nonnull['value_amount'] - both_nonnull['tender_value_amount']
) / both_nonnull['tender_value_amount']
```

### 2a. Sample Size

| Metric | Value |
|---|---|
| Rows with both values non-null and tender_value > 0 | **5,150** |
| As % of all awards (12,305) | 41.9% |
| As % of all main tenders (21,424) | 24.0% |
| Awards with value_amount ≤ 0 or null (excluded) | 5,710 |

### 2b. Distribution Statistics

| Statistic | Value |
|---|---|
| min | -1.0000 |
| P01 | -0.9999 |
| P05 | -0.9100 |
| P10 | -0.3076 |
| **P25** | **-0.1000** |
| **P50 (median)** | **-0.0500** |
| **P75** | **-0.0001** |
| P90 | 0.0000 |
| P95 | 0.0497 |
| P99 | 0.2293 |
| max | 3,657.0 |
| mean | 1.138 |
| std | 63.82 |

**Deviation class counts:**

| Class | Count | % of sample |
|---|---|---|
| Exact match (deviation = 0) | 289 | 5.6% |
| Below estimate (deviation < 0) | 4,411 | **85.7%** |
| Above estimate (deviation > 0) | 450 | 8.7% |
| \|deviation\| > 50% | 468 | 9.1% |
| \|deviation\| > 200% | 7 | 0.1% |

### 2c. Sanity Flags

**Median deviation by procurement method:**

| Method | Median | Mean | Count |
|---|---|---|---|
| Open Tender | **-0.050** | -0.108 | 5,062 |
| Limited | 0.000 | 63.069 | 58 |
| Open Limited | -0.256 | 101.836 | 27 |
| Single | 0.103 | 0.103 | 2 |
| Global Tenders | -0.115 | -0.115 | 1 |

> [!NOTE]
> Open Tender has a median of -5.0%, which is at the lower bound of the -5% to -15% range expected in competitive procurement. Limited tenders have a median of 0.0% (no discount), consistent with less competition. The extremely high means for Limited and Open Limited are driven by a handful of extreme outliers (see below) and are not representative.

**5 most negative deviations:**

All five are from the same tender package (`ocds-f5kvwu-2021_PWD_23764`) — road construction in Dimapur, with `award_value = 0` against non-zero tender estimates. These are likely **cancelled/null awards** encoded as zero rather than null. Deviation of -1.0000 is an artefact.

**5 most positive deviations:**

| ocid | tender_value | award_value | Deviation | Notes |
|---|---|---|---|---|
| `2022_APGCL_26440_1` | ₹1,000 | ₹36.6L | +3,657x | Placeholder tender value (₹1,000) |
| `2022_ICD_27058_1` | ₹120 | ₹3.3L | +2,757x | Placeholder tender value (₹120) |
| `2022_ACCF_25844_1` | ₹50L | ₹7.5Cr | +13.9x | Possible rebid at expanded scope |
| `2021_PWBNH_21467_1` | ₹57L | ₹5.99Cr | +9.5x | Possible order-of-magnitude data entry error |
| `2022_BoTC_24367_1` | ₹14.7L | ₹1.48Cr | +9.1x | Similar pattern — 10x off |

The top two are clearly **placeholder tender values** (₹120, ₹1,000). The remainder appear to be order-of-magnitude data entry issues or scope changes.

### Interpretation

The price deviation distribution is **consistent with a functioning competitive procurement system**: the median is -5.0% (awarded bids come in below estimate), 85.7% of awards are below estimate, and the IQR spans -10.0% to -0.01%. The sample size of 5,150 is adequate for statistical analysis but is only 24% of total tenders, which limits generalizability. The 5.6% exact-zero matches are a mild flag — this could be post-hoc reconciliation, but the proportion is low enough not to dominate the distribution. Extreme outliers (>200% deviation) are rare (7 cases, 0.1%) and traceable to placeholder values or data entry errors; these should be winsorized or excluded. The pattern across procurement methods matches expectations: open tenders show stronger competitive discounts than limited tenders. Price deviation is viable as a core integrity indicator, but the extreme tails need cleaning and the analysis should be restricted to `tender_value_amount > 0` and `awards.value_amount > 0`.

---

## Check 9: Category Sanity

**Goal:** Determine whether `tender_mainProcurementCategory` represents sectors or contracting mechanisms.

### Code

```python
cat_agg = main.groupby('tender_mainProcurementCategory').agg(
    n_tenders        = ('_link', 'count'),
    total_value_inr  = ('tender_value_amount', 'sum'),
    median_value_inr = ('tender_value_amount', 'median'),
    n_distinct_buyers= ('buyer_name', 'nunique')
).sort_values('n_tenders', ascending=False)

cat_agg['total_value_cr'] = (cat_agg['total_value_inr'] / 1e7).round(1)
```

### 9a. Category Summary

| Category | Tenders | Total Value (₹Cr) | Median Value (₹Cr) | Distinct Buyers |
|---|---|---|---|---|
| **Item Rate** | 10,385 | 59,233.2 | 1.18 | 80 |
| **Works** | 4,246 | 14,914.3 | 0.89 | 62 |
| **Supply** | 2,090 | 2,931.5 | 0.53 | 66 |
| **Turn-key** | 1,976 | 14,478.9 | 0.52 | 22 |
| **Lump-sum** | 1,119 | 6,289.4 | 1.50 | 29 |
| Item Wise | 617 | 1,055.6 | 0.63 | 50 |
| Percentage | 488 | 256.0 | 0.26 | 15 |
| EOI | 219 | 1,151.0 | 0.33 | 49 |
| Buy | 151 | 152.7 | 1.00 | 8 |
| Empanelment | 95 | 53.8 | 0.00 | 16 |
| Fixed-rate | 19 | 111.9 | 0.59 | 4 |
| QCBS | 9 | 0.9 | 0.00 | 4 |
| Tender cum Auction | 6 | 0.0 | — | 2 |
| Piece-work | 2 | 0.0 | 0.00 | 2 |
| Multi-stage | 1 | 0.0 | — | 1 |
| PPP-BoT-Annuity | 1 | 3.7 | 3.74 | 1 |

### 9b. Example Titles (3 per category)

| Category | Example titles |
|---|---|
| **Item Rate** | "Construction of Hatigandhoi gaon road…"; "TN_17_73R"; "Supply of Dietary articles for District Jail…" |
| **Works** | "Construction of drainage system…AIIMS Guwahati"; "I/M for recoupment of Pachonia area from flood…"; "Construction of ICBP road at Amteka…" |
| **Supply** | "SUPPLY OF FERTILIZERS"; "Supply of Tricycle Rickshaw…designed by IIT Guwahati"; "SUPPLY OF RADIO DIAGNOSTICS…FOR JORHAT MEDICAL COLLEGE" |
| **Turn-key** | "Construction of new 33/11 kv substation…"; "Construction of PHC at Ambikapur…under NHM"; "Construction of Buildingless Sub Health Centre…" |
| **Lump-sum** | "Construction of sump at Rajgarh Road…"; "Cleaning and Desilting of 143 nos of Drains…"; "Sale out of taken over assets (Land and Buildings)…" |

The titles confirm that categories like "Item Rate", "Lump-sum", "Percentage", "Turn-key", "QCBS" are **pricing/contracting mechanisms**, not economic sectors. "Works" and "Supply" have sector-like names but actually describe contract direction (construction vs. goods procurement). A road construction tender can be classified as either "Item Rate" or "Works" depending on the pricing mechanism.

### 9c. Cross-tab: Category × Contract Type

|  | Empanelment | Rate Contract | Tender |
|---|---|---|---|
| Item Rate | 13 | 640 | 9,732 |
| Works | 3 | 45 | 4,198 |
| Supply | 13 | 108 | 1,969 |
| Turn-key | 1 | 9 | 1,966 |
| Lump-sum | 1 | 8 | 1,110 |
| Other (11 cats) | ... | ... | ... |

The two fields are **partially overlapping** but not orthogonal. Most categories map overwhelmingly to `contractType = "Tender"`, but "Buy" has 26% rate contracts and "Empanelment" is 87% empanelment-type. This confirms that the category field is a contracting mechanism dimension, not a sector dimension.

### 9d. Keyword-Based Sector Feasibility

| Keyword | Matching tenders | % of total |
|---|---|---|
| **road** | **4,402** | **20.5%** |
| **building** | **1,654** | **7.7%** |
| **school** | **1,067** | **5.0%** |
| **health** | **903** | **4.2%** |
| **water** | **651** | **3.0%** |
| **hospital** | **454** | **2.1%** |
| **medical** | **358** | **1.7%** |
| **equipment** | **341** | **1.6%** |
| bridge | 256 | 1.2% |
| vehicle | 73 | 0.3% |
| computer | 68 | 0.3% |
| IT | 31 | 0.1% |
| drug | 28 | 0.1% |
| sanitation | 16 | 0.1% |
| electricity | 11 | 0.1% |

> [!TIP]
> Title-based sector classification is **viable as a fallback**. Five keyword-derived sectors have >300 tenders: **road** (4,402), **building** (1,654), **school** (1,067), **health** (903), and **water** (651). A composite "health" sector (hospital + health + medical + drug) would yield ~1,500+ tenders. A "transport infrastructure" sector (road + bridge) yields ~4,658. These volumes are analytically sufficient.

### Interpretation

`tender_mainProcurementCategory` is **not** a sectoral variable — it encodes the pricing/contracting mechanism (item rate, lump-sum, turnkey, percentage, etc.). It cannot be used directly for sectoral analysis. It is, however, useful as a **control variable** in integrity-risk regression models, since different pricing mechanisms have different structural characteristics (e.g., item rate vs. lump-sum tenders have different competitive dynamics). For sectoral analysis, a **keyword-based classifier on `tender_title`** is feasible and can produce at least 5 sectors with >300 tenders each. A more robust approach would combine keywords with `buyer_name` (e.g., Public Works Roads Department → roads, PHED → water, NHM → health), which would improve recall significantly. The category field should be retained as a separate analytical dimension (contracting mechanism) rather than discarded.

---

## Go / No-Go Summary

### Check 1 (Awards Join): **GO-WITH-CAVEATS**

The join is referentially clean (zero orphans) and semantically correct, but only 28.6% of tenders have award data. Coverage is catastrophically low for FY 2016–2020 (0–3%) and moderate for FY 2020–2023 (30–39%). Supplier concentration analysis must be **scoped to FY 2020-21 through 2022-23** (~17,729 tenders, ~6,100 with awards). Within that window, the awarded subset likely represents *completed* procurements, which introduces survivorship selection — concentration metrics will describe the awarded market, not the full tendered market. This should be documented as a limitation, and we should test whether the awarded subset differs systematically from the non-awarded subset on observables (value, method, buyer). Multi-award tenders (260 cases) are structurally genuine and should be analyzed at the award-line level. Placeholder awards with value = ₹1 (~a few dozen cases in empanelment/rate contracts) should be excluded from financial analysis.

### Check 2 (Price Deviation): **GO**

Price deviation is viable as a core structural indicator. The sample size of 5,150 is adequate, the distribution shape is plausible (median = -5%, 85.7% below estimate), and the pattern across procurement methods matches theoretical expectations (open > limited competition). The 5.6% exact-zero rate is within tolerable bounds for e-procurement data. The tails need light cleaning: exclude `award_value = 0` (cancelled-as-zero artefacts) and winsorize or exclude the ~7 cases with |deviation| > 200% (placeholder tender values). After cleaning, the core metric is well-behaved and analytically serviceable for the Fazekas/GTI framework.

### Check 9 (Category Sanity): **GO-WITH-CAVEATS**

The category field is a contracting-mechanism variable, not a sectoral variable. Direct sectoral analysis from this field is **not possible**. However, a **hybrid classification** approach is viable: use keyword matching on `tender_title` (5+ sectors with >300 tenders each) supplemented by `buyer_name` mapping (department → sector) to build a derived sector variable. This is additional scope — budget approximately one day of regex/manual-mapping work to build and validate the sector classifier. In the meantime, `tender_mainProcurementCategory` should be retained as a separate control/stratification variable for contracting mechanism.

---

### Overall Recommendation

The planned project structure — **concentration analysis as spine + integrity-risk layer + sectoral/geographic layer** — is **viable with two scoping adjustments**: (1) restrict the analysis window to **FY 2020-21 through 2022-23** to ensure adequate award coverage, and (2) plan one round of **derived-sector classification** work (keyword + buyer mapping) before the sectoral layer can be built. The concentration spine and integrity-risk layer (price deviation, single bidding, etc.) can proceed immediately on the FY 2020–23 subsample. No fundamental blockers exist.
