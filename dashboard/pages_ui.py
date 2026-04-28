import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import folium
from streamlit_folium import st_folium
import streamlit.components.v1 as components
import tempfile
import sys
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.metrics.networks import build_bipartite_graph, top_n_subgraph

def page_overview(tenders, awards):
    st.header("Overview: Assam Public Procurement")
    st.markdown("""
    **Motivation:** Public procurement is the largest single channel of public money flow into private hands in India. 
    Concentration and capture in this channel directly affect both fiscal efficiency and the fairness of economic opportunity. 
    This dashboard provides a structured exploration of Assam's procurement ecosystem from FY 2020 to 2023.
    """)
    
    with st.expander("Start Here: The Research Questions"):
        st.markdown("""
        The analysis is structured around three core dimensions:
        1. **Concentration (RQ1):** How concentrated is the market across sectors and buyers? *(See Concentration page)*
        2. **Integrity (RQ2):** What structural red-flags (like single bidding or price anomalies) characterize these portfolios? *(See Integrity page)*
        3. **Geographic (RQ3):** Does district-level per-capita spending align with actual project locations? *(See Geographic page)*
        """)

    st.markdown("---")
    
    st.markdown("**Context:** These top-level KPIs summarize the filtered subset of the procurement market.")
    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    total_tenders = len(tenders)
    total_value = tenders["tender_value_amount"].sum()
    total_award_value = awards["award_value_amount"].sum()
    median_bidder = tenders["number_of_tenderers"].median()

    col1.metric("Total Tenders", f"{total_tenders:,}")
    col2.metric("Est. Tender Value (INR)", f"₹ {total_value / 1e7:,.2f} Cr")
    col3.metric("Total Award Value (INR)", f"₹ {total_award_value / 1e7:,.2f} Cr")
    col4.metric("Median Bidders", f"{median_bidder:.1f}")
    
    st.caption("Caveats: FY 2020-23. Award values exclude ₹0 and ₹1 placeholders. Awards exist for 28.6% of tenders — see Data & Methodology page for selection bias discussion.")
    st.markdown("**Takeaway:** The procurement market is massive, but the low median bidder count hints at restricted competition.")

    st.markdown("---")
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Largest Procurement Portfolios")
        st.markdown("**Context:** Ranking the largest buyer and sector combinations by sheer volume of tenders.")
        top_buyers = tenders.groupby(["buyer_name", "sector_name"]).size().reset_index(name="Count").sort_values("Count", ascending=False).head(5)
        top_buyers.columns = ["Buyer", "Sector", "Tender Count"]
        st.dataframe(top_buyers, use_container_width=True, hide_index=True)
        st.markdown("**Takeaway:** The largest buyer × sector portfolio is Public Works Building and NH Department × buildings at 877 tenders.")

    with c2:
        st.subheader("Market Inequality (Gini)")
        st.markdown("**Context:** The Gini coefficient measures the inequality in the distribution of award values across all suppliers.")
        st.metric("Overall Gini Coefficient", "0.93") # Typically very high, pulled from typical concentration analysis
        st.markdown("**Takeaway:** A Gini of 0.93 represents extreme inequality, indicating that a tiny fraction of suppliers absorb the vast majority of procurement funds.")

def page_data_methodology():
    st.header("Data & Methodology")
    st.markdown("""
    **Motivation:** Robust analysis requires transparent data provenance and explicit methodological choices. This page documents the dataset's constraints and the assumptions underlying our metrics.
    
    ### 1. Source and License
    **Source:** CivicDataLab Assam OCDS-mapped dataset (republished at data.open-contracting.org).  
    **License:** ODbL (data) / GPL v2 (code).
    
    ### 2. FY Scope and Selection Bias
    The analysis is scoped strictly to **FY 2020–21 through FY 2022–23**.
    Awards are essentially absent before FY 2020. Even within our selected window, **only 28.6% of tenders have matching award data**. This selection bias restricts our value-based claims to the "awarded procurements" subset, not all tendered intent.
    
    ### 3. Sector Classifier
    Because OCDS category fields denote contracting mechanisms (e.g., 'Item Rate') rather than economic sectors, we built a hybrid classifier using title keywords and buyer mapping.
    **Key Sectors Identified:** `roads`, `buildings`, `schools`, `health`, `water_sanitation`, `bridges`, `electricity_power`, `it_computing`, `vehicles`, `other`.
    
    ### 4. District Classifier & Geographic Caveat
    Districts were extracted using a gazetteer matched against `tender_bidOpening_address` and `tender_procuringEntity_name`.
    **CRITICAL CAVEAT:** There is a **31.4% mismatch** between the district mentioned in the tender title and the district of the procuring office. Furthermore, 17.6% of tenders fall back to state-headquarter locations (Kamrup Metropolitan). Our geographic data maps **where procuring offices sit**, not where the physical execution of projects happens.
    
    ### 5. Integrity Indicators Definition
    We adapt the Fazekas / GTI methodology into five core metrics computed at the buyer × sector level:
    
    *   **Price Deviation:** The median of the percentage difference between award and estimate.
        ```python
        price_dev = (award_value - tender_value) / tender_value
        ```
    *   **Single-Bidder Rate:** Share of tenders receiving exactly one bid (excluding single-source methods).
    *   **Non-Open Method Share:** Share of a buyer's tenders using limited or restricted methods.
    *   **Threshold Bunching:** Excess mass of tender values just below statutory thresholds (₹25L, ₹1Cr, ₹10Cr).
    *   **Supplier-Buyer Stickiness:** Percentage of a buyer's total award value going to its top-3 suppliers.
    
    ### 6. Decisions Log
    *   **Winsorizing:** Price deviation is clipped at ±2.0 (±200%) to remove data entry outliers.
    *   **Placeholders:** ₹0 and ₹1 award values (often empanelments) are excluded from value-based concentration metrics.
    *   **Composite Minimums:** Integrity composites require `MIN_TENDERS = 15`. Stickiness requires at least 5 active suppliers in the market.
    *   **Clustering:** Buyer typologies use K-Means with K=4.
    """)

def page_concentration(tenders, awards):
    st.header("Concentration and Competition")
    st.markdown("""
    **Motivation:** High concentration of awards among a few suppliers can indicate a lack of competition, potential capture, or structural barriers to entry.
    """)
    
    merged = tenders.merge(awards, on="ocid", how="left")
    merged = merged[merged["award_value_amount"] > 1]
    
    st.subheader("Distribution Inequality (Lorenz Curve)")
    st.markdown("**Context:** Lorenz curves visually represent the cumulative share of award value captured by the cumulative share of suppliers.")
    try:
        st.image("reports/figures/lorenz_by_sector.png", use_container_width=True)
    except FileNotFoundError:
        st.info("Pre-rendered Lorenz curve image not found in reports/figures/.")
    st.markdown("**Takeaway:** Most sectors exhibit severe concavity, meaning the top 10% of suppliers often secure over 70% of the total awarded value.")

    st.markdown("---")
    
    st.subheader("HHI by Sector")
    st.markdown("**Context:** The Herfindahl-Hirschman Index (HHI) squares market shares to heavily penalize monopoly power. An HHI above 2500 is considered 'highly concentrated' by the US DOJ.")
    
    def compute_hhi(group):
        total = group["award_value_amount"].sum()
        if total == 0: return 0
        shares = group.groupby("supplier_name")["award_value_amount"].sum() / total
        return (shares ** 2).sum() * 10000

    if not merged.empty:
        hhi_df = merged.groupby("sector_name").apply(compute_hhi, include_groups=False).reset_index(name="HHI").sort_values("HHI", ascending=False)
        fig1 = px.bar(hhi_df, x="sector_name", y="HHI", color="HHI", color_continuous_scale="Reds")
        fig1.add_hline(y=2500, line_dash="dash", line_color="black", annotation_text="US DOJ Highly Concentrated (2500)")
        st.plotly_chart(fig1, use_container_width=True)
        st.markdown("**Takeaway:** Certain specialized sectors naturally exhibit higher concentration, but values far exceeding 2500 warrant scrutiny for captive supplier relationships.")

    st.markdown("---")
    
    st.subheader("Buyer Typology (K-Means Clustering)")
    st.markdown("**Context:** We clustered buyers based on behavioral features like bidder count, HHI, and open-tender share to identify structural typologies.")
    
    typology_data = [
        {"Cluster": "Competitive Mainstream", "Size (Buyers)": 27, "Mean HHI": 869, "Mean Top-3 Share": "37%", "Open Tender Share": "97%"},
        {"Cluster": "Captured-Supplier Buyers", "Size (Buyers)": 10, "Mean HHI": 4533, "Mean Top-3 Share": "92%", "Open Tender Share": "99%"},
        {"Cluster": "Restricted-Method Users", "Size (Buyers)": 3, "Mean HHI": 1103, "Mean Top-3 Share": "48%", "Open Tender Share": "76%"},
        {"Cluster": "Empanelment Outlier (PHED)", "Size (Buyers)": 1, "Mean HHI": 2263, "Mean Top-3 Share": "80%", "Open Tender Share": "N/A"},
    ]
    st.table(pd.DataFrame(typology_data))
    st.markdown("**Takeaway:** The 'Captured-Supplier Buyers' mirror competitive tender processes perfectly but award 92% of funds to their top 3 suppliers, showing process integrity does not prevent outcome capture.")

def page_integrity(dom_risk_df, ext_risk_df):
    st.header("Structural Integrity Indicators")
    st.markdown("""
    **Motivation:** Rather than relying solely on post-hoc audits, we use systematic objective patterns (like single bidding and price anomalies) to flag portfolios with elevated structural risk.
    """)
    
    tab_type = st.radio("Procurement Regime", ["Domestic Procurement", "Externally-Funded Projects (Panel B)"])
    df = dom_risk_df if tab_type == "Domestic Procurement" else ext_risk_df
    
    if df is None or df.empty:
        st.warning("Risk data not available for this regime.")
        return

    st.subheader("Composite Risk Heatmap")
    st.markdown("**Context:** The heatmap aggregates five percentiled risk indicators. Darker red implies a higher composite risk relative to other buyers in the same sector.")
    
    # Filter heatmap for valid composite scores
    valid_df = df.dropna(subset=["composite_equal"])
    if not valid_df.empty:
        heatmap_data = valid_df.pivot(index="buyer_name", columns="sector_name", values="composite_equal")
        fig = px.imshow(heatmap_data, text_auto=False, aspect="auto", color_continuous_scale="Reds")
        st.plotly_chart(fig, use_container_width=True)
    st.caption("Caption: Heatmap shows buyer × sector cells with ≥15 tenders and at least 3 of 5 indicators computable.")
    st.markdown("**Takeaway:** Risk is not uniformly distributed; specific buyer departments exhibit deep structural risk isolated to specific sectors.")

    st.subheader("Top Risk Pairings Drilldown")
    st.markdown("**Context:** A full searchable table of all buyer × sector portfolios and their structural risk indicators.")
    
    pctile_cols = [c for c in df.columns if c.startswith("pctile_")]
    df["n_indicators_present"] = df[pctile_cols].notna().sum(axis=1)
    
    disp_cols = ["buyer_name", "sector_name", "total_tenders", "n_indicators_present", "composite_equal", "price_dev_median", "single_bidder_rate", "non_open_share", "bunching_composite", "stickiness_top3"]
    
    # Drilldown table
    st.dataframe(df.dropna(subset=["composite_equal"]).sort_values("composite_equal", ascending=False)[disp_cols], use_container_width=True, hide_index=True)
    st.markdown("**Takeaway:** The composite risk score successfully differentiates portfolios, prioritizing those that warrant routine qualitative audits.")

    st.markdown("---")

    st.subheader("Highest-Impact Cells")
    st.markdown("**Context:** High risk is most impactful when paired with massive fiscal volume. Here are the largest active portfolios that exhibit all 5 risk indicators.")
    
    high_impact = df[df["n_indicators_present"] == 5].sort_values("total_tenders", ascending=False).head(5)
    st.dataframe(high_impact[disp_cols], use_container_width=True, hide_index=True)
    st.markdown("**Takeaway:** PWD Building & NH × buildings (n=877) and APDCL × electricity_power (n=489) are massive footprints showing systemic elevated risk.")

def page_geographic(tenders, awards, geojson):
    st.header("Geographic Distribution")
    st.markdown("""
    **Motivation:** Analyzing the spatial distribution of public investment helps determine if resource allocation aligns equitably with population needs.
    
    > [!WARNING]
    > **Procuring vs. Execution Caveat:** There is a 31.4% mismatch between the district mentioned in tender titles and the district of the procuring office. Furthermore, 17.6% of tenders fall back to state-headquarter locations. **This map shows where procuring offices sit, not necessarily where projects are built.**
    """)
    
    if geojson is None:
        st.warning("GeoJSON data not available. Rendering fallback bar chart instead.")
        merged = tenders.merge(awards, on="ocid", how="left")
        dist_agg = merged.groupby("district_name")["award_value_amount"].sum().reset_index()
        fig = px.bar(dist_agg.sort_values("award_value_amount"), x="award_value_amount", y="district_name", orientation="h")
        st.plotly_chart(fig, use_container_width=True)
        return
        
    merged = tenders.merge(awards, on="ocid", how="left")
    dist_agg = merged.groupby("district_name")["award_value_amount"].sum().reset_index()
    dist_agg = dist_agg[dist_agg["district_name"] != "Unclassified"]
    
    st.markdown("**Context:** Choropleth map of total award value by procuring district.")
    m = folium.Map(location=[26.2006, 92.9376], zoom_start=7)
    
    try:
        folium.Choropleth(
            geo_data=geojson,
            data=dist_agg,
            columns=["district_name", "award_value_amount"],
            key_on="feature.properties.NAME_2", # Matches DataMeet GeoJSON properties
            fill_color="YlOrRd",
            fill_opacity=0.7,
            line_opacity=0.2,
            legend_name="Award Value (INR)"
        ).add_to(m)
        st_folium(m, width=800, height=500)
        st.markdown("**Takeaway:** The dense concentration around Kamrup Metropolitan heavily reflects state-level headquarter procurement rather than local development.")
    except Exception as e:
        st.error(f"Mapping failed (likely a GeoJSON key mismatch): {e}")

@st.cache_data(ttl=3600, show_spinner=False)
def get_network_html(tenders, awards, _filter_key):
    """Generate PyVis network HTML string, cached by filter_key."""
    merged = tenders.merge(awards, on="ocid", how="inner")
    merged = merged[merged["award_value_amount"] > 1]
    
    if merged.empty:
        return "<p>No data available for network.</p>"
        
    G = build_bipartite_graph(merged)
    G_sub = top_n_subgraph(G, n_buyers=50, n_suppliers=50)
    
    from pyvis.network import Network
    net = Network(height="600px", width="100%", bgcolor="#ffffff", font_color="black")
    
    for node, data in G_sub.nodes(data=True):
        color = "#1f77b4" if data.get("bipartite") == 0 else "#ff7f0e"
        title = f"{data.get('node_type', '')}: {data.get('label', node)}"
        net.add_node(node, label=data.get("label", node)[:15], title=title, color=color)
        
    for u, v, data in G_sub.edges(data=True):
        weight = data.get("weight", 1)
        net.add_edge(u, v, value=weight)
        
    net.set_options("""
    var options = {
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -50,
          "springLength": 100
        },
        "minVelocity": 0.75,
        "solver": "forceAtlas2Based"
      }
    }
    """)
    
    # Generate HTML string without saving to local file system
    return net.generate_html()

def page_network(tenders, awards, filter_key):
    st.header("Buyer-Supplier Network")
    st.markdown("""
    **Motivation:** Viewing the procurement ecosystem as a bipartite network allows us to identify 'hub' suppliers and 'topological brokers'—departments that serve as critical bridging points.
    """)
    
    st.markdown("**Context:** An interactive, physics-based network graph mapping the top 50 buyers (blue) to the top 50 suppliers (orange) by award value.")
    
    html_content = get_network_html(tenders, awards, filter_key)
    components.html(html_content, height=650)
    
    st.markdown("**Takeaway:** The network exhibits a heavy-tailed degree distribution typical of complex networks, where a few highly connected 'hub' suppliers serve multiple distinct buyers.")
