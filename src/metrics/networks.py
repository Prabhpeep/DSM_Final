"""
Network analysis for Assam procurement (RQ1 / Chapter A).

Builds the bipartite buyer–supplier graph, computes centrality metrics,
runs Louvain community detection on the supplier projection, and exports
to GEXF for Gephi visualization.

Dependencies: networkx, community (python-louvain), numpy, pandas.
"""
from __future__ import annotations

from pathlib import Path

import community as community_louvain  # python-louvain
import networkx as nx
import numpy as np
import pandas as pd
from networkx.algorithms import bipartite


# ── Graph construction ─────────────────────────────────────────────────────

def build_bipartite_graph(
    df: pd.DataFrame,
    buyer_col: str = "buyer_id",
    supplier_col: str = "supplier_canonical_id",
    weight_col: str = "award_value_amount",
    buyer_name_col: str = "buyer_name",
    supplier_name_col: str = "supplier_name",
) -> nx.Graph:
    """Build a bipartite buyer–supplier graph.

    Nodes carry a ``bipartite`` attribute (0 = buyer, 1 = supplier) and a
    ``label`` with the human-readable name.  Edge weight is the total award
    value between the pair across all awards in the input DataFrame.

    Parameters
    ----------
    df : DataFrame with at least buyer_col, supplier_col, weight_col,
         and optionally buyer_name_col, supplier_name_col.
    """
    # Aggregate edge weights
    edges = (
        df.groupby([buyer_col, supplier_col])
        .agg(
            weight=(weight_col, "sum"),
            n_awards=(weight_col, "count"),
        )
        .reset_index()
    )

    # Name lookups
    buyer_names = (
        df.drop_duplicates(buyer_col)
        .set_index(buyer_col)[buyer_name_col]
        .to_dict()
        if buyer_name_col in df.columns
        else {}
    )
    supplier_names = (
        df.drop_duplicates(supplier_col)
        .set_index(supplier_col)[supplier_name_col]
        .to_dict()
        if supplier_name_col in df.columns
        else {}
    )

    G = nx.Graph()

    # Add buyer nodes (bipartite=0)
    for bid in edges[buyer_col].unique():
        G.add_node(
            f"B_{bid}",
            bipartite=0,
            node_type="buyer",
            label=buyer_names.get(bid, str(bid)),
            original_id=int(bid),
        )

    # Add supplier nodes (bipartite=1)
    for sid in edges[supplier_col].unique():
        G.add_node(
            f"S_{sid}",
            bipartite=1,
            node_type="supplier",
            label=supplier_names.get(sid, str(sid)),
            original_id=int(sid),
        )

    # Add edges
    for _, row in edges.iterrows():
        G.add_edge(
            f"B_{int(row[buyer_col])}",
            f"S_{int(row[supplier_col])}",
            weight=float(row["weight"]),
            n_awards=int(row["n_awards"]),
        )

    return G


# ── Degree distribution ───────────────────────────────────────────────────

def degree_distribution(G: nx.Graph, partition: int | None = None) -> pd.DataFrame:
    """Degree distribution table.

    Parameters
    ----------
    G         : bipartite graph.
    partition : 0 for buyers, 1 for suppliers, None for all nodes.

    Returns
    -------
    DataFrame with columns ['degree', 'count', 'node_type'].
    """
    if partition is not None:
        nodes = [n for n, d in G.nodes(data=True) if d.get("bipartite") == partition]
    else:
        nodes = list(G.nodes())

    degrees = [G.degree(n) for n in nodes]
    node_type = "buyer" if partition == 0 else ("supplier" if partition == 1 else "all")
    from collections import Counter
    deg_counts = Counter(degrees)
    return (
        pd.DataFrame({"degree": list(deg_counts.keys()), "count": list(deg_counts.values())})
        .assign(node_type=node_type)
        .sort_values("degree")
        .reset_index(drop=True)
    )


# ── Centrality ─────────────────────────────────────────────────────────────

def compute_centrality(G: nx.Graph, partition: int) -> pd.DataFrame:
    """Eigenvector and betweenness centrality for one partition.

    Parameters
    ----------
    G         : bipartite graph.
    partition : 0 for buyers, 1 for suppliers.

    Returns
    -------
    DataFrame indexed by node ID with columns
    ['label', 'degree', 'eigenvector_centrality', 'betweenness_centrality'].
    """
    nodes = {n for n, d in G.nodes(data=True) if d.get("bipartite") == partition}

    # Eigenvector centrality on the full bipartite graph (works for connected components)
    eig = {n: 0.0 for n in G.nodes()}
    for c in nx.connected_components(G):
        if len(c) > 1:
            sub = G.subgraph(c)
            try:
                sub_eig = nx.eigenvector_centrality(sub, weight="weight", max_iter=1000)
                eig.update(sub_eig)
            except Exception:
                pass

    # Betweenness centrality
    betw = nx.betweenness_centrality(G, weight=None)

    rows = []
    for n in nodes:
        rows.append({
            "node": n,
            "label": G.nodes[n].get("label", n),
            "node_type": "buyer" if partition == 0 else "supplier",
            "degree": G.degree(n),
            "weighted_degree": G.degree(n, weight="weight"),
            "eigenvector_centrality": eig.get(n, 0.0),
            "betweenness_centrality": betw.get(n, 0.0),
        })
    return (
        pd.DataFrame(rows)
        .sort_values("eigenvector_centrality", ascending=False)
        .reset_index(drop=True)
    )





# ── Subgraph extraction ───────────────────────────────────────────────────

def top_n_subgraph(
    G: nx.Graph,
    n_buyers: int = 50,
    n_suppliers: int = 50,
) -> nx.Graph:
    """Extract a subgraph with the top-N buyers and top-N suppliers by
    weighted degree (total award value flowing through the node).
    """
    buyers = sorted(
        [n for n, d in G.nodes(data=True) if d.get("bipartite") == 0],
        key=lambda n: G.degree(n, weight="weight"),
        reverse=True,
    )[:n_buyers]

    suppliers = sorted(
        [n for n, d in G.nodes(data=True) if d.get("bipartite") == 1],
        key=lambda n: G.degree(n, weight="weight"),
        reverse=True,
    )[:n_suppliers]

    keep = set(buyers) | set(suppliers)
    return G.subgraph(keep).copy()


# ── I/O ────────────────────────────────────────────────────────────────────

def save_gexf(G: nx.Graph, path: str | Path) -> None:
    """Save graph in GEXF format for Gephi."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    nx.write_gexf(G, str(p))
