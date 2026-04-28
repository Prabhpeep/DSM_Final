# Text-to-SQL Agent Implementation Walkthrough

The Text-to-SQL agent is now implemented and ready to be used as part of your Streamlit dashboard for querying the Assam procurement dataset!

## What We Built

### 1. Schema Context
- Generated `agent/schema_description.md` which breaks down the `fact_tenders`, `fact_awards`, and dimension tables so the LLM knows how to properly filter and join.
- Provided specific instructions on calculating complex fields (like Single-Bidder Rate vs. Price Deviation).

### 2. Few-Shot Examples
- Created `agent/few_shot_examples.yaml` which teaches the LLM how to write valid SQLite queries for typical analytical questions you might ask.
- Includes patterns for finding top suppliers, calculating single bidder rates within specific sectors, and finding total award values.

### 3. Streamlit Chat UI (`dashboard/agent.py`)
- We implemented a complete Streamlit chat interface wrapping LangChain's `create_sql_agent` and the `SQLDatabaseToolkit`.
- We used `ChatGoogleGenerativeAI` targeting `gemini-1.5-pro` (as you requested a Gemini model previously).
- **Transparency**: We used `StreamlitCallbackHandler` to render the intermediate SQL queries the agent writes and executes before outputting the final natural-language response.
- **Guardrails Implemented**: 
  1. The LLM is strictly instructed to reject PII requests.
  2. The LLM is strictly instructed to reject any DB mutations (DDL/DML). 
  3. In addition to prompt guardrails, we connect to the database via `sqlite:///file:../db/dsm.sqlite?mode=ro&uri=true`, ensuring a hard read-only block at the connection level.
  4. The LLM is instructed to append `LIMIT 200` to prevent dumping large tables into the context window.

## How to Run the App

1. Ensure your Gemini API Key is loaded in your environment:
   ```bash
   export GOOGLE_API_KEY="your-api-key"
   ```
2. Start the Streamlit app:
   ```bash
   streamlit run dashboard/agent.py
   ```
3. Ask it questions like *"Which buyers have the highest single-bidder rate in construction?"* or *"What are the top 5 sectors by total award value?"*.

## Visual Walkthrough

Here is a demo of the agent answering a question about top sectors, generating the correct SQL query, and returning the aggregated totals:

![Agent Demo Screenshot](/Users/prabhpreet16/DSM_Final/reports/figures/agent_demo.png)

> [!TIP]
> The agent is designed to complement the pre-computed views in your final report. If you notice any queries are running slow or are incorrect, you can iteratively improve the system by adding more edge-case queries to `agent/few_shot_examples.yaml`.
