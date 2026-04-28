import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import folium
from streamlit_folium import st_folium
import streamlit.components.v1 as components
import sys
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.metrics.concentration import hhi_by_group, gini_by_group
from src.metrics.networks import build_bipartite_graph, top_n_subgraph

def page_overview(tenders, awards):
    st.header("Overview")
    
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
    
    st.markdown("---")
    
    # Top Buyer & Supplier
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Top Buyers by Tenders")
        top_buyers = tenders["buyer_name"].value_counts().head(5).reset_index()
        top_buyers.columns = ["Buyer", "Count"]
        st.dataframe(top_buyers, use_container_width=True, hide_index=True)

    with c2:
        st.subheader("Top Suppliers by Award Value")
        top_suppliers = awards.groupby("supplier_name")["award_value_amount"].sum().sort_values(ascending=False).head(5).reset_index()
        top_suppliers.columns = ["Supplier", "Total Awarded (INR)"]
        top_suppliers["Total Awarded (INR)"] = top_suppliers["Total Awarded (INR)"].apply(lambda x: f"₹ {x/1e7:,.2f} Cr")
        st.dataframe(top_suppliers, use_container_width=True, hide_index=True)


def page_concentration(tenders, awards):
    st.header("Market Concentration")
    
    merged = tenders.merge(awards, on="ocid", how="left")
    merged = merged[merged["award_value_amount"] > 1] # Remove placeholders
    
    if merged.empty:
        st.warning("No award data available for the selected filters.")
        return
        
    # HHI by Sector
    st.subheader("HHI by Sector")
    # Need to group by sector and compute HHI
    # We use src.metrics.concentration.hhi_by_group but simpler is just doing it here to respect filters
    def compute_hhi(group):
        total = group["award_value_amount"].sum()
        if total == 0: return 0
        shares = group.groupby("supplier_name")["award_value_amount"].sum() / total
        return (shares ** 2).sum() * 10000

    hhi_df = merged.groupby("sector_name").apply(compute_hhi, include_groups=False).reset_index(name="HHI")
    hhi_df = hhi_df.sort_values("HHI", ascending=False)
    
    fig1 = px.bar(hhi_df, x="sector_name", y="HHI", title="Herfindahl-Hirschman Index (HHI) by Sector", labels={"sector_name": "Sector"}, color="HHI", color_continuous_scale="Reds")
    st.plotly_chart(fig1, use_container_width=True)
    
    # Top 20 Suppliers
    st.subheader("Top 20 Suppliers")
    top20 = merged.groupby("supplier_name")["award_value_amount"].sum().sort_values(ascending=False).head(20).reset_index()
    top20.columns = ["Supplier Name", "Total Award Value"]
    st.dataframe(top20, use_container_width=True, hide_index=True)


def page_integrity(risk_df):
    st.header("Integrity Risk Indicators")
    st.write("Displays the composite structural risk scores across buyers and sectors. *Note: These are risk indicators, not proof of impropriety.*")
    
    if risk_df is None or risk_df.empty:
        st.warning("Risk data not available.")
        return
        
    st.subheader("Composite Risk Heatmap")
    heatmap_data = risk_df.pivot(index="buyer_name", columns="sector_name", values="composite_equal")
    
    fig = px.imshow(heatmap_data, text_auto=False, aspect="auto", color_continuous_scale="Reds", title="Buyer × Sector Composite Risk Score")
    st.plotly_chart(fig, use_container_width=True)
    
    st.subheader("Top Risk Pairings Drilldown")
    display_df = risk_df[["buyer_name", "sector_name", "composite_equal", "price_dev_median", "single_bidder_rate", "non_open_share", "stickiness_top3"]].dropna(subset=["composite_equal"]).sort_values("composite_equal", ascending=False).head(50)
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def page_geographic(tenders, awards, geojson):
    st.header("Geographic Distribution")
    
    if geojson is None:
        st.warning("GeoJSON data not available. Cannot render map.")
        return
        
    merged = tenders.merge(awards, on="ocid", how="left")
    
    # Aggregate by district
    dist_agg = merged.groupby("district_name").agg(
        Total_Value=("award_value_amount", "sum"),
        Tenders=("ocid", "nunique")
    ).reset_index()
    
    # We filter out 'Unclassified'
    dist_agg = dist_agg[dist_agg["district_name"] != "Unclassified"]
    
    if dist_agg.empty:
        st.warning("No mapped district data for these filters.")
        return
        
    # Map
    m = folium.Map(location=[26.2006, 92.9376], zoom_start=7)
    
    folium.Choropleth(
        geo_data=geojson,
        data=dist_agg,
        columns=["district_name", "Total_Value"],
        key_on="feature.properties.district", # depends on geojson properties
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name="Award Value (INR)"
    ).add_to(m)
    
    st_folium(m, width=800, height=500)
    
    st.subheader("District Breakdown")
    st.dataframe(dist_agg.sort_values("Total_Value", ascending=False), use_container_width=True, hide_index=True)


def page_network(tenders, awards):
    st.header("Buyer-Supplier Network")
    st.write("Top 50 Buyers and Top 50 Suppliers by award value.")
    
    merged = tenders.merge(awards, on="ocid", how="inner")
    merged = merged[merged["award_value_amount"] > 1]
    
    if merged.empty:
        st.warning("No data to build network.")
        return
        
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
    
    path = "dashboard/network.html"
    net.save_graph(path)
    
    HtmlFile = open(path, 'r', encoding='utf-8')
    source_code = HtmlFile.read() 
    components.html(source_code, height=650)
