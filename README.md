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

## Generate Formatted Report For LLM (Optional / NEW)

After extracting incident data with the download script, you can generate a professional
Alert Quality Management (AQM) analysis report from the raw CSV. The report generator
performs all analysis at runtime — every table, metric, and finding is computed directly
from the incident export with zero hardcoded content.

The script produces **two outputs**:

1. **A formatted `.docx` report** with data tables, KPI metrics, and template narrative
2. **A structured prompt file (`.md`)** designed to be fed to your LLM of choice for polished
   interpretive paragraphs and prioritized recommendations

This two-stage design keeps the data analysis deterministic and reproducible, while
letting an LLM add the contextual narrative that makes the report worth thousands of
dollars in consulting fees.

### Prerequisites

```bash
pip install pandas python-docx
```

### Usage

```bash
# Basic usage (generates two files alongside the CSV)
python3 generate_aqm_report.py --csv incidents.csv --account "ACME Corp"

# With custom analyst name and output path
python3 generate_aqm_report.py \
  --csv incidents.csv \
  --account "Contoso Financial" \
  --analyst "Jane Doe, Senior Solution Architect" \
  --output reports/Contoso_AQM_Report.docx
```

### Arguments

| Argument    | Required | Default                                      | Description                                               |
|-------------|----------|----------------------------------------------|-----------------------------------------------------------|
| `--csv`     | Yes      | —                                            | Path to the raw NrAiIncident CSV export                   |
| `--account` | Yes      | —                                            | Customer / account display name for the cover page        |
| `--analyst` | No       | `Jim Hagan, Principal Solution Architect`    | Analyst name and title for the cover page                 |
| `--output`  | No       | `AQM_Analysis_{account}.docx`                | Output file path for the docx report                      |

The prompt file is automatically generated alongside the docx with the same base name
and a `_prompt.md` suffix (e.g., `AQM_Analysis_ACME_Corp_prompt.md`).

### Output Files

**The `.docx` report** contains 10 sections and 3 appendices, all data-driven:

| Section | Title                                    | Contents                                                                |
|---------|------------------------------------------|-------------------------------------------------------------------------|
| 1       | Executive Summary                        | KPI metrics, date range, data model verification, severity breakdown    |
| 2       | Noisiest Alert Conditions                | Top 20 conditions by open-event count with target counts and severity   |
| 3       | Noisiest Alert Policies                  | Top 15 policies; condition replication analysis (duplicated names)       |
| 4       | Flappiness Analysis                      | Duration distribution; top 15 flappiest conditions (% under 5 min)      |
| 5       | Re-Open Pattern Analysis                 | Close-to-reopen gap by condition+target; aggregated by condition        |
| 6       | Expiration & VTL Configuration           | VTL distribution, close causes, long-running incident inventory         |
| 7       | Noisiest Entities                        | Top 15 entities (entity.name with targetName fallback)                  |
| 8       | Noisiest Signal Targets                  | Top targets (all, then excluding dominant condition); entity mapping     |
| 9       | Noise by Entity Type                     | Entity type distribution with percentage breakdown                      |
| 10      | Prioritized Recommendations              | Placeholder — populated via the prompt file workflow                    |
| A       | Workshop Session Guide                   | Template agenda for a 2-hour AQM workshop                               |
| B       | Methodology                             | Auto-generated: row counts, date range, event pairing stats             |
| C       | Field Analysis                           | All columns with population rates, types, and top values                |

**The `_prompt.md` file** contains a structured prompt with all analysis results
formatted for an LLM. It includes instructions, terminology guidance, and every data
point the LLM needs to write interpretive paragraphs and generate the Top 10
Recommendations (Section 10). Feed it to your LLM of choice like this:

```bash
# Copy the prompt file contents and paste into your LLM, or:
cat AQM_Analysis_ACME_Corp_prompt.md | pbcopy   # macOS
```

### How It Works

The script runs a deterministic analysis pipeline:

1. **Load & validate** — reads the CSV, verifies required columns
   (`timestamp`, `event`, `incidentId`, `conditionName`, `policyName`,
   `durationSeconds`, `targetName`, `priority`), converts timestamps
2. **Separate events** — splits into open/close sets; pairs by `incidentId`
   to verify lifecycle completeness (both, open-only, close-only counts)
3. **Auto-detect dominant noise source** — identifies the condition with the
   highest open count; if it exceeds 50% of volume, automatically excludes it
   from entity/target/re-open tables to prevent it from obscuring other patterns
4. **Compute noise rankings** — top conditions, policies, entities, and targetNames
5. **Calculate flappiness** — from `durationSeconds` on close events; identifies
   conditions with the highest % of incidents closing under 5 minutes
6. **Detect re-open patterns** — measures close-to-next-open gaps per
   condition+target pair (configurable gap threshold, default 600s / 10 min)
7. **Analyze configuration** — VTL distribution, close causes, signal expiration
   settings, long-running incidents (>12h, >24h)
8. **Profile every field** — population rates, data types, unique counts, top
   values, zero percentages, anomaly flags
9. **Extract severity** — parses SEV1/SEV2/SEV3 from policy naming conventions
10. **Render** — writes the `.docx` report and the `_prompt.md` file

### Input File Format

The script expects a standard NrAiIncident CSV export. Required columns:

```
timestamp, event, incidentId, conditionName, policyName,
durationSeconds, targetName, priority
```

Optional columns used when present (graceful fallback if absent):

```
entity.name, entity.type, entity.guid, conditionId, policyId,
threshold, thresholdDuration, thresholdOccurrences, operator,
nrqlQuery, nrqlEventType, evaluationType, aggregationMethod,
aggregationDuration, fillOption, delay, slideBySeconds,
violationTimeLimitSeconds, expirationDuration,
closeViolationsOnExpiration, openViolationOnExpiration,
closeCause, closeTime, recoveryTime, openTime, muted,
runbookUrl, description, title, signalId, accountId
```

If your export was split into chunks (e.g., via `split`), reassemble first:

```bash
cat incidents_chunk_* > incidents_full.csv
```

### Configuration

Internal constants can be adjusted at the top of the script:

| Constant     | Default    | Purpose                                                      |
|--------------|------------|--------------------------------------------------------------|
| `HEADER_BG`  | `00AC69`   | Table header background color (hex)                          |
| `ROW_ALT_BG` | `E8F8F0`   | Alternating row background color (hex)                       |
| `REOPEN_GAP` | `600`      | Re-open threshold in seconds (incidents closing and re-opening within this window are counted) |
| `MIN_FLAP`   | `20`       | Minimum closed incidents for a condition to appear in the flappiness table |

### Example

```
$ python3 generate_aqm_report.py --csv incidents.csv --account "Contoso Financial"

Loading incidents.csv...
  Rows: 500,000, Incidents: 262,852, Range: 2026-02-05 to 2026-03-30

Analyzing...
Analysis complete.
Report: AQM_Analysis_Contoso_Financial.docx
Prompt: AQM_Analysis_Contoso_Financial_prompt.md

Done! Feed AQM_Analysis_Contoso_Financial_prompt.md to your LLM of choice for narrative polish.
```