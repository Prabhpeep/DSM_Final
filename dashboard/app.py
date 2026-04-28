import streamlit as st
from data_loader import load_base_data, load_risk_data, fetch_assam_geojson, filter_data
from pages_ui import page_overview, page_concentration, page_integrity, page_geographic, page_network

st.set_page_config(page_title="Assam Procurement", layout="wide", initial_sidebar_state="expanded")

st.sidebar.title("Global Filters")

with st.spinner("Loading Database..."):
    tenders, awards = load_base_data()
    risk_df = load_risk_data()
    geojson = fetch_assam_geojson()

# Sidebar Selection
f_years = st.sidebar.multiselect("Fiscal Year", options=sorted(tenders["fiscal_year"].dropna().unique()))
f_sectors = st.sidebar.multiselect("Sector", options=sorted(tenders["sector_name"].dropna().unique()))
f_districts = st.sidebar.multiselect("District", options=sorted(tenders["district_name"].dropna().unique()))
f_buyers = st.sidebar.multiselect("Buyer", options=sorted(tenders["buyer_name"].dropna().unique()))
f_methods = st.sidebar.multiselect("Procurement Method", options=sorted(tenders["procurement_method"].dropna().unique()))

# Apply filters
ft, fa = filter_data(tenders, awards, f_years, f_sectors, f_districts, f_buyers, f_methods)

frisk = risk_df.copy()
if f_sectors: frisk = frisk[frisk["sector_name"].isin(f_sectors)]
if f_buyers: frisk = frisk[frisk["buyer_name"].isin(f_buyers)]

st.sidebar.markdown("---")
page = st.sidebar.radio("Navigation", ["Overview", "Concentration", "Integrity", "Geographic", "Network"])

if page == "Overview":
    page_overview(ft, fa)
elif page == "Concentration":
    page_concentration(ft, fa)
elif page == "Integrity":
    page_integrity(frisk)
elif page == "Geographic":
    page_geographic(ft, fa, geojson)
elif page == "Network":
    page_network(ft, fa)
