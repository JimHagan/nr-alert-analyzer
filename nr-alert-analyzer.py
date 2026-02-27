"""
New Relic Alert Analyzer (nr-alert-analyzer.py)

Description:
This script interacts with New Relic's GraphQL API (NerdGraph) to fetch 
NrAiIncident events and provides a deep analysis of patterns by temporal 
distribution, severity, root cause, and related entities.

Dependencies:
    pip install pandas requests

 -:
    python nr-alert-analyzer.py --api_key "NRAK-..." --account_id 12345
    
    # By default, WARNINGs are excluded. To include them:
    python nr-alert-analyzer.py ... --include_warnings
    
    # Adjust the fetch limit (Default: 100000)
    python nr-alert-analyzer.py ... --limit 100000
    
    python nr-alert-analyzer.py ... --show_top_n 20
 
"""

import argparse
import requests
import pandas as pd
import json
import time
from datetime import datetime, timedelta
import textwrap
import io
import contextlib

# --- Configuration & Constants ---
NEW_RELIC_GRAPHQL_URL = "https://api.newrelic.com/graphql"
# EU Endpoint: "https://api.eu.newrelic.com/graphql"

# Helper to print styled headers
def print_header(title):
    print("\n" + ("-" * 60))
    print(f"### {title.upper()} ###")
    print(("-" * 60) + "\n")


# --- Interactive API Key Selection ---

def load_api_keys_from_config():
    """
    Loads API keys from a 'config.json' file in the same directory.
    """
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
            return config.get("api_keys", {})
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print("Warning: 'config.json' is not a valid JSON file.")
        return {}

def select_api_key_interactively(api_keys):
    """
    Prompts the user to select an API key from a list.
    """
    if not api_keys:
        return None

    print("\nPlease select an API key to use:")
    key_names = list(api_keys.keys())
    for i, name in enumerate(key_names):
        print(f"  {i + 1}. {name}")

    while True:
        try:
            choice = input(f"\nEnter a number (1-{len(key_names)}): ")
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(key_names):
                selected_key_name = key_names[choice_idx]
                return api_keys[selected_key_name]
            else:
                print("Invalid choice. Please enter a number from the list.")
        except (ValueError, IndexError):
            print("Invalid input. Please enter a number.")


def list_accounts(api_key):
    """
    Fetches and lists all accounts accessible by the given API key.
    """
    print_header("Fetching Accessible Accounts")
    
    query = """
    {
      actor {
        accounts {
          id
          name
        }
      }
    }
    """
    
    payload = {"query": query}
    data = run_graphql_query(api_key, payload)
    
    if not data:
        print("Failed to fetch accounts.")
        return
        
    try:
        if 'errors' in data:
            print(f"GraphQL Error: {json.dumps(data['errors'], indent=2)}")
            return
            
        accounts = data.get('data', {}).get('actor', {}).get('accounts', [])
        
        if not accounts:
            print("No accounts found for this API key.")
            return
            
        print("**Available Accounts:**")
        for acc in accounts:
            print(f"  - Name: {acc['name']}, ID: {acc['id']}")
            
    except (KeyError, TypeError, AttributeError) as e:
        print(f"Unexpected response structure: {e}")
        print(f"Response data dump: {json.dumps(data, indent=2)}")

def get_account_name(api_key, account_id):
    """
    Fetches the account name for a specific account ID and standardizes it 
    for use as a file prefix (uppercase, spaces replaced with underscores).
    """
    query = """
    query ($accountId: Int!) {
      actor {
        account(id: $accountId) {
          name
        }
      }
    }
    """
    variables = {"accountId": int(account_id)}
    payload = {"query": query, "variables": variables}
    
    data = run_graphql_query(api_key, payload)
    try:
        name = data.get('data', {}).get('actor', {}).get('account', {}).get('name')
        if name:
            return name.replace(" ", "_").upper()
    except (KeyError, TypeError, AttributeError):
        pass
    
    return f"ACCOUNT_{account_id}"

# --- GraphQL Functions ---

def run_graphql_query(api_key, payload):
    """
    Helper to run the actual HTTP post to GraphQL.
    """
    headers = {
        "Content-Type": "application/json",
        "API-Key": api_key
    }
    try:
        response = requests.post(NEW_RELIC_GRAPHQL_URL, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"\nAPI Request failed with status {response.status_code}: {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"\nNetwork error occurred: {e}")
        return None

def fetch_incidents(api_key, account_id, start_time, end_time, exclude_warnings=False, limit=10000):
    """
    Executes the GraphQL request using Key-Set Pagination (Time Walking).
    """
    print(f"  Fetching incidents from Account {account_id}...")
    print(f"  Window: {start_time} to {end_time}")
    print(f"  Target Limit: {limit} incidents")
    
    if exclude_warnings:
        print("  Filter: Excluding 'warning' priority incidents.")
    else:
        print("  Filter: Including ALL priorities.")

    all_incidents = []
    BATCH_SIZE = 2000
    current_until = end_time
    base_where = "priority != 'warning'" if exclude_warnings else "true"
    
    while len(all_incidents) < limit:
        remaining = limit - len(all_incidents)
        fetch_size = min(remaining, BATCH_SIZE)
        
        nrql = (
            f"SELECT * FROM NrAiIncident "
            f"WHERE {base_where} "
            f"SINCE '{start_time}' UNTIL '{current_until}' "
            f"LIMIT {fetch_size}"
        )
        # print(nrql)
        
        query_payload = """
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
        
        variables = {"accountId": int(account_id), "nrqlQuery": nrql}
        payload = {"query": query_payload, "variables": variables}
        
        print(f"    ...Fetching batch (Size: {fetch_size}) UNTIL {current_until}...")
        data = run_graphql_query(api_key, payload)
        
        if not data:
            break
            
        try:
            if 'errors' in data:
                print(f"\n    GraphQL Error: {json.dumps(data['errors'], indent=2)}")
                break
                
            results = data.get('data', {}).get('actor', {}).get('account', {}).get('nrql', {}).get('results')
        except (KeyError, TypeError, AttributeError) as e:
            print(f"\n    Unexpected structure: {e}")
            break
            
        if not results:
            break
            
        all_incidents.extend(results)
        if len(results) < fetch_size or len(all_incidents) >= limit:
            break
            
        last_timestamp = results[-1].get('timestamp')
        if last_timestamp:
            try:
                dt_obj = datetime.fromtimestamp(last_timestamp / 1000.0)
                current_until = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                break
        else:
            break
            
    return all_incidents

# --- Analysis Functions ---

def analyze_temporal(df):
    """Analyzes incidents by time."""
    print_header("Temporal Analysis")
    if 'timestamp' in df.columns:
        df['timestamp_num'] = pd.to_numeric(df['timestamp'], errors='coerce')
        df['dt'] = pd.to_datetime(df['timestamp_num'], unit='ms')
    else:
        return ""

    daily_counts = df.groupby(df['dt'].dt.date).size()
    print("**Incidents by Day:**")
    for date, count in daily_counts.items():
        print(f"  {date}: {count}")

    df['hour'] = df['dt'].dt.hour
    peak_hours = df['hour'].value_counts().nlargest(3)
    summary = f"Temporal peak: {peak_hours.index[0]}:00 with {peak_hours.iloc[0]} events" if not peak_hours.empty else ""
    return summary

def analyze_severity(df):
    """Analyzes severity/priority."""
    print_header("Severity Analysis")
    if 'priority' not in df.columns:
        return ""
    severity_counts = df['priority'].value_counts()
    total = len(df)
    summary_lines = []
    for priority, count in severity_counts.items():
        pct = (count / total) * 100
        print(f"  * {priority}: {count} ({pct:.1f}%)")
        summary_lines.append(f"{priority}: {pct:.1f}%")
    return ", ".join(summary_lines)

def analyze_root_cause(df, top_n=10):
    """Analyzes configuration source."""
    print_header("Source / Root Cause Analysis")
    cols = ['policyName', 'conditionName', 'priority']
    available_cols = [c for c in cols if c in df.columns]
    if not available_cols:
        return ""
    
    grouped = df.groupby(available_cols).size().reset_index(name='count')
    grouped = grouped.sort_values('count', ascending=False).head(top_n)
    
    summary_lines = []
    for idx, row in grouped.iterrows():
        p, c, pr = row.get('policyName', 'N/A'), row.get('conditionName', 'N/A'), row.get('priority', 'N/A')
        count = row['count']
        print(f"  {idx + 1}. [{count}] {pr} | Policy: '{p}' -> Condition: '{c}'")
        summary_lines.append(f"[{pr}] '{p}' / '{c}' ({count})")
    return "\n".join(summary_lines)

def analyze_entities(df, top_n=10):
    """Analyzes by Entity."""
    print_header("Related Entity Analysis")
    possible_cols = ['entity.name', 'targetName', 'entityName']
    target_col = next((c for c in possible_cols if c in df.columns), None)
    if not target_col:
        return ""
        
    top_entities = df[target_col].value_counts().head(top_n)
    summary_lines = []
    for entity, total_count in top_entities.items():
        print(f"  * {entity}: {total_count}")
        summary_lines.append(f"Entity: {entity} ({total_count})")
        entity_df = df[df[target_col] == entity]
        group_cols = [c for c in ['conditionName', 'priority'] if c in df.columns]
        if group_cols:
            sub_counts = entity_df.groupby(group_cols).size().sort_values(ascending=False).head(5)
            for idx, count in sub_counts.items():
                cond = idx[0] if isinstance(idx, tuple) else idx
                prio = idx[1] if isinstance(idx, tuple) and len(idx) > 1 else "N/A"
                print(f"      - [{prio}] {cond}: {count}")
                summary_lines.append(f"    - {cond} [{prio}] ({count})")
    return "\n".join(summary_lines)

def generate_advanced_report(df, filename):
    """
    Generates report.txt with SRE deep-dive metrics: flappiness, redundancy, and severity mismatches.
    """
    print("ADVANCED")
    report = []
    report.append("="*60)
    report.append("SRE ADVANCED INCIDENT DEEP-DIVE REPORT")
    report.append("="*60 + "\n")

    # 1. Intro & Overall Summary
    total_rows = len(df)
    unique_ids = df['incidentId'].nunique() if 'incidentId' in df.columns else total_rows
    report.append(f"### 1. OVERALL SUMMARY ###")
    report.append(f"Total Incident Events: {total_rows}")
    report.append(f"Unique Incidents: {unique_ids}")
    if 'dt' in df.columns:
        report.append(f"Analysis Window: {df['dt'].min()} to {df['dt'].max()}")
    report.append("")

    # 2. Noise & Redundancy
    report.append(f"### 2. NOISE & REDUNDANCY ###")
    if 'conditionName' in df.columns:
        top_noisy = df['conditionName'].value_counts().head(3)
        report.append("Top Noise Contributors:")
        for name, count in top_noisy.items():
            report.append(f"  - '{name}': {count} events")
        
        # Cross-policy duplication check
        overlap = df.groupby('conditionName')['policyName'].nunique()
        redundant = overlap[overlap > 1]
        if not redundant.empty:
            report.append("\nRedundancy Warning: Identical conditions found in multiple policies:")
            for cond, p_count in redundant.head(5).items():
                report.append(f"  - '{cond}' exists in {p_count} different policies.")
    report.append("")

    # 3. Flappiness
    report.append(f"### 3. FLAPPINESS ANALYSIS ###")
    if 'incidentId' in df.columns and 'timestamp' in df.columns:
        times = df.groupby('incidentId')['timestamp'].agg(['min', 'max'])
        times['duration_min'] = (times['max'] - times['min']) / 60000
        flappy = times[(times['duration_min'] > 0) & (times['duration_min'] < 5)]
        pct = (len(flappy) / unique_ids) * 100
        report.append(f"Flappiness Rate: {pct:.1f}% of incidents resolve in < 5 mins.")
        report.append("Recommendation: Evaluate threshold durations to prevent transient notification spam.")
    else:
        report.append("Insufficient temporal data for duration analysis.")
    report.append("")

    # 4. Criticality Patterns
    report.append(f"### 4. CRITICALITY PATTERNS (WARNING VS CRITICAL) ###")
    if 'priority' in df.columns and 'conditionName' in df.columns:
        false_criticals = df[(df['priority'].str.lower() == 'critical') & 
                             (df['conditionName'].str.contains('warning', case=False, na=False))]
        if not false_criticals.empty:
            report.append(f"Misalignment Found: {false_criticals['conditionName'].nunique()} conditions are labeled 'Warning' but trigger as 'Critical':")
            for item in false_criticals['conditionName'].unique()[:5]:
                report.append(f"  - {item}")
        else:
            report.append("Severity labels are consistent with priority levels.")
    report.append("")

    # 5. Entity Patterns
    report.append(f"### 5. ENTITY SPECIFIC PATTERNS ###")
    target_col = next((c for c in ['entity.name', 'targetName', 'entityName'] if c in df.columns), None)
    if target_col:
        noisy_entities = df[target_col].value_counts().head(5)
        report.append("Entities with highest alert volume:")
        for e, c in noisy_entities.items():
            report.append(f"  - {e}: {c} events")
    report.append("")

    report_text = "\n".join(report)

    with open(filename, "w") as f:
        f.write(report_text)
    print("\n  Advanced report saved to report.txt")    


def main():
    parser = argparse.ArgumentParser(description="New Relic Alert Analyzer")
    parser.add_argument("--api_key", help="NR User API Key")
    parser.add_argument("--account_id", help="NR Account ID")
    parser.add_argument("--list-accounts", action="store_true", help="List accessible accounts")
    
    end = datetime.utcnow()
    start = end - timedelta(days=30)
    parser.add_argument("--start_time", default=start.strftime("%Y-%m-%d %H:%M:%S"))
    parser.add_argument("--end_time", default=end.strftime("%Y-%m-%d %H:%M:%S"))
    parser.add_argument("--show_top_n", type=int, default=100)
    parser.add_argument("--include_warnings", default = True, action="store_true")
    parser.add_argument("--limit", type=int, default=100000)
  
    args = parser.parse_args()
    key = args.api_key or select_api_key_interactively(load_api_keys_from_config())
    if not key: return

    if args.list_accounts:
        list_accounts(key)
        return

    if not args.account_id:
        print("Error: --account_id required."); return

    # Fetch and format the account name for use as a file prefix
    account_prefix = get_account_name(key, args.account_id)
    print(f"\nResolved Account Prefix: {account_prefix}")

    results = fetch_incidents(key, args.account_id, args.start_time, args.end_time, not args.include_warnings, args.limit)
    if not results: return

    df = pd.DataFrame(results)
    df['accountId'] = args.account_id
    df.to_csv("{}_incidents.csv".format(account_prefix), index=False)

    summary_io = io.StringIO()
    with contextlib.redirect_stdout(summary_io):
        t_sum = analyze_temporal(df)
        s_sum = analyze_severity(df)
        r_sum = analyze_root_cause(df, args.show_top_n)
        e_sum = analyze_entities(df, args.show_top_n)
    
    summary_content = summary_io.getvalue()
    print(summary_content)
    with open("{}_incident_summary.txt".format(account_prefix), "w") as f: f.write(summary_content)

    # NEW: Advanced Granular Report
    generate_advanced_report(df, filename="{}_report.txt".format(account_prefix))

 
    print_header("Done")

if __name__ == "__main__":
    main()