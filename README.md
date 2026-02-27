# **New Relic Incident Analyzer (NrAiIncident)**

This Python script, nr-alert-analyzer.py, interacts directly with New Relic's GraphQL API (NerdGraph) to fetch NrAiIncident events. It performs a deep statistical analysis to help Site Reliability Engineers (SREs) and DevOps teams separate "signals from the noise" in their alerting strategy.

The script reports on:

1. **Temporal Patterns:** Identifies if noise is constant or spiking at specific times.  
2. **Severity Breakdown:** The ratio of Critical vs. Warning alerts.  
3. **Root Cause:** Which Alert Policies and specific Conditions are generating the most volume (including Priority).  
4. **Entity Hotspots:** Which specific hosts, apps, or targets are the "noisiest," with a drill-down into exactly *which* conditions are failing on them.  

## **Dependencies**

The script requires the following:

* **Python 3.7+**  
* **pandas**: Used for data aggregation and statistical analysis.  
* **requests**

## **Setup and Installation**

It is highly recommended to run this script within a Python virtual environment to manage dependencies cleanly.

### **1\. Create a Virtual Environment**

From your terminal, navigate to the directory where you saved nr-alert-analyzer.py and create a virtual environment:

\# For macOS and Linux  
python3 \-m venv venv

\# For Windows  
python \-m venv venv

### **2\. Activate the Virtual Environment**

You must activate the environment in your terminal session before installing dependencies or running the script.

\# For macOS and Linux  
source venv/bin/activate

\# For Windows (Command Prompt)  
.\\venv\\Scripts\\activate.bat

\# For Windows (PowerShell)  
.\\venv\\Scripts\\Activate.ps1

Your terminal prompt should change to show (venv) at the beginning.

### **3\. Install Dependencies**

With your virtual environment active, install the required libraries:

pip install pandas requests

## **How to Run**

Run the script from your terminal. You **must** provide your New Relic User API Key and Account ID.

### **Basic Usage (Last 7 Days)**

By default, the script analyzes the last 7 days of data.

python nr-alert-analyzer.py \--api\_key "NRAK-YOUR-KEY" \--account\_id 1234567

### **Specifying a Time Window**

You can define a custom window using YYYY-MM-DD HH:MM:SS format.

python nr-alert-analyzer.py \\  
  \--api\_key "NRAK-..." \\  
  \--account\_id 1234567 \\  
  \--start\_time "2023-10-01 00:00:00" \\  
  \--end\_time "2023-10-02 00:00:00"


## **Command-Line Arguments**

| Argument | Required | Description | Default |
| :---- | :---- | :---- | :---- |
| \--api\_key | **Yes** | Your New Relic User Key (starts with NRAK-). | None |
| \--account\_id | **Yes** | The New Relic Account ID to query. | None |
| \--start\_time | No | Start of analysis window (YYYY-MM-DD HH:MM:SS). | 7 days ago |
| \--end\_time | No | End of analysis window (YYYY-MM-DD HH:MM:SS). | Now (UTC) |

## **Interpreting the Output**

The script prints its analysis directly to the terminal in specific sections.

### **1\. Data Fetching**

Confirms the connection to New Relic and the number of events fetched.

* *Note: The script currently fetches a maximum of 2,000 incidents per query.*

### **2\. Temporal Analysis**

Helps you distinguish between "always on" noise and "acute" incidents.

* **Daily Breakdown:** Shows incident volume per day.  
* **Temporal Peak:** Identifies the specific hour of the day with the highest volume.

### **3\. Severity Analysis**

Shows the ratio of **Critical** vs. **Warning** violations.

* *Tip: If you have 90% Warnings, your alert thresholds are likely too sensitive.*

### **4\. Source / Root Cause Analysis**

This groups alerts by **Policy**, **Condition**, and **Priority**.

* **What it finds:** The specific configuration rules that are generating the most noise.  
* **Example:** \[150\] Priority: critical | Policy: 'Database' \-\> Condition: 'High CPU'

### **5\. Related Entity Analysis**

This groups alerts by the **Entity** (Target Name).

* **What it finds:** Specific hosts, pods, or applications that are failing.  
* **Nested Detail:** Under each entity, it lists the specific conditions triggering on that host.  
  * *Example:* host-prod-01 might be triggering "High CPU" (Critical) and "Disk Full" (Warning) simultaneously.

