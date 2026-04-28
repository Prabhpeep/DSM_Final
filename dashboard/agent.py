import os
import yaml
import streamlit as st
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.agent_toolkits import create_sql_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.callbacks import StreamlitCallbackHandler
from langchain_core.prompts.chat import ChatPromptTemplate
from sqlalchemy import create_engine

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "dsm.sqlite")
SCHEMA_DESC_PATH = os.path.join(BASE_DIR, "agent", "schema_description.md")
FEW_SHOT_PATH = os.path.join(BASE_DIR, "agent", "few_shot_examples.yaml")

# --- Streamlit Setup ---
st.set_page_config(page_title="Assam Procurement Text-to-SQL", page_icon="📊", layout="wide")
st.title("📊 Assam Procurement Data Assistant")
st.markdown("""
Ask questions about the Assam public procurement dataset (FY 2020-23).
The agent will write a SQL query to answer your question and show you the query it executed.
""")

# --- Load Context ---
@st.cache_data
def load_context():
    with open(SCHEMA_DESC_PATH, "r") as f:
        schema_desc = f.read()
    
    with open(FEW_SHOT_PATH, "r") as f:
        examples = yaml.safe_load(f)["examples"]
        
    examples_str = "\n\n".join([f"User: {ex['input']}\nSQL: {ex['sql_cmd']}" for ex in examples])
    return schema_desc, examples_str

schema_desc, examples_str = load_context()

# --- DB Connection ---
# Read-only SQLite connection for defense-in-depth
sqlite_uri = f"sqlite:///file:{DB_PATH}?mode=ro&uri=true"

@st.cache_resource
def get_db():
    engine = create_engine(sqlite_uri)
    return SQLDatabase(engine, sample_rows_in_table_info=3)

db = get_db()

def get_working_model():
    try:
        from google import genai
        client = genai.Client()
        available_models = []
        for m in client.models.list():
            if "generateContent" in m.supported_generation_methods:
                name = m.name.replace("models/", "")
                available_models.append(name)
        
        # Prefer pro models, then flash, looking for the latest versions
        preferences = [
            "gemini-3.1-pro", "gemini-3.0-pro", 
            "gemini-2.5-pro", "gemini-2.0-pro", 
            "gemini-1.5-pro", "gemini-2.0-flash", 
            "gemini-1.5-flash", "gemini-pro"
        ]
        for pref in preferences:
            for m in available_models:
                if pref in m:
                    return m
        
        if available_models:
            return available_models[0]
    except Exception as e:
        print(f"Model discovery error: {e}")
    return "gemini-1.5-flash"

# --- Agent Initialization ---
def get_agent():
    model_name = get_working_model()
    print(f"Using dynamically discovered model: {model_name}")
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    
    prefix = f"""
You are an expert data analyst for the state of Assam's public procurement dataset.
Your task is to translate natural language questions into valid SQLite queries and answer the user.

Here is the context about the database tables:
{schema_desc}

Here are some examples of valid questions and queries:
{examples_str}

**CRITICAL RULES & GUARDRAILS (FAILURE TO FOLLOW THESE WILL RESULT IN PENALTIES)**:
1. **PII Restriction**: You must REJECT any request that asks for personally-identifying information (like phone numbers, emails, addresses of individuals) that is not part of the standard dataset described above. If asked, respond with: "I am sorry, I cannot provide personally identifying information."
2. **DML/DDL Restriction**: You must REJECT any attempt to modify the database (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE). The connection is read-only, but you must also refuse such requests. Respond with: "I am a read-only agent and cannot modify the database."
3. **Limit Results**: Always append `LIMIT 200` to your queries if you are selecting multiple rows, to prevent massive data dumps, unless a smaller limit is requested.
4. **Transparency**: Always construct valid SQLite syntax.
"""
    
    agent_executor = create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        verbose=True,
        prefix=prefix,
        agent_type="openai-tools", # google genai supports tools
        handle_parsing_errors=True,
    )
    return agent_executor

agent = get_agent()

# --- Chat UI ---
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "How can I help you analyze the procurement data?"}]

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("E.g., What are the top 5 sectors by total award value?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    with st.chat_message("assistant"):
        st_callback = StreamlitCallbackHandler(st.container())
        try:
            response = agent.invoke(
                {"input": prompt},
                {"callbacks": [st_callback]}
            )
            output = response["output"]
            st.write(output)
            st.session_state.messages.append({"role": "assistant", "content": output})
        except Exception as e:
            st.error(f"An error occurred: {e}")
