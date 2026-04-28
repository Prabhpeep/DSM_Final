"""
03_concentration.py — Chapter A: Concentration Analysis (RQ1)
=============================================================

Orchestration script for all concentration analysis.
Run from project root:  python notebooks/03_concentration.py

Outputs:
  - reports/figures/lorenz_by_sector.png
  - reports/figures/hhi_heatmap.png
  - reports/figures/top20_suppliers.png
  - reports/figures/top20_suppliers_anon.png
  - reports/figures/degree_distribution.png
  - reports/figures/network_top50.png
  - reports/figures/buyer_cluster_silhouette.png
  - reports/figures/buyer_clusters_pca.png
  - reports/figures/supplier_communities.png
  - outputs/buyer_supplier_graph.gexf
  - Console tables for HHI, Gini, CR4/CR10, centrality, clusters
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for headless runs

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import networkx as nx
from matplotlib.colors import LogNorm
from sklearn.decomposition import PCA

# ── Ensure project root is on sys.path ─────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.metrics.concentration import (
    build_buyer_features,
    cluster_buyers,
    concentration_ratio,
    cr_by_group,
    gini,
    gini_by_group,
    hhi,
    hhi_by_group,
    lorenz_curve,
)
from src.metrics.networks import (
    build_bipartite_graph,
    compute_centrality,
    degree_distribution,
    detect_communities,
    project_supplier_graph,
    save_gexf,
    top_n_subgraph,
)

# ── Config ─────────────────────────────────────────────────────────────────
DB_PATH = PROJECT_ROOT / "db" / "dsm.sqlite"
FIG_DIR = PROJECT_ROOT / "reports" / "figures"
OUT_DIR = PROJECT_ROOT / "outputs"
FIG_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
    "font.family": "sans-serif",
    "font.size": 10,
})

# ═══════════════════════════════════════════════════════════════════════════
# 1. DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════

def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load merged awards+tenders, full tenders, and dimension tables."""
    conn = sqlite3.connect(DB_PATH)

    merged = pd.read_sql("""
        SELECT fa.award_link, fa.ocid, fa.supplier_canonical_id,
               fa.award_value_amount,
               ft.buyer_id, ft.sector_id, ft.fiscal_year,
               ft.procurement_method, ft.tender_value_amount,
               ft.number_of_tenderers,
               db.buyer_name, ds.supplier_name, dsec.sector_name
        FROM   fact_awards fa
        JOIN   fact_tenders ft  ON fa.ocid = ft.ocid
        JOIN   dim_buyer db     ON ft.buyer_id = db.buyer_id
        JOIN   dim_supplier ds  ON fa.supplier_canonical_id = ds.supplier_canonical_id
        JOIN   dim_sector dsec  ON ft.sector_id = dsec.sector_id
        WHERE  ft.fiscal_year IN ('2020-2021','2021-2022','2022-2023')
    """, conn)

    tenders = pd.read_sql("""
        SELECT ft.*, db.buyer_name, dsec.sector_name
        FROM   fact_tenders ft
        JOIN   dim_buyer db     ON ft.buyer_id = db.buyer_id
        JOIN   dim_sector dsec  ON ft.sector_id = dsec.sector_id
        WHERE  ft.fiscal_year IN ('2020-2021','2021-2022','2022-2023')
    """, conn)

    conn.close()
    return merged, tenders, merged  # third return unused, kept for API compat


def print_section(title: str) -> None:
    print(f"\n{'═' * 72}")
    print(f"  {title}")
    print(f"{'═' * 72}")


# ═══════════════════════════════════════════════════════════════════════════
# 2. SELECTION BIAS STATEMENT
# ═══════════════════════════════════════════════════════════════════════════

def selection_bias(merged: pd.DataFrame, tenders: pd.DataFrame) -> None:
    print_section("SELECTION BIAS")
    total_tenders = len(tenders)
    awarded_tenders = tenders["has_award"].sum()
    print(f"  Total tenders (FY 2020-23):  {total_tenders:,}")
    print(f"  Tenders with awards:         {awarded_tenders:,.0f}  ({100*awarded_tenders/total_tenders:.1f}%)")
    print(f"  Total award lines:           {len(merged):,}")

    val_df = merged[merged["award_value_amount"] > 1]
    print(f"  Awards with value > 1 (₹):   {len(val_df):,}  ({100*len(val_df)/len(merged):.1f}% of all awards)")

    zero_val = (merged["award_value_amount"] == 0).sum()
    one_val = (merged["award_value_amount"] == 1).sum()
    print(f"  Excluded: value=0 ({zero_val:,}), value=1 ({one_val:,})")
    print()
    print("  ⚠ These results describe the awarded subset of tenders, which")
    print(f"    represents {100*awarded_tenders/total_tenders:.1f}% of all tenders in the period.")
    print("    Selection bias is characterised in §1.7 of the report.")


# ═══════════════════════════════════════════════════════════════════════════
# 3. HHI ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def run_hhi(val_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    print_section("HHI — BY SECTOR")
    hhi_sector = hhi_by_group(val_df, "sector_name")
    print(hhi_sector.to_string(index=False))

    print_section("HHI — BY BUYER (top 20)")
    hhi_buyer = hhi_by_group(val_df, "buyer_name")
    print(hhi_buyer.head(20).to_string(index=False))

    return hhi_sector, hhi_buyer


# ═══════════════════════════════════════════════════════════════════════════
# 4. GINI & LORENZ CURVES
# ═══════════════════════════════════════════════════════════════════════════

def run_gini(val_df: pd.DataFrame) -> pd.DataFrame:
    print_section("GINI — OVERALL & BY SECTOR")

    # Overall
    supplier_totals = val_df.groupby("supplier_canonical_id")["award_value_amount"].sum().values
    g_overall = gini(supplier_totals)
    print(f"  Overall Gini: {g_overall:.4f}  (n_suppliers = {len(supplier_totals):,})")

    # By sector
    gini_df = gini_by_group(val_df, "sector_name")
    print(gini_df.to_string(index=False))
    return gini_df


def plot_lorenz(val_df: pd.DataFrame) -> None:
    """One panel per sector, 2×5 grid."""
    sectors = sorted(val_df["sector_name"].unique())
    fig, axes = plt.subplots(2, 5, figsize=(20, 8))
    axes = axes.ravel()

    for i, sec in enumerate(sectors):
        ax = axes[i]
        grp = val_df[val_df["sector_name"] == sec]
        supplier_totals = grp.groupby("supplier_canonical_id")["award_value_amount"].sum().values
        cum_pop, cum_share = lorenz_curve(supplier_totals)
        g = gini(supplier_totals)

        ax.fill_between(cum_pop, cum_share, cum_pop, alpha=0.15, color="steelblue")
        ax.plot(cum_pop, cum_share, color="steelblue", linewidth=1.5, label=f"Gini={g:.3f}")
        ax.plot([0, 1], [0, 1], "k--", linewidth=0.8, alpha=0.5)
        ax.set_title(sec.replace("_", " ").title(), fontsize=9, fontweight="bold")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.legend(fontsize=7, loc="upper left")
        ax.set_xlabel("Cum. share of suppliers", fontsize=7)
        ax.set_ylabel("Cum. share of value", fontsize=7)
        ax.tick_params(labelsize=7)

    fig.suptitle("Lorenz Curves by Sector — Supplier Award-Value Distribution (FY 2020-23)",
                 fontsize=12, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "lorenz_by_sector.png")
    plt.close(fig)
    print(f"  Saved {FIG_DIR / 'lorenz_by_sector.png'}")


# ═══════════════════════════════════════════════════════════════════════════
# 5. CONCENTRATION RATIOS
# ═══════════════════════════════════════════════════════════════════════════

def run_cr(val_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    print_section("CONCENTRATION RATIOS (CR4, CR10) — BY SECTOR")
    cr_sector = cr_by_group(val_df, "sector_name")
    print(cr_sector.to_string(index=False))

    print_section("CONCENTRATION RATIOS (CR4, CR10) — BY BUYER (top 20)")
    cr_buyer = cr_by_group(val_df, "buyer_name")
    print(cr_buyer.head(20).to_string(index=False))

    return cr_sector, cr_buyer


# ═══════════════════════════════════════════════════════════════════════════
# 6. HHI HEATMAP
# ═══════════════════════════════════════════════════════════════════════════

def plot_hhi_heatmap(val_df: pd.DataFrame) -> None:
    """HHI heatmap: sector (y) × buyer (x).  Only buyers with ≥5 value-filtered awards shown."""
    # Compute per buyer-sector pair
    rows = []
    for (buyer, sector), grp in val_df.groupby(["buyer_name", "sector_name"]):
        if len(grp) < 5:
            continue
        shares = grp.groupby("supplier_canonical_id")["award_value_amount"].sum()
        shares = (shares / shares.sum()).values
        rows.append({"buyer_name": buyer, "sector_name": sector, "hhi": hhi(shares)})

    if not rows:
        print("  (not enough buyer-sector pairs with ≥5 awards for heatmap)")
        return

    hmap = pd.DataFrame(rows).pivot(index="sector_name", columns="buyer_name", values="hhi")

    # Sort sectors and buyers by mean HHI
    sector_order = hmap.mean(axis=1).sort_values(ascending=False).index
    buyer_order = hmap.mean(axis=0).sort_values(ascending=False).index
    hmap = hmap.loc[sector_order, buyer_order]

    # Trim to top 30 buyers for readability
    hmap = hmap.iloc[:, :30]

    fig, ax = plt.subplots(figsize=(18, 6))
    sns.heatmap(hmap, ax=ax, cmap="YlOrRd", annot=False,
                linewidths=0.3, linecolor="white",
                cbar_kws={"label": "HHI (0–10,000)"})
    ax.set_title("HHI by Sector × Buyer Department (≥5 awards, FY 2020-23)",
                 fontsize=12, fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("")
    plt.xticks(rotation=45, ha="right", fontsize=6)
    plt.yticks(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "hhi_heatmap.png")
    plt.close(fig)
    print(f"  Saved {FIG_DIR / 'hhi_heatmap.png'}")


# ═══════════════════════════════════════════════════════════════════════════
# 7. TOP-20 SUPPLIER BAR CHART
# ═══════════════════════════════════════════════════════════════════════════

def plot_top20_suppliers(val_df: pd.DataFrame) -> None:
    """Horizontal bar chart of top-20 suppliers by total award value."""
    top = (val_df.groupby(["supplier_canonical_id", "supplier_name"])["award_value_amount"]
           .sum().reset_index()
           .nlargest(20, "award_value_amount"))

    # Version with real names
    fig, ax = plt.subplots(figsize=(10, 8))
    bars = ax.barh(range(len(top)), top["award_value_amount"].values / 1e9, color="steelblue")
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(top["supplier_name"].values, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel("Total Award Value (₹ Billion)")
    ax.set_title("Top 20 Suppliers by Award Value (FY 2020-23)", fontweight="bold")
    for bar, val in zip(bars, top["award_value_amount"].values):
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                f"₹{val/1e9:.1f}B", va="center", fontsize=7)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "top20_suppliers.png")
    plt.close(fig)
    print(f"  Saved {FIG_DIR / 'top20_suppliers.png'}")

    # Anonymized version
    fig, ax = plt.subplots(figsize=(10, 8))
    anon_labels = [f"Supplier {chr(65+i)}" for i in range(len(top))]
    bars = ax.barh(range(len(top)), top["award_value_amount"].values / 1e9, color="coral")
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(anon_labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Total Award Value (₹ Billion)")
    ax.set_title("Top 20 Suppliers by Award Value — Anonymized (FY 2020-23)", fontweight="bold")
    for bar, val in zip(bars, top["award_value_amount"].values):
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                f"₹{val/1e9:.1f}B", va="center", fontsize=7)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "top20_suppliers_anon.png")
    plt.close(fig)
    print(f"  Saved {FIG_DIR / 'top20_suppliers_anon.png'}")


# ═══════════════════════════════════════════════════════════════════════════
# 8. NETWORK ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def run_network(merged: pd.DataFrame) -> None:
    """Full network analysis pipeline — uses ALL awards (incl. value=0)."""
    print_section("NETWORK ANALYSIS")

    # Build bipartite graph on all awards (count-based metric)
    G = build_bipartite_graph(merged)
    n_buyers = sum(1 for _, d in G.nodes(data=True) if d.get("bipartite") == 0)
    n_suppliers = sum(1 for _, d in G.nodes(data=True) if d.get("bipartite") == 1)
    print(f"  Graph: {n_buyers} buyers, {n_suppliers} suppliers, {G.number_of_edges():,} edges")

    # Degree distribution
    dd_b = degree_distribution(G, 0)
    dd_s = degree_distribution(G, 1)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(dd_b["degree"], dd_b["count"], s=20, alpha=0.6, label="Buyers", color="steelblue")
    ax.scatter(dd_s["degree"], dd_s["count"], s=20, alpha=0.6, label="Suppliers", color="coral")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Degree (log)")
    ax.set_ylabel("Count (log)")
    ax.set_title("Degree Distribution — Buyer–Supplier Bipartite Graph", fontweight="bold")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "degree_distribution.png")
    plt.close(fig)
    print(f"  Saved {FIG_DIR / 'degree_distribution.png'}")

    # Centrality
    print_section("CENTRALITY — TOP 15 BUYERS")
    cent_b = compute_centrality(G, 0)
    print(cent_b.head(15)[["label", "degree", "eigenvector_centrality", "betweenness_centrality"]].to_string(index=False))

    print_section("CENTRALITY — TOP 15 SUPPLIERS")
    cent_s = compute_centrality(G, 1)
    print(cent_s.head(15)[["label", "degree", "eigenvector_centrality", "betweenness_centrality"]].to_string(index=False))

    # Supplier projection + Louvain
    print_section("LOUVAIN COMMUNITY DETECTION (supplier projection)")
    G_proj = project_supplier_graph(G)
    print(f"  Projected graph: {G_proj.number_of_nodes()} nodes, {G_proj.number_of_edges():,} edges")

    communities = detect_communities(G_proj)
    n_comm = len(set(communities.values())) if communities else 0
    print(f"  Communities found: {n_comm}")

    if communities:
        from collections import Counter
        comm_sizes = Counter(communities.values())
        top_communities = comm_sizes.most_common(15)
        print("  Top 15 community sizes:")
        for cid, size in top_communities:
            print(f"    Community {cid}: {size} suppliers")

        # Bar chart of community sizes
        fig, ax = plt.subplots(figsize=(10, 5))
        sizes = sorted(comm_sizes.values(), reverse=True)
        ax.bar(range(len(sizes)), sizes, color="steelblue", alpha=0.8)
        ax.set_xlabel("Community rank")
        ax.set_ylabel("Number of suppliers")
        ax.set_title(f"Louvain Community Sizes — {n_comm} communities detected", fontweight="bold")
        fig.tight_layout()
        fig.savefig(FIG_DIR / "supplier_communities.png")
        plt.close(fig)
        print(f"  Saved {FIG_DIR / 'supplier_communities.png'}")

    # Network diagram (top 50 buyers + top 50 suppliers)
    G_sub = top_n_subgraph(G, 50, 50)
    fig, ax = plt.subplots(figsize=(16, 12))
    pos = nx.spring_layout(G_sub, k=0.5, seed=42, weight="weight")

    buyer_nodes = [n for n, d in G_sub.nodes(data=True) if d.get("bipartite") == 0]
    supplier_nodes = [n for n, d in G_sub.nodes(data=True) if d.get("bipartite") == 1]

    # Edge widths proportional to log(weight)
    edges = G_sub.edges(data=True)
    weights = [d.get("weight", 1) for _, _, d in edges]
    max_w = max(weights) if weights else 1
    edge_widths = [0.3 + 2.0 * np.log1p(w) / np.log1p(max_w) for w in weights]

    nx.draw_networkx_edges(G_sub, pos, ax=ax, width=edge_widths, alpha=0.15, edge_color="gray")

    # Buyer node sizes proportional to degree
    buyer_sizes = [30 + 10 * G_sub.degree(n) for n in buyer_nodes]
    nx.draw_networkx_nodes(G_sub, pos, nodelist=buyer_nodes, node_color="steelblue",
                           node_size=buyer_sizes, alpha=0.8, ax=ax, label="Buyers")

    # Supplier node sizes proportional to degree
    supplier_sizes = [30 + 10 * G_sub.degree(n) for n in supplier_nodes]
    nx.draw_networkx_nodes(G_sub, pos, nodelist=supplier_nodes, node_color="coral",
                           node_size=supplier_sizes, alpha=0.8, ax=ax, label="Suppliers")

    # Labels for high-degree nodes only
    high_deg = [n for n in G_sub.nodes() if G_sub.degree(n) >= 10]
    labels = {n: G_sub.nodes[n].get("label", n)[:25] for n in high_deg}
    nx.draw_networkx_labels(G_sub, pos, labels, font_size=5, ax=ax)

    ax.legend(fontsize=10, loc="upper left")
    ax.set_title("Buyer–Supplier Network (Top 50 × Top 50 by value)", fontsize=13, fontweight="bold")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "network_top50.png")
    plt.close(fig)
    print(f"  Saved {FIG_DIR / 'network_top50.png'}")

    # Save full graph as GEXF
    save_gexf(G, OUT_DIR / "buyer_supplier_graph.gexf")
    print(f"  Saved {OUT_DIR / 'buyer_supplier_graph.gexf'}")


# ═══════════════════════════════════════════════════════════════════════════
# 9. BUYER CLUSTERING
# ═══════════════════════════════════════════════════════════════════════════

def run_clustering(val_df: pd.DataFrame, tenders: pd.DataFrame) -> None:
    print_section("BUYER CLUSTERING")

    features = build_buyer_features(val_df, tenders)
    print(f"  Feature matrix: {features.shape[0]} buyers × {features.shape[1]} features")
    print(f"  NaN counts per feature:")
    print(features.isna().sum().to_string())

    labels, best_k, scores = cluster_buyers(features)
    print(f"\n  Silhouette scores: {scores}")
    print(f"  Best K = {best_k}  (silhouette = {scores[best_k]:.4f})")

    # Silhouette plot
    fig, ax = plt.subplots(figsize=(7, 4))
    ks = sorted(scores.keys())
    ax.plot(ks, [scores[k] for k in ks], "o-", color="steelblue", linewidth=2)
    ax.axvline(best_k, color="coral", linestyle="--", label=f"Best K={best_k}")
    ax.set_xlabel("Number of clusters (K)")
    ax.set_ylabel("Silhouette Score")
    ax.set_title("Buyer Clustering — Silhouette Score vs K", fontweight="bold")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "buyer_cluster_silhouette.png")
    plt.close(fig)
    print(f"  Saved {FIG_DIR / 'buyer_cluster_silhouette.png'}")

    # PCA scatter
    from sklearn.preprocessing import StandardScaler
    filled = features.fillna(features.median())
    X_scaled = StandardScaler().fit_transform(filled)
    pca = PCA(n_components=2, random_state=42)
    X_2d = pca.fit_transform(X_scaled)

    fig, ax = plt.subplots(figsize=(10, 7))
    scatter = ax.scatter(X_2d[:, 0], X_2d[:, 1], c=labels, cmap="Set2",
                         s=60, alpha=0.8, edgecolors="white", linewidth=0.5)
    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}% var)")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}% var)")
    ax.set_title(f"Buyer Clusters (K={best_k}) — PCA Projection", fontweight="bold")
    plt.colorbar(scatter, ax=ax, label="Cluster")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "buyer_clusters_pca.png")
    plt.close(fig)
    print(f"  Saved {FIG_DIR / 'buyer_clusters_pca.png'}")

    # Cluster interpretation
    features_with_labels = features.copy()
    features_with_labels["cluster"] = labels

    # Add buyer name
    conn = sqlite3.connect(DB_PATH)
    buyers = pd.read_sql("SELECT buyer_id, buyer_name FROM dim_buyer", conn)
    conn.close()
    features_with_labels = features_with_labels.merge(buyers, left_index=True, right_on="buyer_id", how="left")

    print_section("CLUSTER PROFILES (mean per cluster)")
    profile = features_with_labels.groupby("cluster")[
        ["median_tender_value", "mean_bidder_count", "single_bidder_rate",
         "supplier_hhi", "procurement_method_open_share", "repeat_top3_supplier_share"]
    ].mean()
    print(profile.to_string())

    print_section("CLUSTER SIZES & SAMPLE BUYERS")
    for c in sorted(features_with_labels["cluster"].unique()):
        members = features_with_labels[features_with_labels["cluster"] == c]
        print(f"\n  Cluster {c}  ({len(members)} buyers)")
        sample = members.head(5)
        for _, row in sample.iterrows():
            print(f"    - {row['buyer_name']}")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("Loading data ...")
    merged, tenders, _ = load_data()
    print(f"  Merged (all awards):     {len(merged):,} rows")
    print(f"  Tenders:                 {len(tenders):,} rows")

    # Split: value-filtered for HHI/Gini/CR; full for count-based / network
    val_df = merged[merged["award_value_amount"] > 1].copy()
    print(f"  Value-filtered awards:   {len(val_df):,} rows")

    selection_bias(merged, tenders)

    # --- Concentration metrics ---
    hhi_sector, hhi_buyer = run_hhi(val_df)
    gini_df = run_gini(val_df)
    plot_lorenz(val_df)
    cr_sector, cr_buyer = run_cr(val_df)
    plot_hhi_heatmap(val_df)
    plot_top20_suppliers(val_df)

    # --- Network analysis (uses ALL awards) ---
    run_network(merged)

    # --- Buyer clustering ---
    run_clustering(val_df, tenders)

    print_section("DONE")
    print(f"  Figures saved to:  {FIG_DIR}")
    print(f"  GEXF saved to:     {OUT_DIR / 'buyer_supplier_graph.gexf'}")


if __name__ == "__main__":
    main()
