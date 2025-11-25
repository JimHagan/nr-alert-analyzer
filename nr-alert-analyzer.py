"""
New Relic Alert Analyzer (nr-alert-analyzer.py)

Description:
This script interacts with New Relic's GraphQL API (NerdGraph) to fetch 
NrAiIncident events and provides a deep analysis of patterns by temporal 
distribution, severity, root cause, and related entities.

It mirrors the "look and feel" of the attribute-analyzer, including 
optional Gemini integration for natural language SRE insights.

Dependencies:
    pip install pandas requests

Usage:
    python nr-alert-analyzer.py --api_key "NRAK-..." --account_id 12345
    python nr-alert-analyzer.py ... --show_top_n 20
    python nr-alert-analyzer.py ... --analyze_with_gemini --gemini_api_key "..."
    
    # To send ONLY the summary (lighter payload):
    python nr-alert-analyzer.py ... --analyze_with_gemini --gemini_summary_only
"""

import argparse
import requests
import pandas as pd
import json
import time
from datetime import datetime, timedelta
import textwrap

# --- Configuration & Constants ---
NEW_RELIC_GRAPHQL_URL = "https://api.newrelic.com/graphql"
# EU Endpoint: "https://api.eu.newrelic.com/graphql"

# Helper to print styled headers
def print_header(title):
    print("\n" + ("-" * 60))
    print(f"### {title.upper()} ###")
    print(("-" * 60) + "\n")

# --- GraphQL Functions ---

def build_nrql_query(account_id, start_time, end_time):
    """
    Constructs the GraphQL payload to fetch NrAiIncident data via NRQL.
    """
    # Note: LIMIT 2000 is the standard max for NRQL. 
    # For production use on massive datasets, you might need time-window partitioning.
    nrql = (
        f"SELECT * FROM NrAiIncident "
        f"SINCE '{start_time}' UNTIL '{end_time}' "
        f"LIMIT 2000"
    )
    
    # GraphQL Query Structure
    # FIXED: Changed $nrqlQuery type from String! to Nrql! to match schema requirements
    query = """
    query ($accountId: Int!, $nrqlQuery: Nrql!) {
      actor {
        account(id: $accountId) {
          nrql(query: $nrqlQuery) {
            results
          }
        }
      }
    }
    """
    
    variables = {
        "accountId": int(account_id),
        "nrqlQuery": nrql
    }
    
    return {"query": query, "variables": variables}

def fetch_incidents(api_key, account_id, start_time, end_time):
    """
    Executes the GraphQL request to New Relic.
    """
    print(f"  Fetching incidents from Account {account_id}...")
    print(f"  Window: {start_time} to {end_time}")
    
    headers = {
        "Content-Type": "application/json",
        "API-Key": api_key
    }
    
    payload = build_nrql_query(account_id, start_time, end_time)
    
    try:
        response = requests.post(NEW_RELIC_GRAPHQL_URL, json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            
            # Check for GraphQL errors
            if 'errors' in data:
                print("\nError in GraphQL response:")
                print(json.dumps(data['errors'], indent=2))
                return None
                
            # Navigate the JSON response to get the list of events
            try:
                results = data['data']['actor']['account']['nrql']['results']
                return results
            except KeyError as e:
                print(f"\nUnexpected response structure: {e}")
                return None
        else:
            print(f"\nAPI Request failed with status {response.status_code}: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"\nNetwork error occurred: {e}")
        return None

# --- Analysis Functions ---

def analyze_temporal(df):
    """
    Analyzes incidents by time (Day and Hour).
    """
    print_header("Temporal Analysis")
    
    # Ensure timestamp is datetime
    if 'timestamp' in df.columns:
        # NR timestamps are often in milliseconds
        df['dt'] = pd.to_datetime(df['timestamp'], unit='ms')
    else:
        print("Timestamp column missing. Skipping temporal analysis.")
        return ""

    # 1. Daily Breakdown
    daily_counts = df.groupby(df['dt'].dt.date).size()
    print("**Incidents by Day:**")
    if daily_counts.empty:
        print("  No data.")
    else:
        for date, count in daily_counts.items():
            print(f"  {date}: {count}")

    # 2. Hourly Heatmap (Top 5 busiest hours)
    df['hour'] = df['dt'].dt.hour
    hourly_counts = df['hour'].value_counts().sort_index()
    
    # Find peak hours
    peak_hours = df['hour'].value_counts().nlargest(3)
    
    summary_lines = [
        f"Temporal peak: {peak_hours.index[0]}:00 had {peak_hours.iloc[0]} incidents" if not peak_hours.empty else "No temporal data"
    ]
    
    return "\n".join(summary_lines)

def analyze_severity(df):
    """
    Analyzes incidents by severity/priority.
    """
    print_header("Severity Analysis")
    
    if 'priority' not in df.columns:
        print("Priority column missing.")
        return "Severity info missing."

    severity_counts = df['priority'].value_counts()
    total = len(df)
    
    print(f"**Breakdown (Total: {total}):**")
    summary_lines = []
    
    for priority, count in severity_counts.items():
        pct = (count / total) * 100
        print(f"  * {priority}: {count} ({pct:.1f}%)")
        summary_lines.append(f"{priority}: {count} ({pct:.1f}%)")
        
    return ", ".join(summary_lines)

def analyze_root_cause(df, top_n=10):
    """
    Analyzes by Policy, Condition, and Priority to find the configuration source of noise.
    """
    print_header("Source / Root Cause Analysis")
    
    # Added 'priority' to the grouping columns so we can distinguish Critical vs Warning
    cols = ['policyName', 'conditionName', 'priority']
    available_cols = [c for c in cols if c in df.columns]
    
    if not available_cols:
        print("Policy/Condition columns missing.")
        return "Root cause info missing."
    
    # Group by Policy + Condition + Priority
    grouped = df.groupby(available_cols).size().reset_index(name='count')
    grouped = grouped.sort_values('count', ascending=False).head(top_n)
    
    print(f"**Top {top_n} Triggering Conditions:**")
    summary_lines = []
    
    for idx, row in grouped.iterrows():
        policy = row.get('policyName', 'N/A')
        condition = row.get('conditionName', 'N/A')
        priority = row.get('priority', 'N/A')
        count = row['count']
        
        # Updated print format to include Priority
        print(f"  {idx + 1}. [{count}] Priority: {priority} | Policy: '{policy}' -> Condition: '{condition}'")
        
        # Keep the summary for Gemini concise, but include the major hitters
        # If list is very long, we might want to cap summary, but typically Top N is fine.
        summary_lines.append(f"[{priority}] Policy '{policy}' / Condition '{condition}' ({count} times)")

    return "\n".join(summary_lines)

def analyze_entities(df, top_n=10):
    """
    Analyzes by Entity (Target) and shows associated conditions/priorities.
    """
    print_header("Related Entity Analysis")
    
    # Check for entity columns (entity.name, entityName, targetName)
    possible_cols = ['entity.name', 'targetName', 'entityName']
    target_col = next((c for c in possible_cols if c in df.columns), None)
    
    if not target_col:
        print("No entity/target name column found.")
        return "Entity info missing."
        
    # Get top N entities
    top_entities = df[target_col].value_counts().head(top_n)
    
    print(f"**Top {top_n} Noisiest Entities ({target_col}):**")
    summary_lines = []
    
    for entity, total_count in top_entities.items():
        print(f"  * {entity}: {total_count}")
        summary_lines.append(f"Entity: {entity} (Total: {total_count})")
        
        # Drill down: Find conditions for this specific entity
        entity_df = df[df[target_col] == entity]
        
        # Define grouping columns (Condition + Priority)
        group_cols = []
        if 'conditionName' in df.columns: group_cols.append('conditionName')
        if 'priority' in df.columns: group_cols.append('priority')
        
        if group_cols:
            # Get top 5 conditions for this entity
            sub_counts = entity_df.groupby(group_cols).size().sort_values(ascending=False).head(5)
            
            for idx, count in sub_counts.items():
                # Handle grouping index (tuple vs scalar)
                if isinstance(idx, tuple):
                    # Unpack based on length (Condition, Priority)
                    cond = idx[0]
                    prio = idx[1] if len(idx) > 1 else "N/A"
                else:
                    cond = idx
                    prio = "N/A"
                
                # Print indented breakdown
                print(f"      - [{prio}] {cond}: {count}")
                
                # Add to summary string for Gemini
                summary_lines.append(f"    - Condition: '{cond}' [{prio}] ({count})")

    return "\n".join(summary_lines)

# --- Gemini Integration ---

def generate_gemini_prompt(df, total_events, temporal_sum, severity_sum, source_sum, entity_sum, include_full_dump=True):
    """
    Prepares the prompt context.
    """
    summary = []
    summary.append(f"Analysis of {total_events} New Relic incidents.\n")
    summary.append(f"--- Temporal Patterns ---\n{temporal_sum}")
    summary.append(f"--- Severity Breakdown ---\n{severity_sum}")
    summary.append(f"--- Top Root Causes (Policy/Condition) ---\n{source_sum}")
    summary.append(f"--- Top Noisiest Entities & Details ---\n{entity_sum}")
    
    if include_full_dump:
        # --- PARED-DOWN DATASET LOGIC ---
        # Instead of sending everything, we select specific columns requested to save tokens.
        
        # 1. Base columns
        cols_to_keep = [
            'timestamp', 
            'policyName', 
            'conditionName', 
            'runbookUrl', 
            'priority',   # <--- Criticality/Severity (Critical vs Warning)
            'event',      # <--- Status (Open vs Close)
            'title'
        ]
        
        # 2. Entity Name (Best effort match)
        for entity_col in ['targetName', 'entity.name', 'entityName']:
            if entity_col in df.columns:
                cols_to_keep.append(entity_col)
                break
        
        # 3. Notification Info (channelIds is the closest match in NrAiIncident)
        if 'channelIds' in df.columns:
            cols_to_keep.append('channelIds')
            
        # 4. Tags (Any column starting with 'tags.' or named 'tags')
        tag_cols = [c for c in df.columns if c.startswith('tags.') or c == 'tags']
        cols_to_keep.extend(tag_cols)
        
        # Filter DataFrame to only existing columns
        existing_cols = [c for c in cols_to_keep if c in df.columns]
        slim_df = df[existing_cols].copy()
        
        # Convert filtered data to JSON
        json_dump = slim_df.to_json(orient='records', date_format='iso', default_handler=str)
        summary.append(f"\n--- PARED-DOWN INCIDENT DATA (JSON) ---\n{json_dump}")
        
    else:
        # Add a few example titles for context if not dumping everything
        if 'title' in df.columns:
            examples = df['title'].head(5).tolist()
            summary.append(f"--- Example Incident Titles ---\n{examples}")
        
    return "\n".join(summary)

def call_gemini(summary_text, api_key):
    """
    Calls the Gemini API for natural language analysis.
    """
    print_header("Gemini Deep Analysis")
    print("  Sending data to Gemini API (model: gemini-2.5-flash-preview-09-2025)...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={api_key}"
    
    system_prompt = (
        "You are a Senior SRE and Observability Expert. "
        "Analyze the provided New Relic incident summary and raw data. "
        "Identify the 'signals from the noise'. "
        "1. Highlight if this is a systemic issue (policy configuration) or an acute outage (temporal spike). "
        "2. Look for correlations in the raw data (e.g., did multiple entities fail at the exact same timestamp?). "
        "3. Recommend specific actions to reduce alert fatigue based on the top contributors. "
        "4. Categorize the findings into 'Urgent', 'Cleanup Required', or 'FYI'. "
    )
    
    payload = {
        "contents": [{"parts": [{"text": "Analyze this incident report:\n" + summary_text}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]}
    }
    
    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        if response.status_code == 200:
            result = response.json()
            analysis = result['candidates'][0]['content']['parts'][0]['text']
            print("\n" + analysis)
        else:
            print(f"Gemini API Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Failed to call Gemini: {e}")

# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="New Relic Alert Analyzer")
    
    # Required/Core Arguments
    parser.add_argument("--api_key", required=True, help="New Relic User API Key (NRAK-...)")
    parser.add_argument("--account_id", required=True, help="New Relic Account ID")
    
    # Time Window (Optional)
    # Defaults to 7 days ago -> Now
    default_end = datetime.utcnow()
    default_start = default_end - timedelta(days=7)
    
    parser.add_argument("--start_time", default=default_start.strftime("%Y-%m-%d %H:%M:%S"),
                        help="Start time (YYYY-MM-DD HH:MM:SS). Default: 7 days ago.")
    parser.add_argument("--end_time", default=default_end.strftime("%Y-%m-%d %H:%M:%S"),
                        help="End time (YYYY-MM-DD HH:MM:SS). Default: Now.")

    # Reporting Options
    parser.add_argument("--show_top_n", type=int, default=10,
                        help="Number of top items to show for conditions and entities (10-100). Default: 10.")

    # Gemini Flags
    parser.add_argument("--analyze_with_gemini", action="store_true", 
                        help="Send data to Gemini for AI analysis.")
    parser.add_argument("--gemini_api_key", help="Google Gemini API Key.")
    
    # NEW Flag: Option to send only summary
    parser.add_argument("--gemini_summary_only", action="store_true",
                        help="If set, only sends the statistical summary to Gemini (excludes the full raw data dump).")

    args = parser.parse_args()

    # validate gemini key if flag is present
    if args.analyze_with_gemini and not args.gemini_api_key:
        print("Error: --analyze_with_gemini requires --gemini_api_key.")
        return

    # Validate show_top_n
    if not (10 <= args.show_top_n <= 100):
        print("Error: --show_top_n must be between 10 and 100.")
        return

    # 1. Fetch Data
    print_header("Data Fetching")
    results = fetch_incidents(args.api_key, args.account_id, args.start_time, args.end_time)
    
    if not results:
        print("No data found or API error.")
        return

    # 2. Convert to Pandas
    df = pd.DataFrame(results)
    total_events = len(df)
    print(f"  Successfully loaded {total_events} incidents.")
    
    if total_events == 0:
        return

    # 3. Run Analysis
    temp_sum = analyze_temporal(df)
    sev_sum = analyze_severity(df)
    root_sum = analyze_root_cause(df, args.show_top_n)
    ent_sum = analyze_entities(df, args.show_top_n)

    # 4. Gemini Integration
    if args.analyze_with_gemini:
        # Determine if we send full dump (default yes, unless flag set)
        send_full_dump = not args.gemini_summary_only
        
        if send_full_dump:
            print("  Preparing pared-down incident dump for Gemini (Condition, Policy, Entity, etc.)...")
        else:
            print("  Preparing statistical summary for Gemini...")

        summary_text = generate_gemini_prompt(
            df, total_events, temp_sum, sev_sum, root_sum, ent_sum, 
            include_full_dump=send_full_dump
        )
        call_gemini(summary_text, args.gemini_api_key)

    print_header("Done")

if __name__ == "__main__":
    main()