#
# GitHub to Trello Synchronization Service (V7 - Handles Deletions & Log Rotation)
#
# Description:
# This script provides a one-way sync from a GitHub Markdown file to a Trello card.
# It reads a structured markdown file with two sections: "Milestones" and "Daily Logs".
# - Milestones are synced to Trello checklists, including deleting tasks removed from GitHub.
# - All Daily Log entries are synced to Trello comments in chronological order.
# - Existing Trello comments are updated if the corresponding log in GitHub changes.
#
#

import os
import requests
import sys
import re
import json
from datetime import date
from dotenv import load_dotenv

# --- CONFIGURATION ---
REPO_OWNER = ""
REPO_NAME = ""
TRELLO_API_KEY = ""
TRELLO_API_TOKEN = ""
GITHUB_TOKEN = ""

STATE_FILE = "sync_state.json"
CONFIG_FILE = "config.json"

# --- API Endpoints ---
GITHUB_API_BASE_URL = "https://api.github.com"
TRELLO_API_BASE_URL = "https://api.trello.com/1"

# --- State Management ---
def load_state():
    if not os.path.exists(STATE_FILE): return {}
    try:
        with open(STATE_FILE, 'r') as f: return json.load(f)
    except (json.JSONDecodeError, IOError): return {}

def save_state(state):
    try:
        with open(STATE_FILE, 'w') as f: json.dump(state, f, indent=4)
    except IOError as e: print(f"Error: Could not save state file: {e}")

# --- GitHub & Parsing Functions ---
def get_github_file_content(branch_name, file_path):
    print(f"Fetching '{file_path}' from branch '{branch_name}'...")
    url = f"{GITHUB_API_BASE_URL}/repos/{REPO_OWNER}/{REPO_NAME}/contents/{file_path}?ref={branch_name}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3.raw"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        print("-> Successfully fetched file from GitHub.")
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching file from GitHub: {e}")
        return None

def parse_markdown(content):
    """Parses the markdown file to extract milestones and daily logs separately."""
    data = {"milestones": {}, "daily_logs": {}}
    current_section = None
    current_milestone = None

    for line in content.split('\n'):
        stripped_line = line.strip()

        # Determine which major section we are in
        if stripped_line == "## 🏁 Milestones":
            current_section = "milestones"
            continue
        elif stripped_line == "## 📆 Daily Logs":
            current_section = "daily_logs"
            continue
        
        if current_section == "milestones":
            milestone_match = re.match(r"###\s*(.+)", stripped_line)
            task_match = re.match(r"-\s*\[(x| )\]\s*(.+)", stripped_line)
            if milestone_match:
                current_milestone = milestone_match.group(1).strip()
                data["milestones"][current_milestone] = []
            elif task_match and current_milestone:
                is_checked = task_match.group(1) == 'x'
                task_name = task_match.group(2).strip()
                data["milestones"][current_milestone].append({"name": task_name, "checked": is_checked})

        elif current_section == "daily_logs":
            date_match = re.match(r"###\s*(\d{4}-\d{2}-\d{2})", stripped_line)
            if date_match:
                date_str = date_match.group(1)
                full_log_block = content.split(stripped_line)[1].split('---')[0].strip()
                data["daily_logs"][date_str] = f"### {date_str}\n{full_log_block}"

    return data

# --- Trello Functions ---
def get_trello_card_data(card_id):
    """Gets all data for a card, including checklists and comments."""
    print(f"Fetching all data for Trello card {card_id[:5]}...")
    url = f"{TRELLO_API_BASE_URL}/cards/{card_id}"
    params = {'key': TRELLO_API_KEY, 'token': TRELLO_API_TOKEN, 'checklists': 'all', 'actions': 'commentCard'}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Trello card data: {e}")
        return None

def sync_milestones(card_id, card_data, milestones_from_github, state):
    """Syncs milestones from GitHub to Trello checklists, including deletions."""
    print("--- Syncing Milestones to Checklists ---")
    card_state = state.setdefault(card_id, {"checklists": {}})
    existing_checklists = {cl['name']: cl for cl in card_data.get('checklists', [])}
    
    # Create a set of task names from GitHub for efficient lookup
    github_task_names_by_milestone = {m_name: {t['name'] for t in tasks} for m_name, tasks in milestones_from_github.items()}

    for milestone_name, tasks_from_github in milestones_from_github.items():
        checklist = None
        if milestone_name in existing_checklists:
            checklist = existing_checklists[milestone_name]
            print(f"Found existing checklist: '{milestone_name}'")
        else:
            print(f"Creating new checklist: '{milestone_name}'")
            url = f"{TRELLO_API_BASE_URL}/checklists"
            params = {'key': TRELLO_API_KEY, 'token': TRELLO_API_TOKEN, 'idCard': card_id, 'name': milestone_name}
            try:
                response = requests.post(url, params=params)
                response.raise_for_status()
                checklist = response.json()
                existing_checklists[milestone_name] = checklist
            except requests.exceptions.RequestException as e:
                print(f"!! ERROR creating checklist '{milestone_name}': {e}")
                continue
        
        if not checklist: continue

        existing_items = {item['name']: item for item in checklist.get('checkItems', [])}
        
        # Create/Update loop
        for task in tasks_from_github:
            task_name = task['name']
            task_checked = task['checked']
            state_str = 'complete' if task_checked else 'incomplete'

            try:
                if task_name not in existing_items:
                    print(f" -> Creating new task: '{task_name}'")
                    url = f"{TRELLO_API_BASE_URL}/checklists/{checklist['id']}/checkItems"
                    checked_str = str(task_checked).lower()
                    params = {'key': TRELLO_API_KEY, 'token': TRELLO_API_TOKEN, 'name': task_name, 'checked': checked_str}
                    response = requests.post(url, params=params)
                    response.raise_for_status()
                else:
                    item = existing_items[task_name]
                    if item['state'] != state_str:
                        print(f" -> Updating task state for: '{task_name}' to {state_str}")
                        url = f"{TRELLO_API_BASE_URL}/cards/{card_id}/checkItem/{item['id']}"
                        params = {'key': TRELLO_API_KEY, 'token': TRELLO_API_TOKEN, 'state': state_str}
                        response = requests.put(url, params=params)
                        response.raise_for_status()
            except requests.exceptions.RequestException as e:
                print(f"!! ERROR syncing task '{task_name}': {e}")
                if 'response' in locals() and response is not None:
                    print(f"   Trello's response: {response.text}")
        
        # ** NEW ** Deletion loop
        github_task_names = github_task_names_by_milestone.get(milestone_name, set())
        for item_name, item_data in existing_items.items():
            if item_name not in github_task_names:
                print(f" -> Deleting task not found in GitHub: '{item_name}'")
                try:
                    url = f"{TRELLO_API_BASE_URL}/checklists/{checklist['id']}/checkItems/{item_data['id']}"
                    params = {'key': TRELLO_API_KEY, 'token': TRELLO_API_TOKEN}
                    response = requests.delete(url, params=params)
                    response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    print(f"!! ERROR deleting task '{item_name}': {e}")


def sync_daily_log(card_id, card_data, daily_logs_from_github):
    """Syncs all daily logs from GitHub to Trello, creating or updating comments as needed."""
    print("\n--- Syncing Daily Logs to Comments ---")
    
    existing_comments = card_data.get('actions', [])
    
    posted_logs = {}
    for comment in existing_comments:
        text = comment['data']['text'].strip()
        date_match = re.search(r"###\s*(\d{4}-\d{2}-\d{2})", text)
        if date_match:
            date_str = date_match.group(1)
            posted_logs[date_str] = {"id": comment['id'], "text": text}

    sorted_logs = sorted(daily_logs_from_github.items())

    for date_str, log_content_from_github in sorted_logs:
        log_content_from_github = log_content_from_github.strip()

        if date_str in posted_logs:
            existing_comment_id = posted_logs[date_str]["id"]
            existing_comment_text = posted_logs[date_str]["text"]

            if log_content_from_github != existing_comment_text:
                print(f"Log for {date_str} has changed. Updating comment...")
                url = f"{TRELLO_API_BASE_URL}/actions/{existing_comment_id}"
                params = {'key': TRELLO_API_KEY, 'token': TRELLO_API_TOKEN, 'text': log_content_from_github}
                try:
                    requests.put(url, params=params).raise_for_status()
                    print("-> Successfully updated comment.")
                except requests.exceptions.RequestException as e:
                    print(f"Error updating comment for {date_str}: {e}")
            else:
                print(f"Log for {date_str} is already up to date. Skipping.")
        else:
            print(f"Posting new comment for {date_str}...")
            url = f"{TRELLO_API_BASE_URL}/cards/{card_id}/actions/comments"
            params = {'key': TRELLO_API_KEY, 'token': TRELLO_API_TOKEN, 'text': log_content_from_github}
            try:
                requests.post(url, params=params).raise_for_status()
                print("-> Successfully posted comment.")
            except requests.exceptions.RequestException as e:
                print(f"Error posting comment for {date_str}: {e}")

# --- Main Execution ---
def main():
    print("\n--- Starting Full Sync Cycle ---")
    load_dotenv()
    
    global REPO_OWNER, REPO_NAME, TRELLO_API_KEY, TRELLO_API_TOKEN, GITHUB_TOKEN
    REPO_OWNER = os.getenv("GITHUB_REPO_OWNER")
    REPO_NAME = os.getenv("GITHUB_REPO_NAME")
    TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
    TRELLO_API_TOKEN = os.getenv("TRELLO_API_TOKEN")
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

    if not all([REPO_OWNER, REPO_NAME, TRELLO_API_KEY, TRELLO_API_TOKEN, GITHUB_TOKEN]):
        print("Error: A required environment variable is not set in .env file. Exiting.")
        return

    try:
        with open(CONFIG_FILE, 'r') as f: config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: Could not load or parse {CONFIG_FILE}: {e}")
        return
        
    state = load_state()

    for intern in config.get("interns", []):
        intern_name = intern.get("name")
        branch_name = intern.get("branch")
        card_id = intern.get("trello_card_id")
        file_path = intern.get("log_file_path")

        if not all([intern_name, branch_name, card_id, file_path]):
            print(f"Skipping invalid entry in config.json: {intern}")
            continue

        print(f"\n====================\nProcessing sync for: {intern_name}\n====================")
        content = get_github_file_content(branch_name, file_path)
        if content is None:
            print(f"Could not fetch content for {intern_name}. Skipping.")
            continue
            
        parsed_data = parse_markdown(content)
        card_data = get_trello_card_data(card_id)

        if card_data is None:
            print(f"Could not fetch Trello card data for {intern_name}. Skipping.")
            continue
            
        sync_milestones(card_id, card_data, parsed_data["milestones"], state)
        sync_daily_log(card_id, card_data, parsed_data["daily_logs"])

    save_state(state)
    print("\n--- Full Sync Cycle Complete ---")

if __name__ == "__main__":
    main()
