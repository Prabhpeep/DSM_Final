# Assam Procurement Dashboard

This interactive dashboard visualizes the concentration, integrity, and geographic aspects of public procurement in Assam (FY 2020-2023).

## Setup & Run

1. Ensure the SQLite database `db/dsm.sqlite` is built and present in the project root.
2. Install the required dependencies:
   ```bash
   pip install -r dashboard/requirements.txt
   ```
3. Run the Streamlit application from the project root:
   ```bash
   streamlit run dashboard/app.py
   ```

## Pages
- **Overview:** General procurement KPIs.
- **Concentration:** Market concentration indicators (HHI, Gini, Top-20 suppliers).
- **Integrity:** Structural integrity risk indicators (Fazekas/GTI methodology).
- **Geographic:** District-level distribution of spending.
- **Network:** Interactive buyer-supplier bipartite graph.
