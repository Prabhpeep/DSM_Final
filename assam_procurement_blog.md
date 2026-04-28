# What Assam Government Tenders Reveal About How India's Public Money Is Spent

Every year, Indian governments spend roughly a quarter of GDP through public procurement. This data is not publicly available and is extremely fragmented, which holds the question of how it is being spent, and if it contributing to development and infrastructure of the country. Assam is one of the few states which adheres to the OCDS mapping of data, and has this information available. We took three years of post-pandemic spending, FY 2020–21 through FY 2022–23, to perform analysis on this subset of data. 

Who actually wins the contracts? Where do the structural risk patterns concentrate the statistical fingerprints of restricted competition? And does public spending track geography, or just the location of the offices signing the cheques? Overall, a small cluster of suppliers captures an outsized share, and the procurement process does not tell you that. Structural risk concentrates in specific departments, not uniformly across the system. Spending does not automatically track geography, so we had to build a classifier to figure out where money is actually going versus where it is being authorized.

The longer answers are what this post is about. And the first finding arrived before we ran a single model: **71.4% of tenders have no published award data at all.** That gap isn't a data-cleaning problem. It's a finding that reveals the logging of this data and highlights when this data was mapped. 

## The Dataset

The raw material for this analysis is Assam's e-procurement portal data, exported in OCDS
(Open Contracting Data Standard) format across 14 spreadsheet tabs covering FY 2020–21
through FY 2022–23. We performed EDA on this dataset to firstly understand the parameters,
missing values, etc in the dataset. 

**Cleaning and processing data** The dataset contains 21,424 tender records involving approximately
111,000 party entries (buyers, suppliers, and intermediaries). Each tender carries metadata
on the *procuring department, tender value, procurement method, district, and sector*. A
keyword-based classifier assigned tenders to derived sectors (buildings, roads, electricity,
water & sanitation, schools, and others) for downstream analysis.

![Awarded vs Non-Awarded Chart](figures/awarded_vs_nonaward.png)
*Figure 1: Share of tenders with and without published award data, FY 2020–23.*

**The award-publication gap.** Of the 21,424 tenders, only around 12,000 have any
published award record or that **71.4% of tenders have no award row.** This
is not a scraping failure or a formatting issue, but it means that award records exist 
on the portal when departments choose to publish them; the gap reflects inconsistent 
post-tender disclosure practice across departments and years.

It is important to distinguish tenders that have an award row and those that do not in order 
to analyse metrics such as HHI, Gini coefficients, price deviation, supplier stickiness and 
look at the *awarded subset*, not the full universe of public procurement intent. This gap is
a finding on itws own as a procurement system that routinely publishes tenders but not outcomes
 provides only half the transparency loop. Citizens, auditors, and competing suppliers can see 
 what was actually sought after; they largely cannot see who won, at what price, or whether the 
 award ever happened.

**What placeholder values tell us.** A further complication is the use of ₹0 and ₹1
as placeholder award values in empanelment and rate-contract tenders, where the actual
per-call-off value is decided later. These entries are excluded from value-based
concentration metrics to prevent distortion of results, but retained for count-based and network
analysis. The remaining analysis operates on the awarded subset with these factors taken into consideration. 

Three questions structure the rest of the post: who wins the contracts that do get awarded, 
where structural risk concentrates, and whether the geography of spending is what it appears to be.


## Q1: Who actually wins or is awarded tenders?

Public procurement systems are designed to be competitive — open tenders, 
multiple bidders, objective award criteria. So who actually ends up with the contracts, 
and how concentrated are the winnings?

### Measuring concentration

We applied three complementary metrics to the awarded subset, each capturing a different
dimension of market structure.

**Gini coefficient and Lorenz curves** measure inequality in how award value is
distributed across suppliers. A Gini of 0 means every supplier wins an equal share; a
Gini of 1 means one supplier wins everything. We computed Gini coefficients both in
aggregate and broken out by derived sector, plotting the full Lorenz curves to show the
shape of inequality and provide more insight to its magnitude.

**Herfindahl-Hirschman Index (HHI)** measures market concentration by summing the squared
market shares of all suppliers within a given buyer or sector, scaled to 0–10,000. A
score below 1,500 is conventionally competitive; above 2,500 is highly concentrated. HHI
is sensitive to the presence of dominant suppliers in a way that the Gini is not, making
the two metrics complementary. The core computation is straightforward:

```python
# HHI: sum of squared market shares, scaled to 0-10,000
def compute_hhi(values: pd.Series) -> float:
    total = values.sum()
    if total == 0:
        return 0
    shares = values / total
    return (shares ** 2).sum() * 10_000
```

**Concentration ratios (CR4, CR10)** report the combined market share of the top 4 and
top 10 suppliers, which a simpler complement to HHI that provides a simple insight into the 
value of the top suppliers and how much market share they actually occupy. 

![Lorenz Curves by Sector](figures/lorenz_by_sector.png)
*Figure 2: Lorenz curves for supplier award values by derived sector. Steeper curve = higher
inequality. The diagonal at 45 degrees represents perfect equality.*

![HHI by Sector and Buyer](figures/hhi_heatmap.png)
*Figure 3: HHI heatmap across buyer × sector combinations. The darker colour indicates a high
concentration. We can observe that many cells exceed the 2,500 "highly concentrated" threshold.*

![Top 20 Suppliers by Value](figures/top20_suppliers_anon.png)
*Figure 4: Top 20 suppliers by total award value, anonymised. The decrease from 1 to
number 20 is a steep line, which is a pattern that is consistent across sectors.*

### Interpretation of Results 

Inequality is high as seen in these these results. The Lorenz curves across all major sectors have a a sharp 
curve that is away from the diagonal, indicating that a small fraction of suppliers captures a disproportionate 
share of the award value. In several sectors, the top 10 suppliers make up for more than half of 
all procurement value. The CR4 and CR10 ratios confirm this is a consistent pattern 
across FY 2020–21 through FY 2022–23.

HHI analysis provides more depth in this analysis and shows that the concentration 
varies substantially across buyers even within the same sector, suggesting that the 
market structure is not simply a feature of sector-specific supply constraints. 
Two departments buying in the same sector can have very different HHI profiles, which 
points toward differences and dependenices on departmental procurement practices, rather 
than the market conditions. To better understand how this concentration arises, we use clustering 
to gain insight into this.

### Buyer typology: four clusters, one anomaly

To identify structural patterns in procurement behaviour, we ran K-Means clustering on
the 41 buyers with at least 30 recorded tenders. The features were: median tender value,
mean bidder count, single-bidder rate, supplier HHI, open-tender share, and repeat top-3
supplier share. The optimal cluster count was K=4, selected by silhouette score (0.55),
with a singleton guard to prevent outlier isolation from artificially inflating the score. 
The silhouette score is a metric to understand how well the data points are assigned to the 
cluster. 

The four clusters are as follows:

| Cluster | Label | n | Median tender value | Mean bidders | Supplier HHI | Top-3 share | Open tender share |
|---|---|---|---|---|---|---|---|
| 0 | Competitive Mainstream | 27 | ₹11.6M | 5.3 | 869 | 37% | 97% |
| 1 | Captured-Supplier Buyers | 10 | ₹6.4M | 5.1 | 4,533 | 92% | 99% |
| 2 | Restricted-Method Users | 3 | ₹6.9M | 4.6 | 1,103 | 48% | 76% |
| 3 | Empanelment-Driven Outlier | 1 | ₹0 | 118 | 2,263 | 80% | — |

Clusters 0, 2, and 3 give expected results, where The competitive mainstream (Cluster 0)
is the reference profile: open tenders, distributed awards, no dominant supplier.
Restricted-Method Users (Cluster 2) rely on limited or single-source procurement for
roughly one in four tenders — a rate four times the mainstream — which mechanically limits
competition. The Empanelment-Driven Outlier (Cluster 3) is the Public Health Engineering
Department, isolated because its procurement model — bulk empanelment panels rather than
individual tenders — is structurally incomparable to all other buyers. Its ₹0 median
reflects rate-contract placeholders, not genuine zero-value awards.

### The captured-supplier finding

Cluster 1 is different, and it is a significant result of this entire project.

The ten buyers in this cluster are, by every process metric, indistinguishable from the
competitive mainstream. They use open tenders 99% of the time — one percentage point
*above* the mainstream. They attract an average of 5.1 bidders per tender, essentially
identical to Cluster 0's 5.3. If you were auditing these departments on process
compliance, they would pass with high marks.

The outcomes tell a different story. Their supplier HHI is 4,533 — more than five times
the mainstream's 869, and well into the "highly concentrated" range by any standard
definition. Their top-3 suppliers capture 92% of total award value, compared to 37% in
Cluster 0. The same three or fewer suppliers keep winning, tender after tender, despite
formally competitive processes.

This pattern is consistent with incumbent advantage operating at the award stage rather
than the tendering stage. Barriers to winning are not always visible in how tenders are
structured or advertised; they can be embedded in evaluation criteria, technical
specifications, relationship capital, or information asymmetries that favour established
suppliers without producing any procedural red flag. **Process integrity does not, by
itself, prevent supplier capture.**

This is the core message of the concentration analysis, and it has direct implications for
reform. Expanding the open-tender mandate — the instinctive policy lever — would have
essentially no effect on these ten buyers, who already tender openly. The intervention
point is the award stage: how evaluations are conducted, whether shortlisting criteria are
genuinely contestable, and whether award decisions are subject to meaningful second-level
review.

### Caveats

The clustering operates on the awarded subset, not all tenders. Buyers with thin award
records may be misclassified, and the features available — while well-chosen — do not
capture all dimensions of procurement behaviour. The single-bidder rate contributed
negligibly to cluster separation because single-bidder tenders are rare in any individual
buyer's portfolio when aggregated across sectors; the typology is primarily driven by
award-outcome concentration, not tendering-process anomalies.

### What this sets up

Knowing *who* wins these awras is a starting point. The next question is whether the concentration
patterns identified here are accompanied by other structural signals such as price deviations,
threshold gaming, method substitution, which would raise the overall risk profile of
specific buyer × sector combinations. That is the work of Q2.


## Q2: Where do the structural risk patterns concentrate?

Knowing that procurement outcomes are concentrated tells us *what* the market looks like.
It does not tell us *why*, or where the system is most likely to be generating that
concentration through avoidable structural failures. For that, we need a different lens —
one that looks not at who wins, but at how the process itself behaves.

### The Fazekas framework

We adopt the structural integrity indicator methodology developed by the Government
Transparency Institute (Fazekas et al.), which identifies objective, measurable patterns
in tendering data that correlate with restricted competition. The framework does not
identify corruption — it identifies procurement environments that are *structurally
hospitable* to it. Five indicators are computed at the buyer × sector level.

**Price deviation** measures the median of `(award_value − tender_value) / tender_value`,
winsorized at [−2.0, 2.0]. In a competitive market, award values should cluster near or
below tender estimates; persistent positive deviation — paying more than estimated —
suggests weak competitive pressure at the award stage.

**Single-bidder rate** measures the share of tenders that received exactly one bid,
excluding tenders that are legitimately single-source by method. A high single-bidder
rate can reflect genuine market thinness, but it can also reflect specifications written
to exclude competitors, inadequate advertising, or intimidation of potential bidders.

**Non-open method share** measures the share of a buyer's tenders conducted through
limited, restricted, or direct-award methods rather than open tender. A high share
mechanically reduces the pool of competing suppliers.

**Threshold bunching** tests whether tender values cluster just below statutory approval
thresholds — ₹25 Lakh, ₹1 Crore, and ₹10 Crore — more than would be expected by chance.
Contract splitting to stay below oversight thresholds is a well-documented pattern in
public procurement globally.

**Supplier-buyer stickiness** measures the percentage of a buyer's total award value going
to its top-3 suppliers within a sector. High stickiness, combined with a competitive
market structure, is a red flag for incumbent lock-in.

### Building the composite — and why the naive version breaks

Each indicator is converted to a percentile rank within its sector before aggregation.
This within-sector normalisation is essential: a 20% single-bidder rate in the roads
sector and a 20% rate in a specialist equipment sector carry very different implications
if the sector baselines differ. The composite score is then the equal-weighted average of
the five percentile ranks, producing a 0–100 score.

```python
# Percentile rank within sector — the right way to normalise
def add_percentile_ranks(df: pd.DataFrame, indicators: list[str]) -> pd.DataFrame:
    for indicator in indicators:
        col = f"{indicator}_pct"
        df[col] = df.groupby("sector")[indicator].rank(pct=True) * 100
    composite_cols = [f"{ind}_pct" for ind in indicators]
    df["composite_score"] = df[composite_cols].mean(axis=1)
    return df
```

The naive version of this approach — computing composite scores without any minimum
tender threshold — produces wildly unstable rankings, and it is worth dwelling on why,
because it is a mistake that is easy to make and hard to spot.

Consider a hypothetical buyer × sector cell containing two tenders, both awarded to the
same supplier, both just below the ₹1 Crore threshold, both with a single bidder. Every
indicator fires at maximum: 100th percentile stickiness, 100th percentile
single-bidder rate, 100th percentile threshold bunching. The cell tops the risk ranking.
This is precisely what happened with the Finance Department – World Bank Tenders (other)
cell in our data, which had n=2 and scored as a top-5 risk pairing under the naive
approach.

The issue is not that the indicators are wrong — both tenders genuinely had one bidder.
The issue is that two observations cannot distinguish a structural pattern from random
noise. A cell with n=2 and a 100% single-bidder rate is statistically identical to a cell
with n=200 and a 100% single-bidder rate from a data perspective, but they have entirely
different interpretive weight.

The fix is a minimum tender threshold. We require at least 15 tenders for a cell to enter
the composite ranking. This is not an arbitrary filter — ranking stability was explicitly
tested: top-N rankings are consistent across minimum thresholds of 10, 15, and 20 tenders
(Spearman ρ > 0.89). The threshold of 15 balances stability against coverage. Small cells
are not discarded; they are simply excluded from the ranked comparison and reported
separately.

This is a general lesson for anyone building composite risk indices from administrative
data: **the denominator matters as much as the numerator.** A percentile rank is only
meaningful if it is computed over a distribution with enough mass to be stable.

![Composite Risk Heatmap](figures/composite_heatmap.png)
*Figure 5: Composite structural risk scores by buyer × sector, minimum 15 tenders.
Darker cells indicate higher composite risk. The largest cells by tender count are
labelled.*

### What the indicators show

**Single-bidder rate** produces the starkest individual finding in the dataset. Globally,
approximately 6% of tenders with bid data received exactly one bid — an already elevated
baseline. But the **Department of Cultural Affairs (other)** records a single-bidder rate
of **61.0%**, roughly ten times the global baseline. Six in every ten tenders this
department issues in the "other" category attract no competitive response at all. Whether
this reflects the specialised nature of cultural procurement, insufficient advertising, or
something more structural, it is the single most anomalous cell in the entire dataset on
this indicator.

The **Department of Housing and Urban Affairs (buildings)** also flags with a 16.7%
single-bidder rate — elevated relative to the buildings sector baseline, if less extreme.

![Single-Bidder Rate by Sector](figures/single_bidder_by_sector.png)
*Figure 6: Single-bidder rate by sector and buyer. The Department of Cultural Affairs
cell (61.0%) is a clear outlier at roughly 10× the global baseline.*

**Threshold bunching** produces a clear signal at the ₹1 Crore threshold. The excess mass
ratio — comparing the density of tender values in the bin just below ₹1 Crore against the
average of surrounding bins — is approximately 1.7, meaning the bin immediately below the
threshold is 70% denser than expected. The ₹25 Lakh and ₹10 Crore thresholds do not show
significant bunching. The ₹1 Crore threshold triggers a distinct level of administrative
oversight under domestic procurement rules; the bunching pattern is consistent with
contract sizing behaviour designed to avoid that trigger.

![Threshold Bunching](figures/threshold_bunching_all.png)
*Figure 7: Density of tender values around statutory thresholds. The ₹1 Crore threshold
shows an excess mass ratio of ~1.7. The ₹25 Lakh and ₹10 Crore thresholds are quiet.*

**Supplier-buyer stickiness** is pervasively high. The unfiltered median buyer awards 100%
of their sector value to their top-3 suppliers, but this is largely mechanical in small
portfolios — if a buyer has exactly three active suppliers, the top-3 share is 100% by
definition. Filtering strictly for cells with five or more active suppliers, the median
drops to 60.9%. Substantial concentration persists even in markets structurally capable
of broader competition.

### The two headline cells

When the composite score is applied to the minimum-15-tender subset, two cells stand out
for different reasons.

The **Department of Cultural Affairs (other)** tops the risk ranking on the back of its
61% single-bidder rate. It is the clearest single-indicator outlier in the dataset —
anomalous enough that its composite score would be elevated even if every other indicator
were at the median.

The more consequential finding is the **Public Works Building and NH Department
(buildings)**. With 877 tenders, it is by far the largest single procurement portfolio in
the dataset. Its composite risk score is 72.5 — above the within-sector median on multiple
indicators simultaneously. This is the elephant in the room: not the most extreme cell on
any single metric, but the largest fiscal footprint intersecting with persistently elevated
structural risk across the board. The Assam Power Distribution Company Ltd
(electricity_power, composite 65.6) and the Public Works Roads Department (bridges,
composite 73.2) round out the highest-impact cells by fiscal volume.

The top-5 domestic buyer × sector pairings by composite score, filtered for minimum 15
tenders, are:

1. Urban Development Department (water & sanitation)
2. Department of Cultural Affairs (other)
3. Department of Housing and Urban Affairs (buildings)
4. Elementary Education Department (schools)
5. Guwahati Municipal Corporation (buildings)

### Caveats

These are structural risk *indicators*, not evidence of impropriety. A high composite
score means a procurement environment that warrants closer scrutiny — not one where
wrongdoing has been demonstrated. The selection bias from the 71.4% award gap is
particularly relevant here: price deviation and stickiness are computed on the awarded
subset only, which may not be representative of the full procurement portfolio for any
given buyer. Departments that publish awards selectively may look better or worse than
they actually are depending on which awards they choose to disclose.

The domestic and externally-funded panels are analysed separately throughout. World Bank,
ADB, and JICA-funded tenders follow different procurement guidelines, different threshold
structures, and different statutory frameworks — ranking them against the domestic
baseline would conflate incomparable benchmarks.

### What this sets up

The concentration analysis showed *who* wins. The structural integrity analysis shows
*where* the conditions for restricted competition are most persistently present. The
remaining question is a geographic one: when money flows through these departments and
these tenders, where does it actually go?

---

## Q3: Does spending track geography?

The third question seems like it should be the easiest. Public procurement is ultimately
about building things and delivering services in specific places. A new school goes in a
district. A road connects two towns. A water sanitation project serves a block. So where
is the money actually going?

The answer, it turns out, is not straightforward — and the reasons why are as revealing
as any of the concentration findings.

### The classification problem

Assam has 35 districts. The procurement data contains addresses for procuring offices and
free-text tender titles. Neither maps cleanly to a project location without work.

We built a district classifier operating as a five-pass pipeline. The first pass performs
exact substring matching against a gazetteer of all 35 Census 2011 districts, extended
with aliases drawn from actual data patterns: Guwahati landmarks like *Bijulee Bhawan*
and *Janata Bhawan*, PWD circle abbreviations, and the newer administrative units of
Majuli and Hojai. Subsequent passes handle state headquarters fallback (mapping
centralized state-level offices to Kamrup Metropolitan), Bodoland Territorial Council
entity fallback, and entity name matching. Fuzzy matching and circle-code matching were
deliberately disabled from the default pipeline to reduce false positives at the cost of
a slightly higher unmatched rate.

Critically, the classifier produces *two separate geographic columns* for each tender:

- **Procuring district**: derived from the office address — where the department that
  issued the tender is physically located.
- **Execution district**: derived from explicit district mentions in the tender title —
  where the project is described as taking place.

A derived view, `v_district_best`, resolves these using
`COALESCE(district_execution_id, district_procuring_id)` — preferring the execution
location where it is explicitly stated, and falling back to the procuring office address
only when no execution location can be extracted.

### What the map shows

The classifier assigned procuring districts to over 90% of the dataset, well within the
15% unmatched-rate target. The distribution of those assignments is where the story is.

**35.8% of all tenders map to Kamrup Metropolitan.** Kamrup Metropolitan is the district
containing Guwahati — Assam's capital and the location of most state government
headquarters. The next largest district, Kokrajhar, accounts for 10.3%. The remaining 33
districts share the rest.

![Choropleth Map: Procurement by District](figures/choropleth_district.png)
*Figure 8: Procurement tender count by best-available district (execution where available,
procuring office otherwise). The dominance of Kamrup Metropolitan reflects centralized
state-level procurement, not a geographic concentration of project activity.*

This concentration is not evidence that a third of Assam's infrastructure spending
benefits Guwahati. It reflects the fact that state-level agencies — the National Health
Mission, the Public Works Roads Department, the Education department — are headquartered
in Guwahati and issue tenders for projects across the entire state from those offices. The
procuring office address is not the project location. It is simply where the paperwork
originates.

### Why this matters

Conflating the two creates a systematic distortion in any geographic analysis of
procurement. Choropleth maps drawn from procuring office addresses will show Guwahati
receiving a third of all tenders and most other districts appearing underserved. This
would be wrong — not because the data is bad, but because the naive geographic
attribution is answering the wrong question.

The execution district column partially corrects this. Where a tender title explicitly
names a district — "Construction of road in Sonitpur district" — the classifier extracts
that mention and assigns it as the execution location, overriding the Guwahati office
address. This dramatically reduces the noise from centralized procurement hubs for the
subset of tenders that are explicit about their project location.

### Caveats

The execution district extraction depends entirely on whether departments name districts
in their tender titles — and many do not. Generic titles like "Supply of materials" or
"Annual maintenance contract" carry no geographic signal. For these tenders, the procuring
office fallback remains the only available attribution, and the centralization bias
persists. Any choropleth drawn from this data should report the share of rows using each
source, and figure captions should note the proportion defaulting to procuring-office
fallback.

The unmatched rate of 9.7% is also worth flagging. The most common unmatched addresses
are highly generic strings — "Online", "S E, PWD (Roads), City Road Circle" — that
contain no extractable geographic signal. Further gazetteer iterations could reduce this,
but complete coverage is unlikely without structured address fields at source.

### What this sets up

Geography is the one dimension where the data's limits are most binding. We can say
where procurement is *authorized* with reasonable confidence. We can say where it
*executes* only for the subset of tenders explicit enough to tell us. Joining this data
with district-level demographic indicators — Census population, NDAP infrastructure
indices, electoral geography — would make the geographic analysis substantially more
powerful. That is work for a future iteration.

---

## What we couldn't measure

Every dataset has a boundary. These are ours — framed not as failures but as the most
productive directions for future work.

**The award-publication gap.** The 71.4% of tenders with no published award outcome are
not just missing data points — they are the most important unmeasured variable in this
entire analysis. We cannot determine whether those tenders were cancelled, awarded without
disclosure, or simply never updated on the portal. A systematic study of *which*
departments and *which* sectors drive the gap — and whether the gap correlates with the
structural risk indicators we can measure — would be the single highest-value extension
of this work. Mandatory, machine-readable award publication within a fixed window of
contract signing would also make this analysis significantly more powerful for future
years.

**One state, three years.** Assam is a useful case precisely because it publishes OCDS
data, but it is one state with specific administrative history, political economy, and
sectoral composition. The patterns identified here — captured-supplier buyers, threshold
bunching at ₹1 Crore, centralized geographic attribution — may generalise to other Indian
states, or they may be idiosyncratic to Assam. Replicating this pipeline on procurement
data from Telangana, Odisha, or Tamil Nadu would begin to answer that question. The code
is designed to be portable.

**No demographic join.** Every district-level finding in Q3 is purely administrative.
We do not know whether procurement spending in a given district correlates with population
density, poverty rates, infrastructure deficits, or development indicators. Joining the
procurement dataset with NDAP district profiles or Census 2011 data would allow a more
substantive question to be asked: is public money going where the need is greatest? That
analysis is technically straightforward given the district classifier we have built. It
simply requires the join.

**No electoral cross-check.** Procurement concentration around specific suppliers,
combined with public information on political donations and electoral bonds, would allow
a more pointed question about the political economy of supplier capture. We did not
attempt this linkage, partly because the electoral bonds data released following the
Supreme Court's 2024 order is incomplete, and partly because causal inference in this
space requires more careful design than a correlational join. It is, however, a clear
direction.

---

## Reproducibility

The analysis is implemented in Python, with dependencies limited to standard data science
libraries. There are no proprietary data sources, no paid APIs, and no infrastructure
requirements beyond a local Python environment. The input data is publicly available from
Assam's e-procurement portal in OCDS format.

- **Code**: [GitHub repository →](#)
- **Interactive dashboard**: [Explore the data →](#)
- **Dependencies**: [requirements.txt →](#)

