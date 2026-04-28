import sqlite3
import pandas as pd
import streamlit as st
import json
import sys
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

DB_PATH = Path("db/dsm.sqlite")

@st.cache_data(ttl=3600)
def load_base_data():
    """Load core dataset."""
    conn = sqlite3.connect(DB_PATH)
    tenders = pd.read_sql("""
        SELECT ft.*, db.buyer_name, ds.sector_name, dd.district_name
        FROM fact_tenders ft
        LEFT JOIN dim_buyer db ON ft.buyer_id = db.buyer_id
        LEFT JOIN dim_sector ds ON ft.sector_id = ds.sector_id
        LEFT JOIN dim_district_derived dd ON ft.district_id = dd.district_id
    """, conn)
    
    awards = pd.read_sql("""
        SELECT fa.*, ds.supplier_name
        FROM fact_awards fa
        LEFT JOIN dim_supplier ds ON fa.supplier_canonical_id = ds.supplier_canonical_id
    """, conn)
    conn.close()
    return tenders, awards

@st.cache_data(ttl=3600)
def load_risk_csvs():
    """Load integrity risk metrics directly from pre-computed CSVs."""
    try:
        dom_df = pd.read_csv("outputs/reports_data/buyer_sector_risk_domestic.csv")
        ext_df = pd.read_csv("outputs/reports_data/buyer_sector_risk_external.csv")
        return dom_df, ext_df
    except Exception as e:
        st.error(f"Error loading risk CSVs: {e}")
        return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_assam_geojson():
    """Fetch bundled Assam district GeoJSON."""
    try:
        with open("data/geo/assam.geojson", "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading bundled GeoJSON: {e}")
    return None

def filter_data(tenders, awards, fiscal_years, sectors, districts, buyers, methods):
    """Filter tenders and awards based on selected sidebar options."""
    filtered_tenders = tenders.copy()
    
    if fiscal_years:
        filtered_tenders = filtered_tenders[filtered_tenders["fiscal_year"].isin(fiscal_years)]
    if sectors:
        filtered_tenders = filtered_tenders[filtered_tenders["sector_name"].isin(sectors)]
    if districts:
        filtered_tenders = filtered_tenders[filtered_tenders["district_name"].isin(districts)]
    if buyers:
        filtered_tenders = filtered_tenders[filtered_tenders["buyer_name"].isin(buyers)]
    if methods:
        filtered_tenders = filtered_tenders[filtered_tenders["procurement_method"].isin(methods)]
        
    filtered_ocids = filtered_tenders["ocid"].unique()
    filtered_awards = awards[awards["ocid"].isin(filtered_ocids)]
    
    return filtered_tenders, filtered_awards
