# Results & Writing Instructions for Blog Post

## Overview of Experiments and Results (Sequential)
- **Data Quality & Basic EDA**: Processed 21,424 tenders across 14 sheets spanning FY 2020-23. Found only ~12,000 awards across ~111,000 parties. 
  - *Key Takeaway*: There is a massive 71.4% gap between published tenders and published awards, representing a systemic transparency deficit.
- **Concentration Analysis (Q1)**: Computed Herfindahl-Hirschman Index (HHI), Gini coefficients, and concentration ratios. Clustered buyers using K-Means into 4 typologies.
  - *Key Takeaway*: "Captured-Supplier Buyers" exist which look competitive during the tendering phase (high open tender rate, similar bidder counts) but their awards are highly concentrated among top-3 suppliers (HHI > 4,500).
- **Structural Integrity Analysis (Q2)**: Calculated 5 Fazekas risk indicators (price deviation, single-bidder rate, non-open method share, threshold bunching, and supplier stickiness). 
  - *Key Takeaway*: Naive composite scores without minimum tender limits break down. When stabilized, structural risks concentrate heavily in specific portfolios like Cultural Affairs (61% single bidder) and PWD Building & NH (largest volume). Notable threshold bunching observed around ₹1 Crore.
- **Geographic Classification (Q3)**: Built a district classifier splitting "Procuring District" (office address) vs. "Execution District" (from title keywords).
  - *Key Takeaway*: Procurement is artificially centralized (35.8% to Kamrup Metropolitan) because state-level offices procure for the whole state. Geographic tracking is unreliable unless execution location is explicitly parsed.

## Answers to Key Questions (Blog Skeleton Data)

**The Dataset**
- 21,424 tenders across 14 sheets spanning three years of post-pandemic public spending (FY 2020-23). 
- Around 111,000 parties involved but only ~12,000 awards published.
- **The Gap**: 71.4% of tenders have no award data published. This isn't just missing data; it's a finding about the limits of current e-procurement transparency.

**Q1: Who actually wins?**
- Lorenz curves show high inequality. HHI analysis identifies high variance between buyers.
- Top-20 suppliers dominate certain key sectors.
- **Buyer Typologies (K-Means)**: Grouped buyers into four clusters. The headline is the **Captured-Supplier Buyers** (n=10): They use open methods 99% of the time, have ~5 bidders per tender (just like the competitive mainstream), but their HHI is ~5x higher (4,533) and top-3 supplier share is 92%. They look clean on process but are captured on outcomes.

**Q2: Where do the structural risk patterns concentrate?**
- Used five Fazekas indicators: Price Deviation, Single-Bidder Rate, Non-Open Method Share, Threshold Bunching, Supplier-Buyer Stickiness.
- **Naive Composite Fix**: Applying these metrics to tiny sample sizes (like the World Bank Tenders cell with n=2) creates false anomalies. We require a minimum threshold (15-20 tenders) to get stable rankings.
- **The Elephant**: Public Works Building and NH Department (buildings) is massive (n=877) and has a very high composite risk score (72.5). 
- **The Outlier**: Department of Cultural Affairs has a 61.0% single-bidder rate, roughly 10x the baseline.
- **Threshold Bunching**: Clear bunching (excess mass ratio ~1.7) just below the ₹1 Crore threshold.

**Q3: Does spending track geography?**
- **Procuring vs. Execution**: 35.8% of tenders map to Kamrup Metropolitan because the state-level offices are headquartered in Guwahati.
- Spending does *not* automatically track geography. We had to build a classifier to extract execution locations from tender titles to differentiate where money is spent vs. where the office sits.

**What we couldn't measure**
- The 71.4% award gap restricts full evaluation.
- The analysis is limited to a single state over three years.
- No direct linkages with demographic data (NDAP/Census) or electoral bonds cross-checks. 
- These represent fertile ground for future work.

**Reproducibility**
- Entire analysis runs on a single laptop in under 10 minutes.

---

## Chatbot Writing Prompts (Section by Section)

Copy and paste these prompts individually into your preferred LLM to generate the blog post sections according to the Karpathy pattern.

### Prompt 1: Title & Hook
```text
Write the Title and Hook (approx. 200 words) for a blog post analyzing Assam's public procurement data. 

Constraints & Context:
- Working Title: "What 17,000 Assam government tenders reveal about how India's public money is spent" (feel free to punch this up, keep it specific).
- Context: Public procurement is about 25% of India's GDP but mostly invisible. Assam publishes OCDS-format data, making it a rare window. We analyzed 3 years of post-pandemic spending (FY 2020-23).
- Focus: We asked three core questions: Who wins? Where is the risk? Does spending track geography?
- Tone: Analytical, punchy, data-journalism style.
```

### Prompt 2: The Dataset
```text
Write 'The Dataset' section (approx. 400 words). Follow the pattern: Question -> Method -> Figure placeholder -> Finding -> Caveat -> Next.

Constraints & Context:
- Dataset Stats: 21,424 tenders across 14 sheets, ~111,000 parties, ~12,000 awards.
- Key Finding: There is a 71.4% "award-publication gap." Explain why this missing data is a finding itself (it shows systemic lack of transparency post-tender). 
- Mention the inclusion of an 'awarded-vs-non-awarded chart' placeholder.
```

### Prompt 3: Q1 - Who actually wins?
```text
Write 'Q1: Who actually wins?' (approx. 1000 words). Follow the pattern: Question -> Method -> Figure placeholder -> Finding -> Caveat -> Next.

Constraints & Context:
- Methodology: We calculated HHI (Herfindahl-Hirschman Index), Gini coefficients, and ran K-Means clustering on buyers. 
- Findings: There's extreme inequality (reference a Lorenz curve and Top-20 supplier table). The biggest finding is the 4-cluster buyer typology. 
- Deep Dive: Focus heavily on the "Captured-Supplier Buyers" cluster. These buyers look competitive on paper (99% open tenders, ~5.1 bidders/tender) but are highly concentrated in outcomes (HHI is 4,533, ~5x the mainstream, and top-3 suppliers get 92% of the money). Process integrity doesn't prevent supplier capture.
- Placeholders: Add placeholders for the Lorenz curve, HHI by sector, and Top-20 supplier table. Also add a placeholder for a "10-line HHI implementation" code snippet.
```

### Prompt 4: Q2 - Where do the structural risk patterns concentrate?
```text
Write 'Q2: Where do the structural risk patterns concentrate?' (approx. 1200 words). Follow the pattern: Question -> Method -> Figure placeholder -> Finding -> Caveat -> Next.

Constraints & Context:
- Methodology: Used 5 Fazekas indicators: Price Deviation, Single-Bidder Rate, Non-Open Method Share, Threshold Bunching (especially at 1 Crore), and Stickiness. Built a composite score.
- The Methodological Trick: Explain why naive composite scores are broken. Small samples (like the World Bank Tenders cell with n=2) create massive false flags. We had to enforce a minimum threshold to fix this. Treat this as a pedagogical moment.
- Key Findings: The Department of Cultural Affairs has a massive 61% single-bidder rate. The Public Works Building and NH Department (PWD-B&NH) is the "elephant in the room" with 877 tenders and a highly elevated composite risk score.
- Placeholders: Add placeholders for 3 figures and a "percentile-rank-within-sector" code snippet.
```

### Prompt 5: Q3 - Does spending track geography?
```text
Write 'Q3: Does spending track geography?' (approx. 700 words). Follow the pattern: Question -> Method -> Figure placeholder -> Finding -> Caveat -> Next.

Constraints & Context:
- Methodology: We built a classifier to map addresses and titles to districts. 
- Finding: 35.8% of tenders map to Kamrup Metropolitan. Why? Because state-level offices in Guwahati procure for the whole state. 
- The Caveat: You cannot reliably attribute project locations based on the procuring office. We had to separate "procuring district" from "execution district" by parsing tender titles. 
- Placeholders: Add a placeholder for a Choropleth map.
```

### Prompt 6: What we couldn't measure & Reproducibility
```text
Write the final two sections: 'What we couldn't measure' (approx. 400 words) and 'Reproducibility' (approx. 200 words).

Constraints & Context:
- What we couldn't measure: Frame these as future work, not failures. We couldn't measure the 71.4% award gap, we only looked at one state, we didn't join with Census/NDAP data, and we didn't cross-check with electoral bonds.
- Reproducibility: Mention the whole pipeline ran on a single laptop in under 10 minutes end-to-end. Provide placeholders to link the GitHub repo, dashboard, and requirements file.
```

---

## Required Images List & Placement

1. **Awarded-vs-Non-Awarded Chart**: Placed in "The Dataset" section to visually demonstrate the 71.4% gap.
2. **Lorenz Curves by Sector** (`reports/figures/lorenz_by_sector.png`): Placed early in the "Q1: Who actually wins?" section.
3. **HHI by Sector and Buyer Heatmap** (`reports/figures/hhi_heatmap.png`): Placed in "Q1: Who actually wins?" to show variance.
4. **Top 20 Suppliers by Value Table/Chart** (`reports/figures/top20_suppliers_anon.png`): Placed in "Q1: Who actually wins?".
5. **Structural Risk Composite Heatmap** (`reports/figures/composite_heatmap.png`): Placed in "Q2: Where do the structural risk patterns concentrate?" to show stabilized risk rankings.
6. **Single-Bidder Rate by Sector** (`reports/figures/single_bidder_by_sector.png`): Placed in "Q2" to highlight the 61% rate in Cultural Affairs.
7. **Threshold Bunching Plot** (`reports/figures/threshold_bunching_all.png`): Placed in "Q2" to highlight the ~1.7 excess mass at the ₹1 Crore mark.
8. **Choropleth Map**: Placed in "Q3: Does spending track geography?" to visually contrast procuring vs. execution geography.
