import subprocess
import time
import os
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE_DIR, "reports", "figures")
os.makedirs(REPORT_DIR, exist_ok=True)

# Start Streamlit
process = subprocess.Popen(["streamlit", "run", "dashboard/agent.py", "--server.port", "8502", "--server.headless", "true"])

# Wait for Streamlit to start
time.sleep(10)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://localhost:8502")
        time.sleep(5) # Wait for page to load
        
        # Take a screenshot
        page.screenshot(path=os.path.join(REPORT_DIR, "agent_demo.png"))
        browser.close()
        print("Screenshot saved to reports/figures/agent_demo.png")
except Exception as e:
    print(f"Error: {e}")
finally:
    process.terminate()
