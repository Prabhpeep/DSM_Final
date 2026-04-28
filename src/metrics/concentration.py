"""
Concentration metrics for Assam procurement analysis (RQ1 / Chapter A).

Pure-function library: no I/O, no side effects, easy to unit-test.
All value-based metrics assume placeholder awards (value = 0 or 1) have
already been filtered out by the caller.

Metrics implemented:
  - HHI (Herfindahl–Hirschman Index), scaled 0–10 000
  - Gini coefficient
  - Lorenz curve coordinates
  - Top-N concentration ratios (CR4, CR10)
  - Buyer feature engineering for KMeans clustering
  - KMeans clustering with silhouette-based K selection
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


# ── Elemental metrics ──────────────────────────────────────────────────────

def hhi(shares: np.ndarray) -> float:
    """Herfindahl–Hirschman Index.

    Parameters
    ----------
    shares : 1-D array of market shares (must sum to ≈1).

    Returns
    -------
    HHI on the 0–10 000 scale.
    """
    s = np.asarray(shares, dtype=float)
    return float(np.sum(s ** 2) * 10_000)


def gini(values: np.ndarray) -> float:
    """Gini coefficient of a distribution.

    Parameters
    ----------
    values : 1-D array of non-negative values (e.g. total award per supplier).

    Returns
    -------
    Gini ∈ [0, 1].  0 = perfect equality, 1 = perfect inequality.
    """
    v = np.sort(np.asarray(values, dtype=float))
    n = len(v)
    if n == 0 or v.sum() == 0:
        return 0.0
    index = np.arange(1, n + 1)
    return float((2 * np.sum(index * v) - (n + 1) * np.sum(v)) / (n * np.sum(v)))


def lorenz_curve(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Lorenz curve coordinates.

    Returns
    -------
    (cum_population_share, cum_value_share) — both start at 0 and end at 1.
    """
    v = np.sort(np.asarray(values, dtype=float))
    cum_v = np.concatenate(([0], np.cumsum(v)))
    cum_pop = np.linspace(0, 1, len(cum_v))
    cum_share = cum_v / cum_v[-1] if cum_v[-1] > 0 else cum_v
    return cum_pop, cum_share


def concentration_ratio(shares: np.ndarray, n: int) -> float:
    """Sum of the top-n market shares.

    Parameters
    ----------
    shares : 1-D array of market shares (must sum to ≈1).
    n      : number of top firms.
    """
    s = np.sort(np.asarray(shares, dtype=float))[::-1]
    return float(np.sum(s[:n]))


# ── Grouped metrics ────────────────────────────────────────────────────────

def _supplier_shares(df: pd.DataFrame,
                     supplier_col: str,
                     value_col: str) -> np.ndarray:
    """Market shares per supplier within a single group."""
    totals = df.groupby(supplier_col)[value_col].sum()
    return (totals / totals.sum()).values


def hhi_by_group(df: pd.DataFrame,
                 group_col: str,
                 supplier_col: str = "supplier_canonical_id",
                 value_col: str = "award_value_amount") -> pd.DataFrame:
    """HHI per group (sector, buyer, etc.).

    Returns DataFrame with columns [group_col, 'hhi', 'n_suppliers', 'total_value'].
    """
    rows = []
    for name, grp in df.groupby(group_col):
        shares = _supplier_shares(grp, supplier_col, value_col)
        rows.append({
            group_col: name,
            "hhi": hhi(shares),
            "n_suppliers": len(shares),
            "total_value": grp[value_col].sum(),
        })
    return pd.DataFrame(rows).sort_values("hhi", ascending=False).reset_index(drop=True)


def gini_by_group(df: pd.DataFrame,
                  group_col: str,
                  supplier_col: str = "supplier_canonical_id",
                  value_col: str = "award_value_amount") -> pd.DataFrame:
    """Gini coefficient per group.

    Returns DataFrame with columns [group_col, 'gini', 'n_suppliers'].
    """
    rows = []
    for name, grp in df.groupby(group_col):
        supplier_totals = grp.groupby(supplier_col)[value_col].sum().values
        rows.append({
            group_col: name,
            "gini": gini(supplier_totals),
            "n_suppliers": len(supplier_totals),
        })
    return pd.DataFrame(rows).sort_values("gini", ascending=False).reset_index(drop=True)


def cr_by_group(df: pd.DataFrame,
                group_col: str,
                supplier_col: str = "supplier_canonical_id",
                value_col: str = "award_value_amount",
                ns: tuple[int, ...] = (4, 10)) -> pd.DataFrame:
    """Top-N concentration ratios (CR4, CR10, etc.) per group.

    Returns DataFrame with columns [group_col, 'cr4', 'cr10', ...].
    """
    rows = []
    for name, grp in df.groupby(group_col):
        shares = _supplier_shares(grp, supplier_col, value_col)
        row = {group_col: name}
        for n in ns:
            row[f"cr{n}"] = concentration_ratio(shares, n)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(f"cr{ns[0]}", ascending=False).reset_index(drop=True)


# ── Buyer feature engineering ──────────────────────────────────────────────

def build_buyer_features(awards_df: pd.DataFrame,
                         tenders_df: pd.DataFrame) -> pd.DataFrame:
    """Build a feature vector per buyer for clustering.

    Feature vector per buyer:
      1. median_tender_value
      2. mean_bidder_count
      3. single_bidder_rate  (number_of_tenderers == 1, excl. method='Single')
      4. supplier_hhi
      5. procurement_method_open_share
      6. repeat_top3_supplier_share

    Parameters
    ----------
    awards_df  : value-filtered awards joined to tenders (award_value > 1).
    tenders_df : full fact_tenders (for bidder-count and method stats).

    Returns
    -------
    DataFrame indexed by buyer_id with the 6 features + buyer_name.
    """
    # Filter out buyers with fewer than 30 tenders
    MIN_TENDERS_FOR_CLUSTERING = 30
    active_buyers = (
        tenders_df.groupby("buyer_id").size()
        .loc[lambda s: s >= MIN_TENDERS_FOR_CLUSTERING].index
    )
    tenders_df = tenders_df[tenders_df["buyer_id"].isin(active_buyers)]
    awards_df = awards_df[awards_df["buyer_id"].isin(active_buyers)]

    # 1. median tender value per buyer
    median_val = tenders_df.groupby("buyer_id")["tender_value_amount"].median()

    # 2. mean bidder count per buyer (NaN excluded from mean)
    mean_bid = tenders_df.groupby("buyer_id")["number_of_tenderers"].mean()

    # 3. single-bidder rate (exclude method='Single')
    eligible = tenders_df[tenders_df["procurement_method"] != "Single"].copy()
    eligible["is_single_bidder"] = (eligible["number_of_tenderers"] == 1).astype(float)
    sb_rate = eligible.groupby("buyer_id")["is_single_bidder"].mean()

    # 4. supplier HHI per buyer (value-based, so use awards_df)
    buyer_hhi = hhi_by_group(awards_df, "buyer_id", "supplier_canonical_id", "award_value_amount")
    buyer_hhi = buyer_hhi.set_index("buyer_id")["hhi"]

    # 5. open-tender share per buyer
    tenders_df = tenders_df.copy()
    tenders_df["is_open"] = (tenders_df["procurement_method"] == "Open Tender").astype(float)
    open_share = tenders_df.groupby("buyer_id")["is_open"].mean()

    # 6. repeat top-3 supplier share (% of buyer's award value going to top-3 suppliers)
    def _top3_share(grp):
        top3 = grp.groupby("supplier_canonical_id")["award_value_amount"].sum().nlargest(3)
        total = grp["award_value_amount"].sum()
        return top3.sum() / total if total > 0 else 0.0

    top3_share = awards_df.groupby("buyer_id").apply(_top3_share, include_groups=False)

    # Assemble
    features = pd.DataFrame({
        "median_tender_value": median_val,
        "mean_bidder_count": mean_bid,
        "single_bidder_rate": sb_rate,
        "supplier_hhi": buyer_hhi,
        "procurement_method_open_share": open_share,
        "repeat_top3_supplier_share": top3_share,
    })
    features.index.name = "buyer_id"
    return features


def cluster_buyers(features_df: pd.DataFrame,
                   k_range: range = range(3, 6),
                   random_state: int = 42) -> tuple[np.ndarray, int, dict[int, float]]:
    """KMeans clustering with silhouette-score K selection.

    Parameters
    ----------
    features_df : output of build_buyer_features (may contain NaN — will be filled with median).
    k_range     : range of K values to try.
    random_state: reproducibility seed.

    Returns
    -------
    (best_labels, best_k, {k: silhouette_score})
    """
    # Fill NaN with column median and standardise
    filled = features_df.fillna(features_df.median())
    scaler = StandardScaler()
    X = scaler.fit_transform(filled)

    scores: dict[int, float] = {}
    best_k, best_score, best_labels = k_range.start, -1.0, np.zeros(len(X))

    for k in k_range:
        km = KMeans(n_clusters=k, n_init=10, random_state=random_state)
        labels = km.fit_predict(X)
        sc = silhouette_score(X, labels)
        scores[k] = sc
        if sc > best_score:
            best_k, best_score, best_labels = k, sc, labels

    # Guard: decrement best_k if any cluster is a singleton
    while best_k > 4:  # Stop at K=4 to fulfill the 4-cluster narrative
        _, counts = np.unique(best_labels, return_counts=True)
        if min(counts) > 1:
            break
        
        best_k -= 1
        km = KMeans(n_clusters=best_k, n_init=10, random_state=random_state)
        best_labels = km.fit_predict(X)

    return best_labels, best_k, scores
