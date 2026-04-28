# DSM Final Project — Context & Implementation Plan

**Purpose of this document:** Drop this into any chat (Claude, Gemini, ChatGPT) at the start of a session to bring the assistant fully up to speed on the project. It contains the problem framing, dataset facts, locked research questions, full skeleton, implementation guidance, library choices, and ready-to-use sub-prompts for delegating specific implementation tasks.

**How to use it:**
- *For a fresh chat:* paste this document, then state the specific task you want help with. The assistant will have all the context it needs.
- *For implementation work:* the section "Sub-prompts for chatbot delegation" at the bottom contains pre-written prompts for each chunk of the project. Copy the relevant block, fill in any task-specific details, paste into a chat.
- *Keep this document evergreen:* as findings emerge or scope shifts, update the relevant section so future chats inherit the latest state.

---

## 1. Project framing

### 1.1 Course context

This is a final project for a Data Science / Management course (DSM). The course brief calls for: (a) selecting a thematic problem, (b) doing exploratory data analysis primarily on NDAP (NITI Aayog National Data and Analytics Platform) datasets — supplemented with other public sources — (c) storing data in a database with a documented design, (d) applying analytical algorithms covered in class, and (e) producing evidence-based recommendations. There is no fixed page limit; the rubric rewards clarity, logical structure, and well-supported conclusions. Optional bonus credit for interactive visualizations / dashboards / LLM-agentic interfaces over the dataset.

### 1.2 Problem statement (final)

Public procurement accounts for roughly a quarter of Indian GDP. In Assam over FY 2020–21 through FY 2022–23, tendered procurement aggregated to over ₹100,000 crore across more than 17,000 tendering processes. Patterns in *how* these contracts are competed, awarded, and distributed have direct implications for fiscal efficiency, contractor market diversity, geographic equity of public investment, and the inclusiveness of post-pandemic public spending recovery.

Using the CivicDataLab Assam OCDS-mapped dataset, we examine three layers of the Assam procurement ecosystem:

1. **Concentration and competition** — how concentrated are awards across suppliers, sectors, buyers, and districts?
2. **Structural integrity indicators** — applying the Fazekas / Government Transparency Institute methodology, what red-flag patterns (price deviation from estimate, single-bidder rates, procurement-method composition, threshold bunching, supplier-buyer stickiness) characterize the dataset?
3. **Geographic / welfare overlay** — does district-level per-capita procurement spending track development indicators from NDAP and Census, and what does any misalignment suggest about resource allocation equity?

A secondary exploratory layer cross-checks top suppliers against publicly disclosed SBI Electoral Bond purchaser data.

### 1.3 Why this problem matters (for the report's intro)

- Public procurement is the largest single channel of public-money flow into private hands in India. Concentration and capture in this channel directly affect both fiscal efficiency and the fairness of economic opportunity.
- Indian procurement transparency has been historically weak. A 2024 report from the GI-ACE / FCDO research programme on India's federal procurement data found that contract-award publication is not consistently enforced and most awards are missing from public sources. State-level OCDS publication (which Assam is one of the few to do) is therefore valuable as a methodological proof-of-concept for what could be done nationally.
- Post-COVID fiscal stress concentrated public spending into a narrower window with greater discretion. Studying procurement patterns specifically in this window is independently interesting beyond the methodological exercise.

### 1.4 What was considered and dropped (for transparency)

- *Scraping GEM (Government e-Marketplace) directly:* abandoned. GEM has captchas, slow rendering, 100-result query caps, no bulk export. Even successful scraping would primarily yield common-goods procurement (stationery, IT, etc.), not infrastructure — which mismatches the original interest.
- *Scraping TendersInfo:* abandoned. Strong anti-scraping plus paywall; their entire business model is data aggregation.
- *Pan-India coverage:* abandoned in favor of single-state depth. Better to have a defensible state-level study than a half-scraped national one.
- *Central vs. state government comparison:* dropped — incoherent in a single-state dataset.
- *Urban vs. rural split as a separate axis:* folded into the geographic/welfare layer (derived from district-level Census).

### 1.5 Methodological note on reframing

Even within the chosen dataset, ~71.4% of tenders have no associated award (see Section 3 below). This appears to be a data-completeness artifact — only successfully concluded procurements are awards-published. The analysis is therefore scoped to FY 2020–21 through FY 2022–23 (where award coverage is meaningful) and the project's final framing is "post-pandemic Assam procurement under stress" rather than "seven years of Assam procurement." This is a feature, not a bug — the narrower temporal window is narratively sharper. Selection bias between awarded and non-awarded tenders is characterized explicitly in Part 1 of the report.

---

## 2. Dataset

### 2.1 Primary dataset: CivicDataLab Assam OCDS

- **Source:** [github.com/CivicDataLab/assam-tenders-data](https://github.com/CivicDataLab/assam-tenders-data), republished at [data.open-contracting.org](https://data.open-contracting.org).
- **Licence:** ODbL (data) / GPL v2 (code). Attribution required.
- **File used:** `ocds_mapped_data_fiscal_year_2016_2022_v3.xlsx`.
- **Standard:** Open Contracting Data Standard (OCDS) — international standard for procurement transparency. Each row in `main` represents a contracting process keyed by `ocid`.
- **Coverage notice:** despite the filename suggesting 2016–2022, the analytically usable window is **FY 2020–21 through FY 2022–23** because awards are essentially absent before that.

### 2.2 Sheet inventory (14 sheets)

| Sheet | Rows | Cols | Avg missing % | Role |
|---|---|---|---|---|
| `main` | 21,424 | 36 | 7.5% | Tender-level fact table; PK `ocid` / `_link` |
| `parties` | 111,206 | 6 | 13.5% | All entities (buyers, suppliers, tenderers, payers); referenced by ID |
| `tender_items` | 21,424 | 4 | 0% | One row per tender's primary item |
| `tender_items_deliveryAddresses` | 21,424 | 5 | 0% | Delivery address per item |
| `tender_participationFees` | 21,424 | 6 | 0% | EMD / fees per tender |
| `tender_milestones` | 156,170 | 6 | 0% | Process milestones (publication, opening, etc.) |
| `tender_amendments` | 7,839 | 5 | 0.8% | Tender amendments (corrigenda) |
| `tender_identifiers` | 21,424 | 4 | 0% | External IDs |
| `bids_details` | 68,358 | 5 | 0% | Bid summaries |
| `bids_details_tenderers` | 68,358 | 5 | 0% | One row per (bid, tenderer) |
| `te_it_additionalClassifications` | 850 | 4 | 0% | Additional classifications |
| `awards` | 12,305 | 7 | 0% | One row per award line; PK `_link` linked to main via `_link_main` |
| `awards_suppliers` | 12,305 | 5 | 0% | One row per (award, supplier) |
| `statistics` | 6,129 | 6 | 0% | Bid-statistic summaries per tender |

### 2.3 Key fields in `main` (most useful 36 → ~15)

| Field | Type | Coverage | Use |
|---|---|---|---|
| `_link` | int | 100% | Primary key (integer index) |
| `ocid` / `tender_id` | str | 100% | OCDS contracting process ID / human-readable tender ID |
| `tender_title` | str | 100% | Free-text title — used for sector classification |
| `tender_description` | str | 100% | Free-text description |
| `buyer_name` / `buyer_id` | str | 100%, 102 unique | Procuring department |
| `tender_procuringEntity_name` / `_id` | str | 100% / 100%, 1838 unique | Field office under buyer |
| `tender_value_amount` | float | 80.8% | Estimated tender value (INR) |
| `tender_value_currency` | str | 80.8% | Always "INR" when present |
| `tender_numberOfTenderers` | float | 66.2% | Bidder count — KEY field for competition analysis |
| `tender_procurementMethod` | str | 100%, 6 vals | Open Tender / Limited / Open Limited / Single / Global Tenders / Auction |
| `tender_mainProcurementCategory` | str | 100%, 16 vals | **NB: this is contracting mechanism, not sector — see §3.4** |
| `tender_contractType` | str | 100%, 3 vals | Tender / Rate Contract / Empanelment |
| `tender_fiscalYear` | str | 100%, 8 vals | "2020-2021", etc. |
| `tender_bidOpening_date`, `tender_tenderPeriod_*`, `tender_datePublished` | datetime | 100% | Time-series and bid-window analysis |
| `tender_bidOpening_address_streetAddress` | str | 100%, 3300 unique | Free-text — used for district extraction |

### 2.4 Key fields in `awards`

`_link`, `_link_main`, `id`, `value_amount`, `value_currency`, `contractPeriod_startDate`, `contractPeriod_durationInDays`. All 100% complete on the 12,305 rows present. `_link_main` joins to `main._link`.

### 2.5 Findings from pre-commitment data quality checks

Three sanity checks were run before locking research questions. Verbatim summary:

- **Awards join:** Referentially clean (zero orphans). 71.4% of main tenders have NO matching award. Coverage is catastrophic in FY 2016–20 (97–100% missing) and ~60–70% missing even in FY 2020–23. Multi-award tenders (~260 cases) are genuine — lot-based or framework agreements. Some empanelment/rate contracts have placeholder award values of ₹1.
- **Price deviation `(award − estimate) / estimate`:** sample size 5,150 after cleaning. Median = -5.0%, P25 = -10%, P75 = -0.01%. 85.7% below estimate, 5.6% exact match, 8.7% above. Open Tender shows the strongest competitive discount; Limited tenders show ~0% median discount. ~7 cases with |deviation| > 200% are placeholder values or order-of-magnitude data entry errors — to be excluded or winsorized. **Verdict: viable as core integrity indicator.**
- **Category sanity:** `tender_mainProcurementCategory` is a *contracting mechanism* variable (Item Rate, Lump-sum, Turn-key, Percentage, QCBS, etc.), NOT a sector. Direct sectoral analysis from this field is impossible. Title-based keyword classification IS viable — keyword counts in titles: road = 4,402; building = 1,654; school = 1,067; health = 903; water = 651; others smaller. Buyer-name mapping (PWD Roads → Roads, PHED → Water, NHM → Health) supplements titles for higher recall.

### 2.6 Selection bias and how to handle it

The 71.4% no-award rate is the single biggest methodological caveat. The plan:

1. Document explicitly in Part 1 ("Data Quality" subsection) what fraction of tenders by year/method/buyer have awards.
2. In Part 2, do a comparison-of-observables between awarded and non-awarded subsets (mean tender_value_amount, distribution of procurement methods, buyer mix). If they look similar, selection bias is mild. If they diverge, characterize the divergence and limit generalizability claims to "awarded procurements" rather than "procurements."
3. Some indicators (like single-bidder rate) can be computed on the fuller `main` dataset using `tender_numberOfTenderers`, which is 66.2% complete — those indicators have less selection bias than award-value-based indicators.

### 2.7 Secondary datasets

- **NDAP** ([ndap.niti.gov.in](https://ndap.niti.gov.in)): district-level development indicators. Specifically of interest — health outcomes (IMR, MMR, OOP health expenditure), education (literacy, school infrastructure), basic services (water access, sanitation, electrification), economic (per-capita income proxies where available). Access: web UI for browsing, API for bulk; register for an API key.
- **Census 2011 / SECC**: population, rural-urban share, district demographics. Plenty of mirrors; `census2011.co.in` is convenient but cross-check against the Office of the Registrar General of India.
- **SBI Electoral Bond data**: post-Feb 2024 SC ruling. ECI has the structured CSVs — donor list, recipient list, bond serial numbers. Used only for the exploratory RQ4 cross-check.

---

## 3. Locked research questions

**RQ1 (Primary, Concentration).** How concentrated is Assam's public procurement market in FY 2020–23, and does concentration vary systematically across derived sectors, buyer departments, and districts?

**RQ2 (Primary, Integrity).** What structural integrity indicators (price deviation from estimate, single-bidder rate, procurement-method composition, value-threshold bunching, supplier-buyer stickiness) characterize Assam procurement, and which buyer × sector combinations show elevated composite risk scores?

**RQ3 (Secondary, Welfare).** Does district-level per-capita procurement spending align with NDAP development indicators and Census demographics, and what does any misalignment suggest about resource allocation equity?

**RQ4 (Exploratory, Capture).** Among top-N Assam contractors by total award value, are there identifiable overlaps with electoral bond donor records disclosed by SBI, and what patterns (if any) warrant further scrutiny?

---

## 4. Project skeleton (locked)

### Part 1 — Problem Statement, Data, and Exploration

**1.1** Problem statement (text from §1.2 above, expanded with citations).
**1.2** Data sources, licences, and access mechanisms documented.
**1.3** OCDS schema walkthrough — relational structure with ER diagram of the 14 sheets.
**1.4** Completeness audit reproducing the pre-commitment DQ findings as the report's "Data Quality" section.
**1.5** Analysis-window justification: why FY 2020–23, with a clear statement of selection bias.
**1.6** Distributions: tender value (log-scale, threshold-aware), bidder counts, durations, procurement-method mix, top buyers, top suppliers (preview).
**1.7** Awarded vs. non-awarded tenders comparison-of-observables.
**1.8** Cleaning decisions documented (negative durations, ₹1 placeholders, |deviation| > 200% outliers).

### Part 2 — Database Design and Analysis

**2.1** Database design (PostgreSQL star schema; see §5 below).
**2.2** Derived-field construction:
  - Sector classifier (keyword + buyer-mapping hybrid).
  - District classifier (gazetteer matching on address + procuring entity).
**2.3** **Chapter A — Concentration (RQ1).** HHI by sector / buyer / district; Gini and Lorenz curves; top-N concentration ratios; bipartite buyer-supplier network with centrality and community detection; clustering of buyers into a behavioral typology.
**2.4** **Chapter B — Integrity Indicators (RQ2).** Composite score from five normalized indicators; sensitivity analysis on weights; flag-raising at the buyer × sector level.
**2.5** **Chapter C — Geographic / Welfare (RQ3).** District aggregation; choropleths; correlation and regression against NDAP / Census variables.
**2.6** **Chapter D — Electoral Bonds Cross-check (RQ4, appendix).** Top-50 supplier extraction; matching against SBI bond purchaser list; case-study writeups with caveats.

### Part 3 — Recommendations

Six recommendation categories, each grounded in a specific finding:
1. Sector-specific competition / unbundling guidelines (driven by Chapter A).
2. Buyer-level oversight triggers (driven by Chapter B).
3. Threshold-disclosure tightening (driven by Chapter B threshold bunching).
4. OCDS publication compliance (driven by 71.4% award-publication gap).
5. District-level allocation equity (driven by Chapter C).
6. Cross-cutting: extend OCDS to CPPP and GEM nationally; cite Assam as a proof-of-concept.

### Bonus components

- Streamlit dashboard with sector / buyer / district / fiscal-year filters; concentration metrics; integrity indicators; choropleths; network visualization.
- Text-to-SQL LLM agent (LangChain / LlamaIndex over PostgreSQL, read-only public schema). Natural-language questions compile to SQL.

---

## 5. Database design

### 5.1 Schema (PostgreSQL)

**Fact tables**
- `fact_tenders` — one row per tender. PK `ocid`. Includes derived `sector_id`, `district_id`. All filterable analytical fields denormalized in.
- `fact_awards` — one row per award line. PK `award_link`. FK to `fact_tenders` via `ocid`. Analytical grain for concentration work — important because lot-based tenders split value across multiple winners.
- `fact_bids` — one row per (bid, tenderer). FK to `fact_tenders`.

**Dimension tables**
- `dim_buyer` — 102 buyers; rollup hierarchy (department → ministry where derivable).
- `dim_supplier` — entity-resolved supplier list with `supplier_canonical_name` and a fuzzy-match flag.
- `dim_sector_derived` — derived sector classification table with `sector_id`, `sector_name`, `classification_method` (keyword | buyer | hybrid | manual).
- `dim_district_derived` — Assam's 35 districts plus an "Unclassified" bucket; matched against Census codes.
- `dim_procurement_method` — 6 values.
- `dim_category_mechanism` — the 16 OCDS category values, kept as contracting-mechanism dimension for use as control variable.
- `dim_date` — fiscal year, calendar year, month.

Indexes on every FK plus `fiscal_year`, `buyer_id`, `supplier_canonical_id`, `sector_id`, `district_id`. Materialized view `mv_buyer_supplier_concentration` for fast HHI lookups.

### 5.2 Why this schema

OCDS is already relationally well-designed; the fact/dim split makes the analytical queries straightforward. Award-line grain (rather than tender grain) is essential because of multi-award tenders. Derived-field tables are kept separate from raw OCDS tables so the provenance of every classification is auditable.

### 5.3 ER diagram

To be generated using `eralchemy2` or `dbml-renderer` once schema is final. Include in the report as a diagram with brief annotations.

### 5.4 Loading pipeline

Use Python with `pandas` + `sqlalchemy` to load the Excel sheets into staging tables, then run SQL transformations to build the star schema. Idempotent — re-runnable. Logged.

---

## 6. Implementation guidance

### 6.1 Core stack

- **Python 3.11+** as primary language.
- **PostgreSQL 15+** for the database.
- **Jupyter / VS Code with notebooks** for analysis.
- **Git** for version control. The repo should have a clean structure (`data/`, `notebooks/`, `src/`, `db/`, `reports/`, `dashboard/`).

### 6.2 Library choices

| Need | Library | Notes |
|---|---|---|
| Data manipulation | `pandas`, `numpy`, `polars` (optional for speed) | Polars worth it if you find pandas slow on the 156k-row milestones table |
| Excel I/O | `openpyxl` (read), `xlsxwriter` (write) | Already in pandas dependency tree |
| DB connection | `sqlalchemy` 2.x + `psycopg2-binary` | Standard |
| ORM (optional) | None — write raw SQL | Faster for analytics; sqlalchemy core is enough |
| Statistics | `scipy.stats`, `statsmodels` | OLS regression, Lorenz/Gini, distribution fitting |
| Concentration metrics | DIY (HHI, Gini are short functions) | Don't pip-install — write 5-line implementations |
| Network analysis | `networkx` | Bipartite graphs, centrality, community detection (Louvain via `python-louvain`) |
| Clustering | `scikit-learn` | KMeans, hierarchical, DBSCAN |
| Fuzzy matching | `rapidfuzz` (NOT `fuzzywuzzy`) | Faster, BSD-licensed |
| Geographic / mapping | `geopandas`, `folium`, `shapely` | District shapefiles from `gadm.org` or DataMeet |
| Visualization | `matplotlib`, `seaborn`, `plotly` | Plotly for dashboard interactivity |
| Dashboard | `streamlit` | Easiest path to a working dashboard |
| LLM agent | `langchain` + `langchain-experimental` (SQLAgent) | Or LlamaIndex; either works |
| Text classification | `scikit-learn` for TF-IDF baseline; optionally a small transformer via `sentence-transformers` | Probably overkill — keyword + buyer mapping should suffice |
| Notebook outputs | `nbconvert` to export final notebooks to HTML for the report appendix | |

### 6.3 Project structure (recommended)

```
dsm_project/
├── data/
│   ├── raw/                  # Original Excel + downloaded NDAP/Census files
│   ├── interim/              # Cleaned but pre-derivation
│   └── processed/            # Final analytical tables (mirror of DB)
├── db/
│   ├── schema.sql            # DDL
│   ├── load.py               # ETL from Excel → staging → star schema
│   └── views.sql             # Materialized views
├── src/
│   ├── classifiers/
│   │   ├── sector.py         # Keyword + buyer-mapping sector classifier
│   │   └── district.py       # Gazetteer-based district classifier
│   ├── metrics/
│   │   ├── concentration.py  # HHI, Gini, CR-N
│   │   ├── integrity.py      # Price deviation, single-bidder, etc.
│   │   └── networks.py       # Bipartite graph construction
│   ├── analysis/
│   │   ├── chapter_a_concentration.py
│   │   ├── chapter_b_integrity.py
│   │   ├── chapter_c_geographic.py
│   │   └── chapter_d_bonds.py
│   └── viz/
│       └── plots.py          # Reusable plotting helpers
├── notebooks/
│   ├── 01_eda.ipynb
│   ├── 02_data_quality.ipynb
│   ├── 03_concentration.ipynb
│   ├── 04_integrity.ipynb
│   ├── 05_geographic.ipynb
│   └── 06_bonds.ipynb
├── dashboard/
│   └── app.py                # Streamlit app
├── reports/
│   ├── final_report.md       # Master writeup (or LaTeX)
│   └── figures/              # Exported figures
├── tests/                    # Sanity checks for classifiers and metrics
├── requirements.txt
├── README.md
└── context_dsm.md            # this document
```

### 6.4 Conventions

- All amounts stored in INR (no conversion).
- Display amounts in lakhs / crores in human-facing outputs; raw INR in the database.
- Fiscal year stored as `"2020-2021"` (string) for joins; integer `fy_start = 2020` derived for sorting.
- Districts use the 2011 Census name spellings as canonical.
- Sector codes: `roads`, `bridges`, `buildings`, `schools`, `health`, `water_sanitation`, `electricity_power`, `it_computing`, `vehicles`, `other`. Hierarchy: sector → super-sector if needed.

### 6.5 Testing and validation

- Sector classifier: validate on a manually-labeled random sample of 200 tenders. Report precision/recall per sector. Target: >85% precision overall.
- District classifier: validate on a manually-labeled random sample of 100 assignments. Track unmatched-rate.
- Concentration metrics: unit test against known toy distributions (e.g., perfect equality → Gini = 0; monopoly → Gini ≈ 1, HHI = 10000).
- Integrity indicators: spot-check the top-N flagged buyers against domain knowledge (does it pass the smell test).

### 6.6 Reproducibility

- `requirements.txt` pinned. Use `pip-tools` or `uv` to manage.
- A single `make all` (or a `run.py`) target that loads → derives → analyzes → renders. Idempotent.
- Commit cleaning decisions and parameter choices in a config file (`config.yaml`).
- Keep a `decisions.md` log: every meaningful methodological choice (winsorize threshold, sector keyword list, etc.) gets one line of justification.

---

## 7. Watch-outs and methodological discipline

### 7.1 Language

Throughout the report — especially Chapter B — use:
- "Structural integrity indicators," "elevated risk score," "patterns warranting scrutiny."
NOT:
- "Corruption," "evidence of corruption," "this department is corrupt."

The Fazekas methodology produces *risk indicators*, not proof. Keep this discipline in every paragraph.

### 7.2 Selection bias

State explicitly in every chapter using award-level data: "These results describe the awarded subset of tenders, which represents X% of all tenders in the period. We characterize selection in §1.7."

### 7.3 Within-sector comparisons

Single-bidder rates and price deviation must be compared *within* sector, not across. Some sectors (specialized medical equipment, proprietary systems) have legitimate bidder scarcity. A 40% single-bidder rate in office stationery is alarming; the same number in MRI maintenance is baseline.

### 7.4 RQ4 framing

Electoral bond cross-check must be framed as exploratory. Required language: "Temporal overlap between bond purchase and contract award does not establish quid pro quo. Ownership opacity (parent-subsidiary structure, SPVs) means absence of a name match does not prove absence of a connection. We report observed overlaps as case studies for further investigation, not as findings of impropriety."

### 7.5 Causal claims

The geographic regression in Chapter C is *descriptive*, not causal. State this. Don't say "more procurement causes better health outcomes." Say "districts receiving higher per-capita procurement spending also have/lack better baseline health outcomes; this association does not establish direction."

### 7.6 Threshold-bunching analysis

Be careful about reverse causation: tenders may genuinely be sized to fit available work, not to evade thresholds. Bunching evidence is suggestive only. If you find sharp spikes, report the magnitude (excess mass below threshold vs. counterfactual smooth distribution) rather than asserting manipulation.

### 7.7 ₹1 / placeholder values

Empanelment and rate-contract tenders sometimes encode ₹1 as a placeholder for "to be determined per-call-off." Exclude these from value-based analysis (HHI, Gini, deviation) but RETAIN them for count-based analysis (single-bidder rate, repeat-award counts).

### 7.8 Negative tender period durations

Present in `tender_tenderPeriod_durationInDays` (min = -1453). Filter `where duration > 0` for any analysis using this field; report the count of dropped rows.

---

## 8. Suggested timeline (6 weeks)

| Week | Deliverables |
|---|---|
| 1 | Postgres set up; ETL pipeline loading Excel → staging → star schema; sector and district classifiers built and validated; Notebook 01 (EDA) and 02 (DQ) drafted |
| 2 | Chapter A (concentration) complete, including network analysis and clustering; Notebook 03 |
| 3 | Chapter B (integrity) complete, including composite score and sensitivity analysis; Notebook 04 |
| 4 | Chapter C (geographic) complete; NDAP API integration; Census joins; choropleths; Notebook 05 |
| 5 | Chapter D (bonds) appendix; Streamlit dashboard MVP; Notebook 06 |
| 6 | LLM Text-to-SQL agent (if time); final report writing; recommendations; polish |

If the schedule slips, drop in this order: (1) LLM agent, (2) electoral-bonds chapter, (3) network community detection. Do NOT drop the integrity chapter or the geographic chapter — they are core to differentiation.

---

## 9. Sub-prompts for chatbot delegation

Each block below is a self-contained prompt you can paste into a fresh chat (with `context_dsm.md` already loaded as context) to delegate a specific implementation task.

### 9.1 ETL: load Excel into Postgres star schema

```
Given the dataset described in Section 2 of context_dsm.md and the schema in Section 5,
write a Python ETL script (using pandas + sqlalchemy + psycopg2) that:

1. Reads `ocds_mapped_data_fiscal_year_2016_2022_v3.xlsx` and loads each of the 14
   sheets into corresponding `staging_<sheetname>` tables in Postgres (no transforms,
   just typed loads).
2. Runs SQL transformations to populate `fact_tenders`, `fact_awards`, `fact_bids`,
   and the dimension tables. Use idempotent UPSERTs. The final tables should mirror
   the schema described in Section 5.1 of context_dsm.md.
3. Logs row counts in/out of each step. Writes a load report to `db/load_report.json`.
4. Is parameterized via `config.yaml` (Postgres connection, file path, fiscal-year
   window).
5. Includes a `--dry-run` mode that validates without writing.

Constraints:
- Do not invent any fields not in the source. The 36 columns of `main` and the
  fields enumerated in Section 2.3 are authoritative.
- Award-line grain is the analytical unit for `fact_awards` — do not collapse to
  tender level.
- Negative `tender_tenderPeriod_durationInDays` should be loaded as-is; filtering
  happens at query time.
- Keep raw OCDS values intact in staging; only the fact/dim tables get cleaned values.

Deliverables: `db/load.py`, `db/schema.sql` (DDL), `config.yaml.example`, and a
`README` snippet explaining how to run.
```

### 9.2 Sector classifier

```
Build a hybrid sector classifier per Section 2.5 of context_dsm.md and the spec in
Section 6.2 (sector codes: roads, bridges, buildings, schools, health,
water_sanitation, electricity_power, it_computing, vehicles, other).

Approach:
1. Keyword matching on `tender_title` (case-insensitive, word-boundary). Use the
   keyword counts from Section 2.5 as a starting point but expand with synonyms and
   common Assamese/Hindi loanwords seen in titles (e.g., "rasta" for road, "pul"
   for bridge — verify against actual titles before adding).
2. Buyer-name mapping fallback. Build a lookup table of buyer_name -> default_sector
   using the 102 unique buyers. Examples in Section 2.5.
3. Conflict resolution: if title keyword is unambiguous, use it. If title is
   ambiguous and buyer mapping is decisive, use buyer. Otherwise mark "other".
4. Output a `dim_sector_derived` table with classification provenance:
   sector_id, sector_name, classification_method (keyword | buyer | hybrid | other).

Validate on a sample of 200 manually-labeled tenders. Print per-sector
precision/recall. If overall precision < 85% on first pass, iterate on the keyword
list before proceeding. Save the final keyword + buyer-mapping config to
`src/classifiers/sector_config.yaml` for auditability.

Deliverables: `src/classifiers/sector.py`, `src/classifiers/sector_config.yaml`,
`tests/test_sector.py`, plus a validation report Markdown.
```

### 9.3 District classifier

```
Build a gazetteer-based district classifier per Section 6.2 of context_dsm.md.

Approach:
1. Compile a gazetteer of Assam's 35 districts (use 2011 Census names as canonical;
   include common alternate spellings — e.g. "Kamrup Metropolitan" / "Kamrup Metro"
   / "Guwahati"; "Dibrugarh" / "Debrugarh"; "Karbi Anglong" / "Karbi-Anglong").
2. Match against `tender_bidOpening_address_streetAddress` (100% complete, 3,300
   unique values) and `tender_procuringEntity_name` (1,838 unique values).
3. Multi-pass: exact match first, then `rapidfuzz` partial-ratio with threshold 90.
4. Unmatched → "Unclassified" bucket; report count.
5. Output `dim_district_derived` with district_id, district_name, census_code,
   matched_via (address | entity_name | hybrid | unclassified).

Validate on 100 manually-labeled rows. Report unmatched rate; if >15%, iterate on
the gazetteer.

Note: state-level offices in Guwahati (e.g., "O/O The CE PWD Bldg Assam, Chandmari,
Ghy-3" — which is the most frequent address per the EDA) should be classified as
Kamrup Metropolitan, NOT distributed across the state. The geographic analysis
needs to acknowledge that these tenders may be procured *from* Guwahati but
*for* sites elsewhere — flag any tender where the title mentions a different
district from the address as a special case.

Deliverables: `src/classifiers/district.py`,
`src/classifiers/assam_gazetteer.yaml`, `tests/test_district.py`, validation report.
```

### 9.4 Concentration metrics (Chapter A)

```
Per Section 4 / Chapter A of context_dsm.md and watch-outs in Section 7, implement
the concentration analysis.

Requirements:
1. Load from `fact_awards` joined to `fact_tenders` and dimension tables. Scope:
   FY 2020-21 to FY 2022-23. Exclude awards with value_amount = 0 or = 1
   (placeholders) for value-based metrics; retain them for count-based.

2. Compute and tabulate:
   - HHI (Herfindahl-Hirschman Index) of supplier shares of award value, by sector
     and by buyer department. HHI = sum over suppliers of (share_i)^2, scaled to
     0-10000.
   - Gini coefficient of contract-value distribution across suppliers, overall and
     within each sector. Plot Lorenz curves.
   - Top-N concentration ratios: CR4 and CR10 by sector and buyer.

3. Build the bipartite buyer-supplier graph using `networkx`:
   - Nodes typed buyer / supplier; edge weight = total award value in the window.
   - Compute degree distribution (log-log plot).
   - Compute eigenvector and betweenness centrality on both partitions.
   - Run Louvain community detection on the projected supplier-supplier graph
     (suppliers connected if they share a buyer).
   - Save the graph as `outputs/buyer_supplier_graph.gexf` for Gephi
     visualization.

4. Cluster the 102 buyers using KMeans on a feature vector:
   [median_tender_value, mean_bidder_count, single_bidder_rate, supplier_HHI,
   procurement_method_open_share, repeat_top3_supplier_share]. Choose K via
   silhouette score (try K = 3..8). Interpret each cluster.

5. Visualizations: Lorenz curves (one panel per sector), HHI heatmap (sector x
   buyer), top-20 supplier bar chart (with anonymization toggle), network diagram
   (top-50 buyers + top-50 suppliers).

6. Methodological discipline (Sec 7 of context_dsm.md):
   - Compare within sector, not across, where possible.
   - Document selection bias.
   - Use neutral language.

Deliverables: `src/metrics/concentration.py`, `src/metrics/networks.py`,
`notebooks/03_concentration.ipynb`, exported figures in `reports/figures/`,
markdown writeup in `reports/chapter_a.md`.
```

### 9.5 Integrity indicators (Chapter B)

```
Per Section 4 / Chapter B of context_dsm.md and the Fazekas/GTI methodology
referenced there, implement the integrity-risk analysis.

Indicators (compute each at buyer x sector level for FY 2020-23):
1. Price deviation: median of (award_value - tender_value) / tender_value. Sample
   size constraints from Section 2.5 — use the 5,150-row clean subset.
   Filter: award_value > 1, tender_value > 0, |deviation| <= 2.0 (winsorize beyond).
2. Single-bidder rate: share of tenders with tender_numberOfTenderers = 1, EXCLUDING
   procurement_method = "Single" (those are legitimately single-source). Compute on
   the full main dataset (not awards) for max sample size. Document missingness
   handling: treat NaN bidder count as a separate category, do not impute.
3. Non-open method share: share of tenders using methods other than "Open Tender"
   in a buyer's portfolio.
4. Threshold bunching: histogram of `tender_value_amount` at fine binning (e.g., 1L
   bins in the 20-30L range). Compute "excess mass" below ₹25L, ₹1Cr, ₹10Cr
   thresholds. Use a McCrary-style or simpler counterfactual: compare observed mass
   in the 5L bin below threshold vs. average mass in surrounding bins. Report ratio.
5. Supplier-buyer stickiness: % of a buyer's total award value going to its top-3
   suppliers in the window.

Composite score:
- Standardize each indicator (percentile rank within sector, so within-sector
  comparison is enforced).
- Sum with equal weights.
- Sensitivity analysis: also compute with two alternative weightings (price
  deviation 2x, single-bidder 2x). Report whether buyer rankings are stable.

Output:
- A `buyer_sector_risk` table with all 5 indicators and the composite score.
- Top-20 buyer x sector risk pairings.
- For each top pairing, a "case-study card": buyer, sector, sample size,
  indicator values, and 2-3 example tender titles.

Language discipline (Section 7.1): "elevated structural risk indicators,"
"patterns warranting scrutiny," NEVER "corrupt" or "evidence of corruption."

Deliverables: `src/metrics/integrity.py`,
`notebooks/04_integrity.ipynb`, `reports/chapter_b.md`, figure exports.
```

### 9.6 Geographic and welfare overlay (Chapter C)

```
Per Section 4 / Chapter C of context_dsm.md, implement the geographic equity
analysis.

Inputs:
- `fact_awards` x `dim_district_derived` aggregations.
- NDAP API: pull district-level indicators for Assam in the FY 2020-23 window.
  Specifically request: IMR, MMR, OOP health expenditure, literacy rate,
  electrification rate, household water access, household sanitation access. If
  any are unavailable at district granularity, fall back to state-level and note.
- Census 2011: district-level population, rural population share. Also pull the
  GADM or DataMeet Assam district shapefile.

Outputs:
1. District-level table: total tender count, total tender value, total award value,
   per-capita award value (with Census population denominator). Stratified by
   fiscal year.
2. Choropleth maps:
   - Tender count density.
   - Per-capita award value.
   - Award value normalized by district HDI proxy or composite need indicator.
3. Correlation matrix between per-capita award value and NDAP indicators. Pearson
   and Spearman; flag any |r| > 0.3.
4. OLS regression: log(per_capita_award_value + 1) ~ log_population +
   rural_share + literacy + electrification + sanitation + fy_fixed_effects +
   sector_fixed_effects. Robust standard errors clustered at district level.
   Report coefficient table; interpret descriptively only.
5. A simple "underspending index": districts where per-capita value is below state
   median AND development indicators are below state median (i.e., low capacity AND
   low investment). Flag these as priority districts in recommendations.

Data discipline:
- Coverage of districts must match between procurement data and NDAP — report any
  districts present in one but not the other.
- "Unclassified" district bucket from the classifier should be reported separately,
  not silently dropped.
- Causal language is forbidden (Section 7.5). State all findings as associations.

Deliverables: `src/analysis/chapter_c_geographic.py`,
`notebooks/05_geographic.ipynb`, `reports/chapter_c.md`, choropleth PNGs and
interactive HTML maps.
```

### 9.7 Electoral bonds cross-check (Chapter D, appendix)

```
Per Section 4 / Chapter D of context_dsm.md, implement the exploratory bond
cross-check.

Inputs:
- Top 50 suppliers by total award value across FY 2020-23 from `fact_awards`.
- ECI / SBI electoral bond CSV (post-Feb 2024 SC release): purchaser names,
  amounts, dates, redemption parties.

Steps:
1. Extract top-50 supplier list with canonical names (post entity-resolution).
2. Where possible, look up corporate parents via MCA21 / OpenCorporates / Tofler
   for each top supplier. (Manual / partial — skip suppliers where it's not
   feasible.)
3. Match supplier canonical names AND parent entities against bond purchaser names
   using rapidfuzz (token_sort_ratio >= 85). Manual review of all matches.
4. For confirmed matches: report supplier, bond purchase amount and date, recipient
   party, and the supplier's Assam contracts in the relevant period.

Framing (mandatory, Section 7.4):
- Title chapter "Exploratory: Top-Supplier and Bond-Purchaser Overlap."
- Open with the caveat paragraph from Section 7.4: temporal overlap is not quid
  pro quo, ownership opacity, etc.
- Report observed overlaps as case studies; do not aggregate or rank by "risk."
- Do not name individual suppliers in the headline summary; refer to them by
  anonymized IDs (Supplier A, Supplier B) in the report body, with a separate
  appendix table mapping IDs to names. This protects the report from being
  excerpted out of context.

Deliverables: `src/analysis/chapter_d_bonds.py`,
`notebooks/06_bonds.ipynb`, `reports/chapter_d.md` (with caveat block),
appendix table of matches.
```

### 9.8 Streamlit dashboard

```
Build a Streamlit dashboard per the bonus components in Section 4 of
context_dsm.md.

Requirements:
- Connects read-only to the Postgres database.
- Sidebar filters: fiscal year (multiselect), sector (multiselect), district
  (multiselect), buyer (multiselect), procurement method (multiselect).
- Pages:
  1. Overview: KPIs (total tenders, total award value, top buyer, top supplier,
     median bidder count) responsive to filters.
  2. Concentration: HHI by sector bar chart, Lorenz curve, top-20 supplier table.
  3. Integrity: composite risk heatmap (sector x buyer), per-indicator drilldowns.
  4. Geographic: choropleth map (use folium or pydeck), per-capita value table.
  5. Network: interactive bipartite buyer-supplier graph
     (use streamlit-agraph or pyvis embed).
- Caching: `@st.cache_data` on all DB queries. TTL 1 hour.
- Performance: queries should return in <2 sec for typical filter combinations.
  Use materialized views for heavy aggregations.
- All language reflects Section 7 discipline ("structural risk," not "corruption").
- Read the `dim_*` tables for filter populations rather than hardcoding.

Deliverables: `dashboard/app.py`, `dashboard/requirements.txt`,
`dashboard/README.md` with run instructions.
```

### 9.9 LLM Text-to-SQL agent

```
Build a Text-to-SQL agent per the bonus components in Section 4 of context_dsm.md.

Stack: `langchain` with `SQLDatabaseChain` or `langchain_experimental.sql.SQLDatabase`,
backed by an OpenAI / Anthropic / Gemini LLM. The agent should:

1. Have read-only access to the Postgres database (separate user account in
   Postgres with SELECT-only grants on the public schema).
2. Be initialized with a description of the schema (sourced from
   `db/schema.sql` and a hand-written `schema_description.md` with one paragraph
   per table explaining what it represents — generate this from Section 2 and 5
   of context_dsm.md).
3. Include few-shot examples of natural-language → SQL pairs for typical
   user questions ("Which buyers have the highest single-bidder rate in
   construction?" → SQL with single_bidder_rate computation; "What are the
   top 10 suppliers in Kamrup district?" → SQL with district filter).
4. Wrap the agent in a Streamlit chat UI. Show the user the SQL the agent wrote
   before executing (transparency). Cap result rows at 200.
5. Include guardrails: reject questions that ask for personally-identifying
   information beyond what's in the dataset; reject any DDL or DML attempts
   (the read-only Postgres user enforces this at DB level too — defense in depth).

Deliverables: `dashboard/agent.py` (or a separate `agent/` directory),
`agent/schema_description.md`, `agent/few_shot_examples.yaml`,
demo screenshots in `reports/figures/`.
```

### 9.10 Final report writing

```
Using all chapter deliverables and figures, write the master report following
the locked skeleton in Section 4 of context_dsm.md.

Format: Markdown with embedded figure references. (Convert to PDF at the end via
pandoc.)

Structure exactly per Section 4. Within each chapter, structure as:
1. Question and motivation.
2. Methodology (data, indicators, formulas).
3. Findings (numbers and figures).
4. Limitations (data, methodology).
5. What it implies for recommendations.

Voice: third-person, observational, careful. Hedge appropriately
("the data suggests," "is associated with"). Never causal claims unless explicitly
warranted.

Length target: 30-50 pages including figures and appendices. Course rubric does not
fix length, prefers clarity.

Required components:
- Executive summary (1 page) with the 3-5 headline findings and 3-5 top
  recommendations.
- Data quality section (Part 1.4) reproducing the pre-commitment DQ findings.
- Methodology appendix with formulas for all metrics.
- Schema diagram and SQL DDL appendix.
- Decisions log (`decisions.md` content) appendix.
- Reproducibility section: how to re-run the analysis from scratch.

Recommendations (Part 3): each recommendation must be a single sentence stating
the action, followed by 2-3 sentences of justification linked to a specific finding
in Chapters A-C. Number them. Group by the six categories in Section 4 / Part 3.

Deliverables: `reports/final_report.md`, `reports/final_report.pdf`,
`reports/executive_summary.md`.
```

---

## 10. Reference materials and citations

For the report's bibliography:

- **OCDS standard:** Open Contracting Partnership, [standard.open-contracting.org](https://standard.open-contracting.org). The schema and semantics used throughout.
- **CivicDataLab Assam tenders:** [github.com/CivicDataLab/assam-tenders-data](https://github.com/CivicDataLab/assam-tenders-data); dataset at [data.open-contracting.org](https://data.open-contracting.org).
- **Fazekas, M., Tóth, I.J. (and various co-authors)** — methodology for structural integrity indicators in public procurement. Government Transparency Institute, [govtransparency.eu](https://govtransparency.eu). Their 2024 *Data in Brief* paper on the Global Contract-level Public Procurement Dataset is the most current methodological reference.
- **GI-ACE / FCDO 2024 report on India procurement data** — for the contextual claim about systemic publication gaps in Indian federal procurement.
- **NDAP:** [ndap.niti.gov.in](https://ndap.niti.gov.in).
- **Census 2011:** Office of the Registrar General & Census Commissioner, India.
- **SBI electoral bond data:** as released by the Election Commission of India following the Supreme Court's February 2024 ruling.
- **Indian GFR (General Financial Rules) 2017:** for procurement thresholds (₹25 lakh advertised tender threshold, etc.).

---

## 11. Project state log

This is the section that should be updated as you work, so any future chat sees current state.

**As of project lock-in (replace with current date when updating):**
- Pre-commitment DQ checks: complete.
- Research questions: locked.
- Skeleton: locked.
- Database: not yet built.
- Classifiers: not yet built.
- Chapter A: not started.
- Chapter B: not started.
- Chapter C: not started.
- Chapter D: not started.
- Dashboard: not started.
- LLM agent: not started.
- Report writing: not started.

**Open methodological questions (revisit as needed):**
- Final list of sector codes — finalize after sector classifier validation.
- Composite-score weighting scheme for Chapter B — finalize after sensitivity analysis.
- Whether to anonymize buyers / suppliers in the published report — decide before final writeup.

---

*End of context_dsm.md — when in doubt, refer back to Section 2 (data facts), Section 4 (skeleton), Section 7 (methodological discipline), and Section 9 (sub-prompts).*
