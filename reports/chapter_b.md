# Chapter B: Structural Integrity Indicators (RQ2)

## 1. Question and Motivation
**Research Question:** What structural integrity indicators characterize Assam procurement, and which buyer × sector combinations show elevated composite risk scores?

Public procurement is vulnerable to inefficiencies and restricted competition. Rather than relying solely on post-hoc audits of individual contracts, we use a systematic data-driven approach based on the Government Transparency Institute (Fazekas et al.) methodology. This identifies objective patterns in tendering that correlate with restricted competition. Identifying elevated structural risk indicators allows oversight resources to be targeted more effectively.

## 2. Methodology
We analyze five structural integrity indicators computed at the buyer × sector level for the FY 2020-23 period.

*   **Price Deviation:** The median of `(award_value - tender_value) / tender_value`. Values are winsorized at [-2.0, 2.0]. Higher deviation (less competitive discount) indicates higher risk.
*   **Single-Bidder Rate:** The share of tenders receiving exactly one bid, excluding legitimately single-source methods (`procurement_method = "Single"`). Computed using bid-detail records.
*   **Non-Open Method Share:** The share of a buyer's tenders using methods other than "Open Tender".
*   **Threshold Bunching:** The excess mass of tender values just below statutory thresholds (₹25 Lakh, ₹1 Crore, ₹10 Crore), measured by comparing the density in the 5 Lakh bin just below the threshold against the average of surrounding bins.
*   **Supplier-Buyer Stickiness:** The percentage of a buyer's total award value going to its top-3 suppliers.

**Composite Score:** Each indicator is converted to a percentile rank (0-100) within its sector to ensure within-sector comparability. The final composite score is an equal-weighted average of the five percentiles.

## 3. Findings

### Price Deviation
The overall median price deviation for the clean subset is negative (-0.06), indicating a baseline competitive discount. However, this varies significantly across sectors and buyers.
![Price Deviation Distribution](figures/price_deviation_distribution.png)
![Price Deviation by Sector](figures/price_deviation_by_sector.png)

### Single-Bidder Rate
Globally, ~6% of tenders with bid data received exactly one bid. Sectoral variation is stark, with some sectors exhibiting elevated structural single-bidder rates.
![Single-Bidder Rate by Sector](figures/single_bidder_by_sector.png)

### Non-Open Method Share
While 98.2% of all tenders use the "Open Tender" method, a small number of buyer × sector combinations rely heavily on limited or restricted methods, which elevates their structural risk profile.

### Threshold Bunching
We observe noticeable bunching below the ₹1 Crore threshold (excess mass ratio ~1.7), suggesting potential contract sizing patterns warranting scrutiny. The ₹25 Lakh and ₹10 Crore thresholds do not show significant bunching.
![Threshold Bunching - All](figures/threshold_bunching_all.png)

### Supplier-Buyer Stickiness
Stickiness is exceptionally high across the dataset, with the median buyer awarding 100% of their sector value to their top 3 suppliers. This is partially a mechanical result of small buyer portfolios, but the pattern persists even when filtering for larger buyers.
![Stickiness Distribution](figures/stickiness_distribution.png)

### Composite Risk and Top Pairings
The composite risk score successfully differentiates portfolios. Sensitivity analysis confirms the rankings are stable across different weighting schemes (Spearman ρ > 0.85).

![Composite Heatmap](figures/composite_heatmap.png)

**Top-5 Buyer × Sector Risk Pairings:**
1. **Finance Department - World Bank Tenders** (buildings)
2. **Urban Affairs Department Externally Aided Project** (water_sanitation)
3. **Assam State Disaster Management Authority- Externally Aided Project** (schools)
4. **Assam Power Generation Company Limited APGCL - ADB** (electricity_power)
5. **Urban Development Department** (water_sanitation)

## 4. Limitations
*   **Selection Bias:** Because we only have award values for ~29% of tenders, indicators relying on award values (Price Deviation, Stickiness) describe the *awarded subset*, not all procurement.
*   **Missing Bid Data:** 26.4% of tenders lack detailed bid records, removing them from the single-bidder calculation denominator.
*   **Indicator Nature:** These metrics are *structural risk indicators*, not evidence of impropriety. High scores warrant scrutiny, not automatic condemnation.

## 5. Implications for Recommendations
*   **Targeted Oversight:** Buyer × sector combinations with high composite scores should be prioritized for routine qualitative audits.
*   **Threshold Review:** The bunching around the ₹1 Crore mark implies that oversight and approval requirements triggered at this threshold should be reviewed for effectiveness.
*   **Sector-Specific Baselines:** The wide variance in single-bidder rates across sectors confirms that competition guidelines must be sector-specific rather than universal.
