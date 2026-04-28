# Chapter A — Concentration Analysis (RQ1) Walkthrough

I have successfully completed the implementation of the concentration analysis module as outlined in the implementation plan. Here is a summary of the work done and the results generated.

## 1. Metrics & Networks Modules
We created two pure Python modules designed to be robust and testable:
- **`src/metrics/concentration.py`**: Computes Herfindahl-Hirschman Index (HHI), Gini coefficients, Lorenz curves, Concentration Ratios (CR4, CR10), and performs K-Means clustering on buyer features.
- **`src/metrics/networks.py`**: Builds the bipartite buyer-supplier graph, computes eigenvector and betweenness centrality (handling disconnected subgraphs), runs Louvain community detection on supplier projections, and extracts subgraphs.

## 2. Orchestration Script
I created an end-to-end Python script `notebooks/03_concentration.py` that queries the database, extracts the necessary metrics, and generates all the visuals. 
*Note: Due to `python-louvain` taking significant time to run on over 6,000 suppliers and nearly 6 million edges, I created this as a Python script first to ensure it could run fully without notebook overhead. It can be easily imported into a Jupyter Notebook if desired.*

## 3. Results and Visualizations
The script generated all the required figures into `reports/figures/`.

### Concentration and Distribution
We mapped the supplier award-value distribution across different sectors. 
![Lorenz Curves by Sector](/Users/prabhpreet16/DSM_Final/reports/figures/lorenz_by_sector.png)

We also built an anonymized view of the top 20 suppliers by award value.
![Top 20 Suppliers by Value](/Users/prabhpreet16/DSM_Final/reports/figures/top20_suppliers_anon.png)

### Bipartite Network Topology
The buyer-supplier network highlights a power-law degree distribution, indicating that a small number of suppliers interact with many buyers, while most suppliers interact with very few.
![Degree Distribution](/Users/prabhpreet16/DSM_Final/reports/figures/degree_distribution.png)

A force-directed network plot of the top 50 buyers and top 50 suppliers visually demonstrates these hub connections.
![Network Top 50](/Users/prabhpreet16/DSM_Final/reports/figures/network_top50.png)

### Buyer Clustering
Using K-Means on features like median tender value, bidder count, and supplier HHI, we grouped buyers into behavioral clusters. The optimal number of clusters (K=7) was chosen using the Silhouette score.
![Buyer Clustering Silhouette](/Users/prabhpreet16/DSM_Final/reports/figures/buyer_cluster_silhouette.png)
![Buyer Clustering PCA](/Users/prabhpreet16/DSM_Final/reports/figures/buyer_clusters_pca.png)

### Community Detection
The Louvain community detection algorithm successfully ran on the supplier projection graph (6,275 nodes, 5.99M edges) and detected 21 communities, highlighting fragmentation and distinct groups of suppliers that bid on similar buyer profiles.
![Supplier Communities](/Users/prabhpreet16/DSM_Final/reports/figures/supplier_communities.png)

## 4. Final Output
A preliminary write-up of these findings was authored in `reports/chapter_a.md`, summarizing the methodology, findings, and addressing the selection bias and data limitations properly per the project guardrails. The network was also exported as `outputs/buyer_supplier_graph.gexf` for use in Gephi.
