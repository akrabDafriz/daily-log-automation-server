# GitHub to Trello Synchronization Service

## 📖 Overview

This project provides a robust, one-way synchronization service that automatically updates a Trello card based on the content of a structured Markdown file hosted in a GitHub repository. It is designed for teams of interns or developers who maintain their work logs and milestones in GitHub but require a visual dashboard on Trello for review and tracking.

The service runs as a background task on a Windows Server, periodically checking for changes in each user's specified log file and reflecting those changes on their designated Trello card.

---

## ✨ Features

- **Multi-User Support:** Easily configurable for multiple users, each with their own GitHub branch, log file, and Trello card.
- **Milestone Syncing:** Translates the `## 🏁 Milestones` section of a Markdown file into Trello checklists.
  - ✅ **Creates** new checklists for new milestones.
  - ✅ **Creates** new tasks within a checklist.
  - ✅ **Updates** the state (checked/unchecked) of existing tasks.
  - ✅ **Deletes** tasks from a checklist if they are removed from the Markdown file.
- **Daily Log Syncing:** Translates the `## 📆 Daily Logs` section into Trello comments.
  - ✅ **Posts** all historical log entries that haven't been posted before.
  - ✅ **Updates** existing Trello comments if the corresponding log entry in the Markdown file is changed.
  - ✅ Posts comments in chronological order (oldest first).
- **Automated & Scheduled:** Runs automatically on a configurable schedule (e.g., every 5 minutes) and on server startup using Windows Task Scheduler.
- **Log Management:** Automatically rotates log files to prevent them from growing indefinitely.

---

## ⚙️ How It Works

The service consists of three main components that work together on the server:

1.  **Python Script (`sync_script.py`):** The core of the service. It contains all the logic for communicating with the GitHub and Trello APIs, parsing the Markdown files, and performing the synchronization.
2.  **PowerShell Wrapper (`run_sync.ps1`):** A simple script that handles log rotation and reliably executes the main Python script. This is the entry point for the scheduled task.
3.  **Windows Task Scheduler:** The system's "cron-job." It is configured to run the `run_sync.ps1` wrapper script on a recurring schedule and at startup, ensuring the service is always active.

---

## 📂 File Structure

Your project directory on the server should contain the following files:

-   `sync_script.py`: The main Python logic.
-   `config.json`: The central configuration file for managing users and their respective files/cards.
-   `.env`: The file for storing secret API keys and tokens. **This file should never be committed to a public repository. Use gitignore to prevent comitting this**
-   `run_sync.ps1`: The PowerShell script that executes the service.
-   `sync.log` (auto-generated): The log file for the current run cycle.
-   `sync.log.old` (auto-generated): A backup of the previous log cycle. This file will be replaced by a new sync.log.old file when the sync.log file has reached 1 MB in size. This can be changed in the run_sync.ps1 file.
-   `sync_state.json` (auto-generated): The script's "memory" to track created Trello items and prevent duplicates.

---

## 🚀 Setup and Installation

Follow these steps to set up the service on a Windows Server or a local machine.

### 1. Prerequisites

-   **Python 3.8+:** Ensure Python is installed. During installation, check the box to **"Add Python to PATH"**. You can verify the installation by opening a Command Prompt and running `python --version`.

### 2. Initial Setup

1.  **Create a Directory:** Create a dedicated folder for the service (e.g., `C:\SyncService`).
2.  **Copy Files:** Place `sync_script.py`, `config.json`, `.env`, and `run_sync.ps1` into this directory.
3.  **Install Dependencies:** Open a Command Prompt or PowerShell **as an Administrator**, navigate to your directory (`cd C:\SyncService`), and run:
    ```bash
    pip install requests python-dotenv
    ```

### 3. Get API Keys

-   **GitHub Personal Access Token (PAT):**
    1.  Go to GitHub -> Settings -> Developer settings -> Personal access tokens -> Tokens (classic).
    2.  Generate a new token with the full `repo` scope.
-   **Trello API Key & Token:**
    1.  Go to the [Trello Power-Ups admin page](https://trello.com/power-ups/admin).
    2.  Create a new Power-Up for this application.
    3.  On the Power-Up's "API Key" tab, generate a new API key.
    4.  On the same page, click the "Token" link to generate an API token.

### 4. Configuration

1.  **`.env` file:** Open the `.env` file and fill in your secrets along with the repository owner and repository name. I provided the file as `dummy.env`, change it into `.env` in your local directory.
    ```env
    GITHUB_TOKEN="ghp_YourPersonalAccessToken..."
    TRELLO_API_KEY="YourTrelloAPIKey..."
    TRELLO_API_TOKEN="YourTrelloAPIToken..."
    GITHUB_REPO_OWNER="repository-owner-username"
    GITHUB_REPO_NAME="repository-name"
    ```

2.  **`config.json` file:** Open `config.json` and add an entry for each user. I provided the file as `dummy-config.json`, change it into `config.json` in your local directory. 
    ```json
    {
      "interns": [
        {
          "name": "Bob",
          "branch": "bob-branch",
          "trello_card_id": "their_trello_card_id",
          "log_file_path": "path/to/their/log.md"
        },
        {
          "name": "Alice",
          "branch": "alice-branch",
          "trello_card_id": "their_trello_card_id",
          "log_file_path": "path/to/their/log.md"
        }
      ]
    }
    ```

---

## 🖥️ Deployment

To automate the script, create a task using Windows Task Scheduler.

1.  **Open Task Scheduler** as an Administrator.
2.  Click **Create Task...**
3.  **General Tab:**
    -   **Name:** `Trello-GitHub Sync`
    -   Select **"Run whether user is logged on or not"**.
    -   Check **"Run with highest privileges"**.
4.  **Triggers Tab:**
    -   **New Trigger 1:** Begin the task **"At startup"**.
    -   **New Trigger 2:** Begin the task **"On a schedule"**, repeating every **5 minutes** indefinitely.
5.  **Actions Tab:**
    -   **Action:** `Start a program`
    -   **Program/script:** `powershell.exe`
    -   **Add arguments:** `-ExecutionPolicy Bypass -File "C:\SyncService\run_sync.ps1"` (use the correct path).
6.  **Settings Tab:**
    -   Check **"Allow task to be run on demand"**.
    -   Set **"Stop the task if it runs longer than:"** to `1 hour`.
7.  **Save the Task:** Click OK and enter your Windows password when prompted.

---

## 🛠️ Usage

Once deployed, the service runs automatically. The primary way to use it is by updating the specified Markdown file in your GitHub branch.

-   **To add a new milestone:** Add a new `### Milestone Title` section.
-   **To add a new task:** Add a new `- [ ] Task description` line under a milestone.
-   **To complete a task:** Change `[ ]` to `[x]`.
-   **To add a new log:** Add a new `###
