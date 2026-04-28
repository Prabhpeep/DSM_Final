"""
Structural integrity-risk indicators for Assam OCDS procurement (FY 2020-23).

Implements five indicators from the Fazekas / GTI methodology:
  1. Price deviation (median, buyer × sector)
  2. Single-bidder rate (from bids_details, buyer × sector)
  3. Non-open procurement method share (buyer × sector)
  4. Threshold bunching (excess-mass ratios below ₹25L, ₹1Cr, ₹10Cr)
  5. Supplier-buyer stickiness (top-3 supplier share of award value)

Plus composite scoring with equal and alternative weightings, and
sensitivity analysis (Spearman ρ) across weighting schemes.

Language discipline (context_dsm.md §7.1): all outputs use
"elevated structural risk indicators" / "patterns warranting scrutiny."
Never "corrupt" or "evidence of corruption."

Run standalone for a quick sanity check:
    python src/metrics/integrity.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_PATH = Path("db/dsm.sqlite")
FY_SCOPE = ("2020-2021", "2021-2022", "2022-2023")

# Price-deviation winsorize bounds (per §2.5)
PRICE_DEV_CLIP_LO = -2.0
PRICE_DEV_CLIP_HI = 2.0

# Minimum sample sizes per buyer × sector group
MIN_AWARDS_PRICE_DEV = 3
MIN_TENDERS_SINGLE_BID = 5
MIN_TENDERS_FOR_COMPOSITE = 15

# Threshold bunching thresholds (INR)
THRESHOLDS = {
    "25L": 2_500_000,
    "1Cr": 10_000_000,
    "10Cr": 100_000_000,
}
# Bin width for excess-mass calculation (5 Lakh = 500,000)
BUNCHING_BIN_WIDTH = 500_000


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_data(db_path: Path = DB_PATH) -> dict[str, pd.DataFrame]:
    """Load all tables needed for integrity analysis.

    Returns dict with keys:
        tenders   — fact_tenders + dim_buyer + dim_sector
        awards    — fact_awards + supplier name
        bid_counts — per-tender bid count from staging_bids_details
        merged    — tenders LEFT JOIN awards (tender-award grain)
    """
    conn = sqlite3.connect(db_path)

    tenders = pd.read_sql("""
        SELECT ft.*, db.buyer_name, ds.sector_name
        FROM   fact_tenders ft
        LEFT JOIN dim_buyer  db ON ft.buyer_id  = db.buyer_id
        LEFT JOIN dim_sector ds ON ft.sector_id = ds.sector_id
    """, conn)

    awards = pd.read_sql("""
        SELECT fa.*, ds.supplier_name
        FROM   fact_awards fa
        LEFT JOIN dim_supplier ds
            ON fa.supplier_canonical_id = ds.supplier_canonical_id
    """, conn)

    # Derive per-tender bid count from staging_bids_details.
    # number_of_tenderers in fact_tenders has min=2 (never 1), so we use
    # bids_details as the authoritative source for single-bidder detection.
    bid_counts = pd.read_sql("""
        SELECT _link_main, COUNT(*) AS n_bids
        FROM   staging_bids_details
        GROUP BY _link_main
    """, conn)

    # Map _link_main back to ocid via staging_main
    link_to_ocid = pd.read_sql("""
        SELECT _link, ocid FROM staging_main
        WHERE  tender_fiscalYear IN ('2020-2021','2021-2022','2022-2023')
    """, conn)
    bid_counts = bid_counts.merge(
        link_to_ocid, left_on="_link_main", right_on="_link", how="inner"
    )[["ocid", "n_bids"]]

    conn.close()

    # Merge tenders with bid counts
    tenders = tenders.merge(bid_counts, on="ocid", how="left")

    # Merge tenders with awards (tender-award grain)
    merged = tenders.merge(awards, on="ocid", how="left", suffixes=("", "_award"))

    # Create is_externally_funded flag
    tenders["is_externally_funded"] = tenders["buyer_name"].str.contains(
        r"World Bank|ADB|JICA|Externally Aided|Externally Funded|External Aid|EAP",
        case=False, na=False, regex=True
    )

    return {
        "tenders": tenders,
        "awards": awards,
        "bid_counts": bid_counts,
        "merged": merged,
    }


# ---------------------------------------------------------------------------
# Indicator 1: Price Deviation
# ---------------------------------------------------------------------------
def compute_price_deviation(merged: pd.DataFrame) -> pd.DataFrame:
    """Median price deviation per buyer × sector.

    Filters:
      - award_value_amount > 1 (exclude ₹1 placeholders)
      - tender_value_amount > 0
      - price_deviation not null
      - Winsorize |deviation| to [-2.0, 2.0]

    Returns DataFrame with columns:
      buyer_id, sector_id, price_dev_median, price_dev_p25, price_dev_p75,
      price_dev_n (sample size)
    """
    df = merged[
        (merged["award_value_amount"] > 1)
        & (merged["tender_value_amount"] > 0)
        & (merged["price_deviation"].notna())
    ].copy()

    # Winsorize
    df["price_dev_clipped"] = df["price_deviation"].clip(
        lower=PRICE_DEV_CLIP_LO, upper=PRICE_DEV_CLIP_HI
    )

    agg = (
        df.groupby(["buyer_id", "sector_id"])["price_dev_clipped"]
        .agg(
            price_dev_median="median",
            price_dev_p25=lambda x: x.quantile(0.25),
            price_dev_p75=lambda x: x.quantile(0.75),
            price_dev_n="count",
        )
        .reset_index()
    )

    # Mark groups below minimum sample
    agg.loc[agg["price_dev_n"] < MIN_AWARDS_PRICE_DEV, "price_dev_median"] = np.nan

    return agg


# ---------------------------------------------------------------------------
# Indicator 2: Single-Bidder Rate
# ---------------------------------------------------------------------------
def compute_single_bidder_rate(tenders: pd.DataFrame) -> pd.DataFrame:
    """Share of tenders receiving exactly 1 bid, per buyer × sector.

    Uses n_bids derived from staging_bids_details.
    Excludes procurement_method = "Single" (legitimately single-source).
    Tenders with no bid data (n_bids NaN) are excluded from the
    denominator but their count is reported separately.

    Returns DataFrame with columns:
      buyer_id, sector_id, single_bidder_rate, single_bidder_n,
      total_with_bids, no_bid_data_count
    """
    df = tenders[tenders["procurement_method"] != "Single"].copy()

    def _agg(g: pd.DataFrame) -> pd.Series:
        has_bids = g["n_bids"].notna()
        with_bids = g[has_bids]
        n_single = (with_bids["n_bids"] == 1).sum()
        n_with_bids = len(with_bids)
        n_no_data = (~has_bids).sum()

        rate = n_single / n_with_bids if n_with_bids >= MIN_TENDERS_SINGLE_BID else np.nan

        return pd.Series({
            "single_bidder_rate": rate,
            "single_bidder_n": n_single,
            "total_with_bids": n_with_bids,
            "no_bid_data_count": n_no_data,
        })

    result = df.groupby(["buyer_id", "sector_id"]).apply(_agg, include_groups=False).reset_index()
    return result


# ---------------------------------------------------------------------------
# Indicator 3: Non-Open Method Share
# ---------------------------------------------------------------------------
def compute_non_open_share(tenders: pd.DataFrame) -> pd.DataFrame:
    """Share of tenders using methods other than 'Open Tender',
    per buyer × sector.

    Returns DataFrame with columns:
      buyer_id, sector_id, non_open_share, non_open_count, total_tenders
    """
    def _agg(g: pd.DataFrame) -> pd.Series:
        total = len(g)
        non_open = (g["procurement_method"] != "Open Tender").sum()
        share = non_open / total if total >= 5 else np.nan
        if non_open < 2:
            share = np.nan
        return pd.Series({
            "non_open_share": share,
            "non_open_count": non_open,
            "total_tenders": total,
        })

    result = tenders.groupby(["buyer_id", "sector_id"]).apply(_agg, include_groups=False).reset_index()
    return result


# ---------------------------------------------------------------------------
# Indicator 4: Threshold Bunching
# ---------------------------------------------------------------------------
def compute_threshold_bunching_global(
    tenders: pd.DataFrame,
) -> dict[str, dict]:
    """Compute excess-mass ratios at each threshold globally.

    For each threshold T, compare density in the 5L bin just below
    [T - 5L, T) vs. average density in surrounding bins
    [T - 15L, T - 5L) ∪ [T, T + 10L).

    Returns dict keyed by threshold label with:
        below_count, surround_avg_count, excess_ratio, threshold_inr
    """
    df = tenders[
        (tenders["tender_value_amount"].notna())
        & (tenders["tender_value_amount"] > 0)
    ].copy()

    values = df["tender_value_amount"].values
    results = {}

    for label, T in THRESHOLDS.items():
        bin_5L = 500_000  # 5 Lakh

        # Below bin: [T - 5L, T)
        below_count = np.sum((values >= T - bin_5L) & (values < T))

        # Surrounding bins: [T - 15L, T - 5L) and [T, T + 10L)
        surround_lo = np.sum((values >= T - 3 * bin_5L) & (values < T - bin_5L))
        surround_hi = np.sum((values >= T) & (values < T + 2 * bin_5L))

        # Average per 5L bin: surround has 2+2 = 4 bins of 5L each
        surround_total = surround_lo + surround_hi
        surround_avg = surround_total / 4.0 if surround_total > 0 else 0

        excess_ratio = below_count / surround_avg if surround_avg > 0 else np.nan

        results[label] = {
            "threshold_inr": T,
            "below_count": int(below_count),
            "surround_avg_count": round(surround_avg, 1),
            "excess_ratio": round(excess_ratio, 3),
        }

    return results


def compute_threshold_bunching_buyer(
    tenders: pd.DataFrame,
) -> pd.DataFrame:
    """Per buyer × sector: fraction of tenders in 'just-below' bins.

    For each threshold, compute the share of a buyer×sector's tenders
    that fall in [T - 5L, T).

    Returns DataFrame with columns:
        buyer_id, sector_id, bunching_25L, bunching_1Cr, bunching_10Cr,
        bunching_composite
    """
    df = tenders[
        (tenders["tender_value_amount"].notna())
        & (tenders["tender_value_amount"] > 0)
    ].copy()

    bin_5L = 500_000

    for label, T in THRESHOLDS.items():
        df[f"below_{label}"] = (
            (df["tender_value_amount"] >= T - bin_5L)
            & (df["tender_value_amount"] < T)
        ).astype(int)

    agg = (
        df.groupby(["buyer_id", "sector_id"])
        .agg(
            bunching_25L=("below_25L", "mean"),
            bunching_1Cr=("below_1Cr", "mean"),
            bunching_10Cr=("below_10Cr", "mean"),
            bunching_n=("tender_value_amount", "count"),
        )
        .reset_index()
    )

    # Composite bunching: average of the three rates
    agg["bunching_composite"] = agg[
        ["bunching_25L", "bunching_1Cr", "bunching_10Cr"]
    ].mean(axis=1)

    return agg


def threshold_histogram_data(
    tenders: pd.DataFrame,
    threshold_label: str,
    bin_width: int = 100_000,  # 1 Lakh default for visualization
) -> pd.DataFrame:
    """Return histogram bin data around a threshold for plotting.

    Generates bins from T - 15L to T + 10L.
    """
    T = THRESHOLDS[threshold_label]
    lo = T - 15 * 100_000  # 15L below
    hi = T + 10 * 100_000  # 10L above

    df = tenders[
        (tenders["tender_value_amount"].notna())
        & (tenders["tender_value_amount"] >= lo)
        & (tenders["tender_value_amount"] <= hi)
    ].copy()

    bins = np.arange(lo, hi + bin_width, bin_width)
    df["bin"] = pd.cut(
        df["tender_value_amount"], bins=bins, right=False, include_lowest=True
    )
    counts = df.groupby("bin", observed=True).size().reset_index(name="count")
    counts["bin_lo"] = [float(x.left) for x in counts["bin"]]
    counts["bin_hi"] = [float(x.right) for x in counts["bin"]]
    counts["is_below_threshold"] = counts["bin_hi"] <= T
    counts["is_just_below"] = (counts["bin_lo"] >= T - 5 * 100_000) & (
        counts["bin_hi"] <= T
    )

    return counts


# ---------------------------------------------------------------------------
# Indicator 5: Supplier-Buyer Stickiness
# ---------------------------------------------------------------------------
def compute_stickiness(merged: pd.DataFrame) -> pd.DataFrame:
    """% of a buyer's award value going to top-3 suppliers, per buyer × sector.

    Filters: award_value_amount > 1 (exclude placeholders).

    Returns DataFrame with columns:
        buyer_id, sector_id, stickiness_top3, total_award_value,
        n_suppliers, top3_value
    """
    df = merged[
        (merged["award_value_amount"] > 10000)
        & (merged["supplier_canonical_id"].notna())
    ].copy()

    def _agg(g: pd.DataFrame) -> pd.Series:
        supplier_totals = (
            g.groupby("supplier_canonical_id")["award_value_amount"]
            .sum()
            .sort_values(ascending=False)
        )
        total_val = supplier_totals.sum()
        top3_val = supplier_totals.head(3).sum()
        n_suppliers = len(supplier_totals)
        stickiness = top3_val / total_val if total_val > 0 and n_suppliers >= 5 else np.nan

        return pd.Series({
            "stickiness_top3": stickiness,
            "total_award_value": total_val,
            "n_suppliers": n_suppliers,
            "top3_value": top3_val,
        })

    result = df.groupby(["buyer_id", "sector_id"]).apply(_agg, include_groups=False).reset_index()
    return result


# ---------------------------------------------------------------------------
# Composite Score
# ---------------------------------------------------------------------------
def _percentile_rank_within_sector(
    df: pd.DataFrame, col: str
) -> pd.Series:
    """Compute percentile rank of `col` within each sector_id group.

    Higher raw value → higher percentile (i.e., higher risk).
    NaN inputs → NaN output.
    """
    return df.groupby("sector_id")[col].rank(pct=True, na_option="keep") * 100


def composite_score(
    risk_df: pd.DataFrame,
) -> pd.DataFrame:
    """Add composite scores (equal weight + two sensitivity variants).

    Input must have columns:
        buyer_id, sector_id, price_dev_median, single_bidder_rate,
        non_open_share, bunching_composite, stickiness_top3

    Adds columns:
        pctile_price_dev, pctile_single_bidder, pctile_non_open,
        pctile_bunching, pctile_stickiness,
        composite_equal, composite_pricedev2x, composite_singlebid2x

    Returns enriched DataFrame.
    """
    df = risk_df.copy()

    # For price deviation: more negative = more competitive discount = LOWER risk.
    # We want higher deviation (less discount / premium) = higher risk.
    # So we rank price_dev_median directly (higher median → higher percentile).
    indicator_cols = [
        ("price_dev_median", "pctile_price_dev"),
        ("single_bidder_rate", "pctile_single_bidder"),
        ("non_open_share", "pctile_non_open"),
        ("bunching_composite", "pctile_bunching"),
        ("stickiness_top3", "pctile_stickiness"),
    ]

    pctile_cols = []
    for raw_col, pctile_col in indicator_cols:
        df[pctile_col] = _percentile_rank_within_sector(df, raw_col)
        pctile_cols.append(pctile_col)

    # Equal weights
    df["composite_equal"] = df[pctile_cols].mean(axis=1)

    # Sensitivity A: price deviation 2× weight
    weights_a = np.array([2, 1, 1, 1, 1], dtype=float)
    weights_a /= weights_a.sum()
    df["composite_pricedev2x"] = (
        df[pctile_cols].values * weights_a[np.newaxis, :]
    ).sum(axis=1)

    # Sensitivity B: single-bidder 2× weight
    weights_b = np.array([1, 2, 1, 1, 1], dtype=float)
    weights_b /= weights_b.sum()
    df["composite_singlebid2x"] = (
        df[pctile_cols].values * weights_b[np.newaxis, :]
    ).sum(axis=1)

    # Bug A strict variant: require at least 3 indicators
    n_indicators_present = df[pctile_cols].notna().sum(axis=1)
    df.loc[n_indicators_present < 3, ["composite_equal", "composite_pricedev2x", "composite_singlebid2x"]] = np.nan

    # Bug B: minimum tender sample for composite ranking
    if "total_tenders" in df.columns:
        df.loc[df["total_tenders"] < MIN_TENDERS_FOR_COMPOSITE, ["composite_equal", "composite_pricedev2x", "composite_singlebid2x"]] = np.nan

    return df


def sensitivity_analysis(risk_df: pd.DataFrame) -> dict[str, float]:
    """Compute Spearman ρ between equal-weight and alternative rankings.

    Returns dict with keys:
        rho_pricedev2x, pval_pricedev2x,
        rho_singlebid2x, pval_singlebid2x
    """
    valid = risk_df.dropna(
        subset=["composite_equal", "composite_pricedev2x", "composite_singlebid2x"]
    )

    rho_a, p_a = sp_stats.spearmanr(
        valid["composite_equal"], valid["composite_pricedev2x"]
    )
    rho_b, p_b = sp_stats.spearmanr(
        valid["composite_equal"], valid["composite_singlebid2x"]
    )

    return {
        "rho_pricedev2x": round(rho_a, 4),
        "pval_pricedev2x": round(p_a, 6),
        "rho_singlebid2x": round(rho_b, 4),
        "pval_singlebid2x": round(p_b, 6),
        "n_valid": len(valid),
    }


# ---------------------------------------------------------------------------
# Top Risk Pairings
# ---------------------------------------------------------------------------
def top_risk_pairings(
    risk_df: pd.DataFrame, n: int = 20
) -> pd.DataFrame:
    """Return top-N buyer × sector pairings by composite_equal score."""
    return (
        risk_df.dropna(subset=["composite_equal"])
        .nlargest(n, "composite_equal")
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Case-Study Cards
# ---------------------------------------------------------------------------
def case_study_cards(
    top_df: pd.DataFrame,
    merged: pd.DataFrame,
    tenders: pd.DataFrame,
) -> list[dict]:
    """Generate case-study cards for top buyer × sector pairings.

    Each card contains:
        buyer_name, sector_name, n_tenders, n_awards,
        indicator values, example_titles (2–3)
    """
    cards = []

    for _, row in top_df.iterrows():
        bid = int(row["buyer_id"])
        sid = int(row["sector_id"])

        # Get buyer and sector names
        buyer_name = row.get("buyer_name", "Unknown")
        sector_name = row.get("sector_name", "Unknown")

        # Sample tender titles from this buyer × sector
        bs_tenders = tenders[
            (tenders["buyer_id"] == bid) & (tenders["sector_id"] == sid)
        ]
        n_tenders = len(bs_tenders)

        bs_awards = merged[
            (merged["buyer_id"] == bid)
            & (merged["sector_id"] == sid)
            & (merged["award_value_amount"] > 1)
        ]
        n_awards = len(bs_awards)

        # Pick 2-3 example titles
        sample_titles = (
            bs_tenders["tender_title"]
            .dropna()
            .sample(n=min(3, len(bs_tenders.dropna(subset=["tender_title"]))),
                    random_state=42)
            .tolist()
        )

        card = {
            "buyer_name": buyer_name,
            "sector_name": sector_name,
            "n_tenders": n_tenders,
            "n_awards": n_awards,
            "price_dev_median": _safe_round(row.get("price_dev_median"), 4),
            "single_bidder_rate": _safe_round(row.get("single_bidder_rate"), 4),
            "non_open_share": _safe_round(row.get("non_open_share"), 4),
            "bunching_composite": _safe_round(row.get("bunching_composite"), 4),
            "stickiness_top3": _safe_round(row.get("stickiness_top3"), 4),
            "composite_equal": _safe_round(row.get("composite_equal"), 2),
            "composite_pricedev2x": _safe_round(row.get("composite_pricedev2x"), 2),
            "composite_singlebid2x": _safe_round(row.get("composite_singlebid2x"), 2),
            "example_titles": sample_titles,
        }
        cards.append(card)

    return cards


def _safe_round(val, decimals: int = 4):
    """Round if not NaN/None."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return round(val, decimals)


# ---------------------------------------------------------------------------
# Master builder: assemble buyer_sector_risk table
# ---------------------------------------------------------------------------
def build_risk_table(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build the full buyer × sector risk table with all 5 indicators
    and composite scores.

    Parameters
    ----------
    data : dict from load_data()

    Returns
    -------
    dict with keys 'domestic' and 'external', each containing a DataFrame
    """
    merged = data["merged"]
    tenders = data["tenders"]

    # 1. Price deviation
    price_dev = compute_price_deviation(merged)

    # 2. Single-bidder rate
    single_bid = compute_single_bidder_rate(tenders)

    # 3. Non-open method share
    non_open = compute_non_open_share(tenders)

    # 4. Threshold bunching (buyer-level)
    bunching = compute_threshold_bunching_buyer(tenders)

    # 5. Stickiness
    stickiness = compute_stickiness(merged)

    # Assemble: start from all buyer × sector combos in tenders
    base = (
        tenders.groupby(["buyer_id", "sector_id"])
        .agg(
            buyer_name=("buyer_name", "first"),
            sector_name=("sector_name", "first"),
            is_externally_funded=("is_externally_funded", "first")
        )
        .reset_index()
    )

    risk_df = base.copy()
    for indicator_df, cols in [
        (price_dev, ["price_dev_median", "price_dev_p25", "price_dev_p75", "price_dev_n"]),
        (single_bid, ["single_bidder_rate", "single_bidder_n", "total_with_bids", "no_bid_data_count"]),
        (non_open, ["non_open_share", "non_open_count", "total_tenders"]),
        (bunching, ["bunching_25L", "bunching_1Cr", "bunching_10Cr", "bunching_composite", "bunching_n"]),
        (stickiness, ["stickiness_top3", "total_award_value", "n_suppliers", "top3_value"]),
    ]:
        merge_cols = ["buyer_id", "sector_id"] + cols
        available = [c for c in merge_cols if c in indicator_df.columns]
        risk_df = risk_df.merge(
            indicator_df[available], on=["buyer_id", "sector_id"], how="left"
        )

    # Partition by funding regime and compute composite scores independently
    domestic = risk_df[~risk_df["is_externally_funded"]].copy()
    external = risk_df[risk_df["is_externally_funded"]].copy()

    domestic = composite_score(domestic)
    if len(external) > 0:
        external = composite_score(external)

    return {"domestic": domestic, "external": external}


# ---------------------------------------------------------------------------
# Standalone sanity check
# ---------------------------------------------------------------------------
def main() -> None:
    """Quick sanity check: load data, compute all indicators, print summary."""
    print("Loading data ...")
    data = load_data()
    print(f"  tenders: {len(data['tenders']):,}")
    print(f"  awards:  {len(data['awards']):,}")
    print(f"  merged:  {len(data['merged']):,}")

    print("\nBuilding risk table ...")
    tables = build_risk_table(data)
    risk_df = tables["domestic"]
    print(f"  buyer × sector combos (domestic): {len(risk_df):,}")
    print(f"  buyer × sector combos (external): {len(tables['external']):,}")

    # Indicator summaries
    for col in ["price_dev_median", "single_bidder_rate", "non_open_share",
                 "bunching_composite", "stickiness_top3", "composite_equal"]:
        valid = risk_df[col].dropna()
        if len(valid) > 0:
            print(f"\n  {col}:")
            print(f"    n={len(valid):,}  mean={valid.mean():.4f}  "
                  f"median={valid.median():.4f}  min={valid.min():.4f}  "
                  f"max={valid.max():.4f}")

    # Sensitivity
    sa = sensitivity_analysis(risk_df)
    print(f"\nSensitivity analysis:")
    print(f"  Equal vs PriceDev 2×: ρ = {sa['rho_pricedev2x']:.4f}  (p = {sa['pval_pricedev2x']:.6f})")
    print(f"  Equal vs SingleBid 2×: ρ = {sa['rho_singlebid2x']:.4f}  (p = {sa['pval_singlebid2x']:.6f})")
    print(f"  N valid: {sa['n_valid']}")

    # Top 10
    top = top_risk_pairings(risk_df, n=10)
    print(f"\nTop-10 buyer × sector risk pairings (composite_equal):")
    for i, row in top.iterrows():
        print(f"  {i+1}. {row['buyer_name'][:40]:40s} × {row['sector_name']:20s}  "
              f"score={row['composite_equal']:.1f}")

    # Global bunching
    bunching_global = compute_threshold_bunching_global(data["tenders"])
    print(f"\nGlobal threshold bunching:")
    for label, info in bunching_global.items():
        print(f"  {label}: below={info['below_count']}, "
              f"surround_avg={info['surround_avg_count']}, "
              f"ratio={info['excess_ratio']}")


if __name__ == "__main__":
    main()
