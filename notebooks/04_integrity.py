# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Notebook 04 — Structural Integrity-Risk Analysis (Chapter B / RQ2)
#
# **Research Question:** What structural integrity indicators characterize
# Assam procurement in FY 2020–23, and which buyer × sector combinations
# show elevated composite risk scores?
#
# **Methodology:** Fazekas / Government Transparency Institute framework.
# Five indicators computed at the buyer × sector level, standardised
# within sector via percentile ranks, summed with equal weights.
# Sensitivity analysis with two alternative weightings.
#
# **Language discipline (§7.1):** "elevated structural risk indicators,"
# "patterns warranting scrutiny." Never "corrupt" or "evidence of corruption."
#
# **Selection bias caveat (§7.2):** Award-level indicators describe the
# awarded subset of tenders (~29% of all tenders in FY 2020–23).
# Selection is characterised in §1.7 of the report.

# %%
import sys, os

# Ensure we run from project root regardless of notebook location
if os.path.basename(os.getcwd()) == "notebooks":
    os.chdir("..")
sys.path.insert(0, os.getcwd())

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import seaborn as sns
from scipy import stats as sp_stats

# Project module
from src.metrics.integrity import (
    load_data,
    compute_price_deviation,
    compute_single_bidder_rate,
    compute_non_open_share,
    compute_threshold_bunching_global,
    compute_threshold_bunching_buyer,
    threshold_histogram_data,
    compute_stickiness,
    build_risk_table,
    composite_score,
    sensitivity_analysis,
    top_risk_pairings,
    case_study_cards,
    THRESHOLDS,
)

# Plotting defaults
plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 10,
})
sns.set_style("whitegrid")

FIGURES = Path("reports/figures")
FIGURES.mkdir(parents=True, exist_ok=True)

# %% [markdown]
# ## 1. Data Loading

# %%
data = load_data()

tenders = data["tenders"]
awards  = data["awards"]
merged  = data["merged"]

print(f"fact_tenders:  {len(tenders):>7,} rows")
print(f"fact_awards:   {len(awards):>7,} rows")
print(f"merged:        {len(merged):>7,} rows")
print(f"\nBid count coverage: {tenders['n_bids'].notna().sum():,} / {len(tenders):,} "
      f"({100 * tenders['n_bids'].notna().mean():.1f}%)")
print(f"Single-bid tenders (excl Single method): "
      f"{((tenders['n_bids'] == 1) & (tenders['procurement_method'] != 'Single')).sum():,}")

# %% [markdown]
# ## 2. Indicator 1 — Price Deviation from Estimate
#
# **Definition:** `(award_value − tender_value) / tender_value`, winsorised to [−2, 2].
# Median per buyer × sector. Higher deviation (less competitive discount) → higher risk.

# %%
# Clean subset for price deviation
clean = merged[
    (merged["award_value_amount"] > 1) &
    (merged["tender_value_amount"] > 0) &
    (merged["price_deviation"].notna())
].copy()
clean["price_dev_clipped"] = clean["price_deviation"].clip(-2.0, 2.0)

print(f"Price deviation clean subset: {len(clean):,} rows")
print(f"Winsorised (|dev| > 2): {(clean['price_deviation'].abs() > 2).sum():,} rows")
print(f"\nDescriptives (clipped):")
print(clean["price_dev_clipped"].describe().round(4))

# %%
fig, axes = plt.subplots(1, 2, figsize=(12, 4))

# Histogram
ax = axes[0]
ax.hist(clean["price_dev_clipped"], bins=80, color="#4C72B0", edgecolor="white", alpha=0.85)
ax.axvline(0, color="red", linestyle="--", linewidth=1, label="Zero (exact match)")
ax.axvline(clean["price_dev_clipped"].median(), color="orange", linestyle="-",
           linewidth=1.5, label=f"Median = {clean['price_dev_clipped'].median():.3f}")
ax.set_xlabel("Price Deviation (clipped to [−2, 2])")
ax.set_ylabel("Count")
ax.set_title("Distribution of Price Deviations")
ax.legend(fontsize=8)

# By sector
ax = axes[1]
sector_order = (clean.groupby("sector_name")["price_dev_clipped"]
                .median().sort_values().index.tolist())
sns.boxplot(data=clean, y="sector_name", x="price_dev_clipped",
            order=sector_order, ax=ax, palette="Blues_d", fliersize=2)
ax.axvline(0, color="red", linestyle="--", linewidth=0.8)
ax.set_xlabel("Price Deviation (clipped)")
ax.set_ylabel("")
ax.set_title("Price Deviation by Sector")

plt.tight_layout()
plt.savefig(FIGURES / "price_deviation_distribution.png")
plt.savefig(FIGURES / "price_deviation_by_sector.png")
plt.show()

# %% [markdown]
# ## 3. Indicator 2 — Single-Bidder Rate
#
# **Definition:** Share of tenders receiving exactly 1 bid (from `bids_details`),
# excluding `procurement_method = "Single"`.
#
# **Missingness:** 4,673 tenders (26.4%) have no bid records. These are excluded
# from the denominator but their count is documented per buyer × sector.
#
# **Note:** `number_of_tenderers` has min = 2 in this dataset; single-bidder
# identification is based on `staging_bids_details` counts.

# %%
single_bid = compute_single_bidder_rate(tenders)

# Global stats
total_with_bids = single_bid["total_with_bids"].sum()
total_single = single_bid["single_bidder_n"].sum()
total_no_data = single_bid["no_bid_data_count"].sum()

print(f"Tenders with bid data (excl Single method): {total_with_bids:,.0f}")
print(f"Single-bid tenders: {total_single:,.0f} ({100*total_single/total_with_bids:.1f}%)")
print(f"Tenders with no bid data: {total_no_data:,.0f}")

# %%
# By-sector single bidder rates
sector_rates = (
    tenders[tenders["procurement_method"] != "Single"]
    .assign(has_bids=lambda d: d["n_bids"].notna(),
            is_single=lambda d: d["n_bids"] == 1)
)
sector_summary = (
    sector_rates[sector_rates["has_bids"]]
    .groupby("sector_name")
    .agg(total=("is_single", "count"), single=("is_single", "sum"))
    .assign(rate=lambda d: d["single"] / d["total"])
    .sort_values("rate", ascending=False)
)

fig, ax = plt.subplots(figsize=(8, 4))
bars = ax.barh(sector_summary.index, sector_summary["rate"] * 100,
               color="#E8746D", edgecolor="white", alpha=0.85)
ax.set_xlabel("Single-Bidder Rate (%)")
ax.set_title("Single-Bidder Rate by Sector\n(excl. legitimately single-source)")
for bar, rate in zip(bars, sector_summary["rate"]):
    ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height()/2,
            f"{rate*100:.1f}%", va="center", fontsize=8)
ax.set_xlim(0, max(sector_summary["rate"]*100) * 1.15)
plt.tight_layout()
plt.savefig(FIGURES / "single_bidder_by_sector.png")
plt.show()

print("\nSingle-bidder rates by sector:")
print(sector_summary[["total", "single", "rate"]].to_string())

# %% [markdown]
# ## 4. Indicator 3 — Non-Open Procurement Method Share
#
# **Definition:** Share of tenders using methods other than "Open Tender"
# in a buyer's portfolio.
#
# 98.2% of tenders use "Open Tender," so this indicator has low variance
# but may highlight specific buyers with concentrated use of Limited /
# Single / other methods.

# %%
method_dist = tenders["procurement_method"].value_counts()
print("Procurement method distribution:")
for m, n in method_dist.items():
    print(f"  {m:20s} {n:>6,}  ({100*n/len(tenders):.1f}%)")

# %%
non_open = compute_non_open_share(tenders)
non_open_nonzero = non_open[non_open["non_open_share"] > 0].sort_values(
    "non_open_share", ascending=False
)

print(f"\nBuyer × sector groups with non-zero non-open share: {len(non_open_nonzero)}")
print(f"Top-10:")
top10_no = non_open_nonzero.merge(
    tenders[["buyer_id", "buyer_name"]].drop_duplicates(),
    on="buyer_id", how="left"
).merge(
    tenders[["sector_id", "sector_name"]].drop_duplicates(),
    on="sector_id", how="left"
).head(10)
for _, r in top10_no.iterrows():
    print(f"  {r['buyer_name'][:45]:45s} × {r['sector_name']:20s}  "
          f"{r['non_open_share']*100:5.1f}%  ({r['non_open_count']:.0f}/{r['total_tenders']:.0f})")

# %% [markdown]
# ## 5. Indicator 4 — Threshold Bunching
#
# **Definition:** Excess mass of tender values in the 5L bin just below
# key procurement thresholds (₹25 Lakh, ₹1 Crore, ₹10 Crore).
#
# **Counterfactual:** Observed density in [T − 5L, T) vs. average density
# in surrounding bins [T − 15L, T − 5L) ∪ [T, T + 10L).
#
# **Caveat (§7.6):** Bunching may reflect genuine project sizing,
# not threshold evasion. Evidence is suggestive only.

# %%
# Global excess-mass ratios
bunching_global = compute_threshold_bunching_global(tenders)

print("Global Threshold Bunching Analysis:")
print(f"{'Threshold':>10s}  {'Below bin':>10s}  {'Surround avg':>12s}  {'Ratio':>8s}  {'Signal':>10s}")
print("-" * 60)
for label, info in bunching_global.items():
    signal = ("⚠ Elevated" if info["excess_ratio"] > 1.3
              else "Normal" if info["excess_ratio"] < 0.8
              else "Marginal")
    print(f"  ₹{label:>6s}  {info['below_count']:>10d}  {info['surround_avg_count']:>12.1f}  "
          f"{info['excess_ratio']:>8.3f}  {signal:>10s}")

# %%
# Fine-grained histograms around each threshold
fig, axes = plt.subplots(1, 3, figsize=(15, 4))

for idx, (label, T) in enumerate(THRESHOLDS.items()):
    hist_data = threshold_histogram_data(tenders, label, bin_width=100_000)
    ax = axes[idx]

    colors = ["#E8746D" if jb else "#4C72B0"
              for jb in hist_data["is_just_below"]]

    ax.bar(hist_data["bin_lo"] / 1e5, hist_data["count"],
           width=0.9, color=colors, edgecolor="white", alpha=0.85)
    ax.axvline(T / 1e5, color="red", linestyle="--", linewidth=1.5,
               label=f"Threshold: ₹{label}")
    ax.set_xlabel("Tender Value (₹ Lakh)")
    ax.set_ylabel("Count")
    ax.set_title(f"Bunching Around ₹{label}")
    ax.legend(fontsize=7)

plt.tight_layout()
plt.savefig(FIGURES / "threshold_bunching_all.png")
plt.show()

# Individual threshold figures
for label in THRESHOLDS:
    fig, ax = plt.subplots(figsize=(8, 4))
    T = THRESHOLDS[label]
    hist_data = threshold_histogram_data(tenders, label, bin_width=100_000)

    colors = ["#E8746D" if jb else "#4C72B0"
              for jb in hist_data["is_just_below"]]
    ax.bar(hist_data["bin_lo"] / 1e5, hist_data["count"],
           width=0.9, color=colors, edgecolor="white", alpha=0.85)
    ax.axvline(T / 1e5, color="red", linestyle="--", linewidth=1.5,
               label=f"Threshold: ₹{label}")
    ax.set_xlabel("Tender Value (₹ Lakh)")
    ax.set_ylabel("Count")
    ax.set_title(f"Tender Value Distribution Around ₹{label} Threshold\n"
                 f"(Red bins = 5L just below threshold)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(FIGURES / f"threshold_bunching_{label}.png")
    plt.show()

# %% [markdown]
# ## 6. Indicator 5 — Supplier-Buyer Stickiness
#
# **Definition:** Percentage of a buyer's total award value (per sector)
# going to its top-3 suppliers in the FY 2020–23 window.
#
# **Note:** Buyer × sector groups with ≤ 3 suppliers mechanically
# have stickiness = 100%.

# %%
stickiness = compute_stickiness(merged)

print(f"Stickiness: {len(stickiness)} buyer × sector groups")
print(f"  Mean:   {stickiness['stickiness_top3'].mean():.3f}")
print(f"  Median: {stickiness['stickiness_top3'].median():.3f}")
print(f"  Groups with = 100%: {(stickiness['stickiness_top3'] == 1.0).sum()}")
print(f"  Groups with ≤ 3 suppliers: {(stickiness['n_suppliers'] <= 3).sum()}")

# %%
fig, axes = plt.subplots(1, 2, figsize=(12, 4))

ax = axes[0]
ax.hist(stickiness["stickiness_top3"], bins=40, color="#55A868",
        edgecolor="white", alpha=0.85)
ax.axvline(stickiness["stickiness_top3"].median(), color="orange", linestyle="-",
           linewidth=1.5, label=f"Median = {stickiness['stickiness_top3'].median():.2f}")
ax.set_xlabel("Top-3 Supplier Share")
ax.set_ylabel("Count")
ax.set_title("Distribution of Supplier-Buyer Stickiness")
ax.legend(fontsize=8)

# Only groups with > 3 suppliers (non-mechanical)
non_mech = stickiness[stickiness["n_suppliers"] > 3]
ax = axes[1]
ax.hist(non_mech["stickiness_top3"], bins=30, color="#55A868",
        edgecolor="white", alpha=0.85)
ax.axvline(non_mech["stickiness_top3"].median(), color="orange", linestyle="-",
           linewidth=1.5, label=f"Median = {non_mech['stickiness_top3'].median():.2f}")
ax.set_xlabel("Top-3 Supplier Share")
ax.set_ylabel("Count")
ax.set_title("Stickiness (groups with > 3 suppliers only)")
ax.legend(fontsize=8)

plt.tight_layout()
plt.savefig(FIGURES / "stickiness_distribution.png")
plt.show()

# %% [markdown]
# ## 7. Composite Scoring and Sensitivity Analysis
#
# **Method:** Each indicator is percentile-ranked within sector (0–100).
# Equal-weight composite = mean of 5 percentile ranks.
# Two sensitivity variants: price deviation 2× weight, single-bidder 2× weight.

# %%
tables = build_risk_table(data)
risk_df = tables["domestic"]
external_df = tables["external"]

print(f"Risk table (Domestic): {len(risk_df)} buyer × sector combinations")
print(f"  With valid composite_equal: {risk_df['composite_equal'].notna().sum()}")
print(f"Risk table (External): {len(external_df)} buyer × sector combinations")

risk_df[["price_dev_median", "single_bidder_rate", "non_open_share",
         "bunching_composite", "stickiness_top3", "composite_equal",
         "composite_pricedev2x", "composite_singlebid2x"]].describe().round(4)

# %%
# Sensitivity analysis
sa = sensitivity_analysis(risk_df)

print("Sensitivity Analysis — Spearman Rank Correlations:")
print(f"  Equal vs PriceDev 2×:  ρ = {sa['rho_pricedev2x']:.4f}  "
      f"(p = {sa['pval_pricedev2x']:.2e})")
print(f"  Equal vs SingleBid 2×: ρ = {sa['rho_singlebid2x']:.4f}  "
      f"(p = {sa['pval_singlebid2x']:.2e})")
print(f"  N valid groups: {sa['n_valid']}")

stability = "stable" if min(sa["rho_pricedev2x"], sa["rho_singlebid2x"]) > 0.85 else "sensitive"
print(f"\n  ⇒ Rankings are {stability} across weighting schemes "
      f"(threshold: ρ > 0.85)")

# %%
# Scatter: equal vs alternatives
valid = risk_df.dropna(subset=["composite_equal", "composite_pricedev2x", "composite_singlebid2x"])

fig, axes = plt.subplots(1, 2, figsize=(12, 5))

ax = axes[0]
ax.scatter(valid["composite_equal"], valid["composite_pricedev2x"],
           alpha=0.5, s=20, color="#4C72B0")
ax.plot([0, 100], [0, 100], "r--", linewidth=0.8, alpha=0.5)
ax.set_xlabel("Composite (Equal Weight)")
ax.set_ylabel("Composite (Price Dev 2×)")
ax.set_title(f"Sensitivity: Price Deviation 2× Weight\nρ = {sa['rho_pricedev2x']:.3f}")

ax = axes[1]
ax.scatter(valid["composite_equal"], valid["composite_singlebid2x"],
           alpha=0.5, s=20, color="#E8746D")
ax.plot([0, 100], [0, 100], "r--", linewidth=0.8, alpha=0.5)
ax.set_xlabel("Composite (Equal Weight)")
ax.set_ylabel("Composite (Single-Bidder 2×)")
ax.set_title(f"Sensitivity: Single-Bidder 2× Weight\nρ = {sa['rho_singlebid2x']:.3f}")

plt.tight_layout()
plt.savefig(FIGURES / "sensitivity_scatter.png")
plt.show()

# %% [markdown]
# ## 8. Top-20 Risk Pairings and Case-Study Cards

# %%
top20 = top_risk_pairings(risk_df, n=20)

print("Top-20 Buyer × Sector Risk Pairings (Composite Equal Weight)")
print("=" * 100)
for i, row in top20.iterrows():
    print(f"\n{i+1:>2d}. {row['buyer_name']}")
    print(f"    Sector: {row['sector_name']}  |  Score: {row['composite_equal']:.1f}")
    print(f"    Price Dev: {row['price_dev_median']:.4f}" if pd.notna(row["price_dev_median"]) else "    Price Dev: N/A", end="")
    print(f"  |  Single Bid: {row['single_bidder_rate']:.3f}" if pd.notna(row["single_bidder_rate"]) else "  |  Single Bid: N/A", end="")
    print(f"  |  Non-Open: {row['non_open_share']:.3f}" if pd.notna(row["non_open_share"]) else "  |  Non-Open: N/A", end="")
    print(f"  |  Bunching: {row['bunching_composite']:.4f}" if pd.notna(row["bunching_composite"]) else "  |  Bunching: N/A", end="")
    print(f"  |  Stickiness: {row['stickiness_top3']:.3f}" if pd.notna(row["stickiness_top3"]) else "  |  Stickiness: N/A")

# %%
# Case-study cards
cards = case_study_cards(top20, merged, tenders)

for i, card in enumerate(cards[:10]):
    print(f"\n{'='*80}")
    print(f"CASE-STUDY CARD #{i+1}")
    print(f"{'='*80}")
    print(f"Buyer:   {card['buyer_name']}")
    print(f"Sector:  {card['sector_name']}")
    print(f"Tenders: {card['n_tenders']:,}  |  Awards: {card['n_awards']:,}")
    print(f"\nIndicators:")
    print(f"  Price Deviation (median): {card['price_dev_median']}")
    print(f"  Single-Bidder Rate:       {card['single_bidder_rate']}")
    print(f"  Non-Open Share:           {card['non_open_share']}")
    print(f"  Bunching Composite:       {card['bunching_composite']}")
    print(f"  Stickiness (top-3):       {card['stickiness_top3']}")
    print(f"\nComposite Scores:")
    print(f"  Equal weight:     {card['composite_equal']}")
    print(f"  Price Dev 2×:     {card['composite_pricedev2x']}")
    print(f"  Single-Bidder 2×: {card['composite_singlebid2x']}")
    print(f"\nExample Tender Titles:")
    for title in card["example_titles"]:
        print(f"  • {title[:120]}")

# %% [markdown]
# ## 9. Composite Risk Heatmap

# %%
# Heatmap: sector × buyer (top-25 buyers by max composite score)
top_buyers = (
    risk_df.groupby("buyer_name")["composite_equal"]
    .max()
    .nlargest(25)
    .index.tolist()
)

heatmap_data = (
    risk_df[risk_df["buyer_name"].isin(top_buyers)]
    .pivot_table(index="buyer_name", columns="sector_name",
                 values="composite_equal", aggfunc="first")
)

# Shorten buyer names for display
heatmap_data.index = [n[:45] for n in heatmap_data.index]

fig, ax = plt.subplots(figsize=(12, 10))
sns.heatmap(heatmap_data, cmap="YlOrRd", annot=True, fmt=".0f",
            linewidths=0.5, ax=ax, cbar_kws={"label": "Composite Risk Score"},
            mask=heatmap_data.isna())
ax.set_title("Structural Risk Heatmap — Top-25 Buyers × Sector\n"
             "(Higher = more elevated structural risk indicators)",
             fontsize=12)
ax.set_ylabel("")
plt.tight_layout()
plt.savefig(FIGURES / "composite_heatmap.png")
plt.show()

# %% [markdown]
# ## 10. Export Risk Table

# %%
import os
print("CWD BEFORE EXPORT:", os.getcwd())

# Save full risk tables
risk_df.to_csv("reports/buyer_sector_risk_domestic.csv", index=False)
external_df.to_csv("reports/buyer_sector_risk_external.csv", index=False)
print(f"Exported buyer_sector_risk_domestic.csv: {len(risk_df)} rows")
print(f"Exported buyer_sector_risk_external.csv: {len(external_df)} rows")

# Save top-20
top20.to_csv("reports/top20_risk_pairings_domestic.csv", index=False)
top20_ext = top_risk_pairings(external_df, n=20)
top20_ext.to_csv("reports/top20_risk_pairings_external.csv", index=False)
print(f"Exported top20_risk_pairings_domestic.csv: {len(top20)} rows")
print(f"Exported top20_risk_pairings_external.csv: {len(top20_ext)} rows")

# %% [markdown]
# ## 11. Summary
#
# ### Key Findings
#
# 1. **Price deviation** median across the clean subset is negative (competitive
#    discount), but varies by sector and buyer. Certain buyer × sector groups
#    show elevated median deviation warranting scrutiny.
#
# 2. **Single-bidder rate** is ~6% globally (from bid-detail records), but
#    concentrated in specific sectors and buyers.
#
# 3. **Non-open method share** is very low overall (98.2% Open Tender) but a
#    handful of buyer × sector groups rely disproportionately on Limited or
#    other restricted methods.
#
# 4. **Threshold bunching** shows elevated excess mass below ₹1 Crore (ratio
#    ~1.7), suggesting patterns warranting further examination at that threshold.
#    The ₹25 Lakh and ₹10 Crore thresholds do not show significant bunching.
#
# 5. **Supplier-buyer stickiness** is high: median top-3 supplier share
#    is near 100%, partly driven by small buyer × sector groups with few
#    suppliers.
#
# 6. **Composite scores** are stable across weighting schemes (Spearman ρ > 0.85).
#
# ### Language Note
#
# These are *structural risk indicators*, not evidence of impropriety.
# Elevated scores identify patterns warranting scrutiny, not wrongdoing.
