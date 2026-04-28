# Assam Procurement Dashboard

This project analyzes Assam's public procurement data from FY 2020-23, using the CivicDataLab OCDS dataset to map market concentration and compute structural integrity indicators based on the Government Transparency Institute methodology. The dashboard serves as a guided narrative to explore these findings interactively.

## Local Run Instructions

1. Ensure you have the SQLite database `db/dsm.sqlite` and the reports in `reports/` built.
2. Install dependencies:
   ```bash
   pip install -r dashboard/requirements.txt
   ```
3. Run the Streamlit app:
   ```bash
   streamlit run dashboard/app.py
   ```

## Streamlit Cloud Deployment

To deploy on Streamlit Cloud:
- Point it at this repository and the `main` branch.
- Set the entry point to `dashboard/app.py`.
- Set the requirements file path to `dashboard/requirements.txt` (or Streamlit will automatically find it).
- URL: [Placeholder for live URL]
