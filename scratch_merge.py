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

features = build_buyer_features(val_df, tenders)
filled = features.fillna(features.median())
X = StandardScaler().fit_transform(filled)

km = KMeans(n_clusters=4, n_init=10, random_state=42)
labels = km.fit_predict(X)

unique, counts = np.unique(labels, return_counts=True)
singletons = unique[counts == 1]
for s in singletons:
    idx = np.where(labels == s)[0][0]
    point = X[idx]
    centroids = km.cluster_centers_
    dists = np.linalg.norm(centroids - point, axis=1)
    dists[s] = np.inf
    closest = np.argmin(dists)
    labels[idx] = closest
    print(f"Merged singleton {s} into {closest}")

print("K=4 sizes after merge:", pd.Series(labels).value_counts().to_dict())
