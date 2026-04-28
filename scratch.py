import sqlite3
import pandas as pd
from src.metrics.concentration import build_buyer_features
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import numpy as np

conn = sqlite3.connect("db/dsm.sqlite")
merged = pd.read_sql("SELECT fa.award_value_amount, ft.buyer_id, ft.procurement_method, ft.number_of_tenderers, fa.supplier_canonical_id FROM fact_awards fa JOIN fact_tenders ft ON fa.ocid = ft.ocid WHERE ft.fiscal_year IN ('2020-2021','2021-2022','2022-2023')", conn)
tenders = pd.read_sql("SELECT * FROM fact_tenders WHERE fiscal_year IN ('2020-2021','2021-2022','2022-2023')", conn)
val_df = merged[merged["award_value_amount"] > 1].copy()

MIN_TENDERS_FOR_CLUSTERING = 30
active_buyers = tenders.groupby("buyer_id").size().loc[lambda s: s >= MIN_TENDERS_FOR_CLUSTERING].index
tenders = tenders[tenders["buyer_id"].isin(active_buyers)]
val_df = val_df[val_df["buyer_id"].isin(active_buyers)]

features = build_buyer_features(val_df, tenders)
print(features["mean_bidder_count"].sort_values(ascending=False).head(5))
