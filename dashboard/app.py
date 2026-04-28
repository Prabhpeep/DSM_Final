import streamlit as st
from data_loader import load_base_data, load_risk_csvs, fetch_assam_geojson, filter_data
from pages_ui import page_overview, page_data_methodology, page_concentration, page_integrity, page_geographic, page_network

st.set_page_config(page_title="Assam Procurement", layout="wide", initial_sidebar_state="expanded")

st.sidebar.title("Global Filters")

with st.spinner("Loading Database..."):
    tenders, awards = load_base_data()
    dom_risk_df, ext_risk_df = load_risk_csvs()
    geojson = fetch_assam_geojson()

# Navigation
page = st.sidebar.radio("Navigation", ["Overview", "Data & Methodology", "Concentration", "Integrity", "Geographic", "Network"])
st.sidebar.markdown("---")

if page in ["Integrity", "Data & Methodology"]:
    st.sidebar.info("Global filters are disabled for this page to preserve pre-computed integrity percentiles and static documentation.")
    # Apply empty filters so full data is passed if needed, though these pages rely on pre-computed or static
    f_years, f_sectors, f_districts, f_buyers, f_methods = [], [], [], [], []
    ft, fa = tenders, awards
else:
    # Sidebar Selection
    f_years = st.sidebar.multiselect("Fiscal Year", options=sorted(tenders["fiscal_year"].dropna().unique()))
    f_sectors = st.sidebar.multiselect("Sector", options=sorted(tenders["sector_name"].dropna().unique()))
    f_districts = st.sidebar.multiselect("District", options=sorted(tenders["district_name"].dropna().unique()))
    f_buyers = st.sidebar.multiselect("Buyer", options=sorted(tenders["buyer_name"].dropna().unique()))
    f_methods = st.sidebar.multiselect("Procurement Method", options=sorted(tenders["procurement_method"].dropna().unique()))

    # Apply filters
    ft, fa = filter_data(tenders, awards, f_years, f_sectors, f_districts, f_buyers, f_methods)

if page == "Overview":
    page_overview(ft, fa)
elif page == "Data & Methodology":
    page_data_methodology()
elif page == "Concentration":
    page_concentration(ft, fa)
elif page == "Integrity":
    page_integrity(dom_risk_df, ext_risk_df)
elif page == "Geographic":
    page_geographic(ft, fa, geojson)
elif page == "Network":
    # Pass filter tuple to cache graph generation efficiently
    filter_key = (tuple(f_years), tuple(f_sectors), tuple(f_districts), tuple(f_buyers), tuple(f_methods))
    page_network(ft, fa, filter_key)
