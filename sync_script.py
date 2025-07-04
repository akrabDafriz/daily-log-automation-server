#
# GitHub to Trello Synchronization Service (V3 - Milestones & Daily Logs)
#
# Description:
# This script provides a one-way sync from a GitHub Markdown file to a Trello card.
# It reads a structured markdown file with two sections: "Milestones" and "Daily Logs".
# - Milestones are synced to Trello checklists.
# - All new Daily Log entries are synced to Trello comments, and existing comments are updated if the log changes.
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
                # Find the full text for this daily log entry
                date_str = date_match.group(1)
                # A simple way to get the block is to split by '---'
                full_log_block = content.split(stripped_line)[1].split('---')[0].strip()
                data["daily_logs"][date_str] = f"### {date_str}\n{full_log_block}"

    return data

# --- Trello Functions ---
def get_trello_card_data(card_id, fields="all"):
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
    """Syncs milestones from GitHub to Trello checklists."""
    print("--- Syncing Milestones to Checklists ---")
    card_state = state.setdefault(card_id, {"checklists": {}})
    existing_checklists = {cl['name']: cl for cl in card_data.get('checklists', [])}

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
                existing_checklists[milestone_name] = checklist # Add to our local copy
            except requests.exceptions.RequestException as e:
                print(f"Error creating checklist: {e}")
                continue
        
        if not checklist: continue

        # Sync items within the checklist
        existing_items = {item['name']: item for item in checklist.get('checkItems', [])}
        for task in tasks_from_github:
            task_name = task['name']
            task_checked = task['checked']
            state_str = 'complete' if task_checked else 'incomplete'

            if task_name not in existing_items:
                print(f" -> Creating new task: '{task_name}'")
                url = f"{TRELLO_API_BASE_URL}/checklists/{checklist['id']}/checkItems"
                params = {'key': TRELLO_API_KEY, 'token': TRELLO_API_TOKEN, 'name': task_name, 'checked': task_checked}
                requests.post(url, params=params)
            else:
                # Check if state needs updating
                item = existing_items[task_name]
                if item['state'] != state_str:
                    print(f" -> Updating task state for: '{task_name}' to {state_str}")
                    url = f"{TRELLO_API_BASE_URL}/cards/{card_id}/checkItem/{item['id']}"
                    params = {'key': TRELLO_API_KEY, 'token': TRELLO_API_TOKEN, 'state': state_str}
                    requests.put(url, params=params)

def sync_daily_log(card_id, card_data, daily_logs_from_github):
    """Syncs all daily logs from GitHub to Trello, updating existing comments if they differ."""
    print("\n--- Syncing Daily Logs to Comments ---")
    
    existing_comments = card_data.get('actions', [])
    
    # Create a dictionary mapping the date header to the comment's ID and full text.
    posted_logs = {}
    for comment in existing_comments:
        text = comment['data']['text'].strip()
        if text.startswith("###"):
            header = text.split('\n')[0]
            posted_logs[header] = {"id": comment['id'], "text": text}

    # Loop through all logs found in the markdown file
    for date_str, log_content_from_github in daily_logs_from_github.items():
        date_header = f"### {date_str}"
        log_content_from_github = log_content_from_github.strip()

        # Check if a log for this date has already been posted
        if date_header in posted_logs:
            existing_comment_id = posted_logs[date_header]["id"]
            existing_comment_text = posted_logs[date_header]["text"]

            # Compare the content from GitHub with the existing Trello comment
            if log_content_from_github != existing_comment_text:
                # Content has changed, so update the comment
                print(f"Log for {date_str} has changed. Updating comment...")
                url = f"{TRELLO_API_BASE_URL}/actions/{existing_comment_id}"
                params = {'key': TRELLO_API_KEY, 'token': TRELLO_API_TOKEN, 'text': log_content_from_github}
                try:
                    requests.put(url, params=params)
                    print("-> Successfully updated comment.")
                except requests.exceptions.RequestException as e:
                    print(f"Error updating comment for {date_str}: {e}")
            else:
                # Content is the same, do nothing
                print(f"Log for {date_str} is already up to date. Skipping.")
        else:
            # If not posted, post it as a new comment
            print(f"Posting new comment for {date_str}...")
            url = f"{TRELLO_API_BASE_URL}/cards/{card_id}/actions/comments"
            params = {'key': TRELLO_API_KEY, 'token': TRELLO_API_TOKEN, 'text': log_content_from_github}
            try:
                requests.post(url, params=params)
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
            
        # Run both sync functions
        sync_milestones(card_id, card_data, parsed_data["milestones"], state)
        sync_daily_log(card_id, card_data, parsed_data["daily_logs"])

    save_state(state)
    print("\n--- Full Sync Cycle Complete ---")

if __name__ == "__main__":
    main()
