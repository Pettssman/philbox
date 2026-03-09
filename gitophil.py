#!/usr/bin/env python3

import subprocess
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.formatted_text import HTML
import questionary
import json
import urllib.request
import sys
import threading
import tomllib
import tomli_w

DEBUG = False
CONFIG_PATH = Path(sys.executable).parent / "gitophil_config.toml" if getattr(sys, 'frozen', False) else Path(__file__).parent / "gitophil_config.toml"
CONFIG = {}

# ─── Workflow presets ────────────────────────────────────────────────
# Each preset maps to a set of step keys that will run automatically.
DEFAULT_WORKFLOWS = {
    "Full workflow":   ["branch", "commit", "rebase", "push", "create pr", "send webhook", "automerge", "switch to main"],
    "Full workflow, no AI":   ["branch", "commit", "rebase", "push", "create pr", "send webhook", "automerge", "switch to main"],
    "Create branch, commit":   ["branch", "commit"],
    "Commit only":     ["commit"],
    "Push & PR":       ["push", "create pr"],
    "Cleanup branches": ["cleanup_branches"],
    "Custom":          [],   # user picks steps interactively
}

NO_AI_WORKFLOWS = {"Full workflow, no AI"}

AVAILABLE_GIT_OPERATIONS = {
    "branch":    "Create branch",
    "commit":    "Commit changes",
    "rebase":    "Rebase on origin/main",
    "push":      "Push branch",
    "create pr": "Create PR",
    "send webhook": "Send webhook",
    "automerge": "Auto-merge PR",
    "switch to main": "Switch to main branch",
    "cleanup_branches": "Cleanup gone branches",
}


# ─── Helpers ─────────────────────────────────────────────────────────

def confirm(message):
    response = prompt(f"{message} (y/n): ").lower()
    return response == "y"


def prompt(message, **kwargs):
    """Wrapper around pt_prompt that renders the message in cyan."""
    response = pt_prompt(HTML(f"<cyan>{message}</cyan>"), **kwargs).strip()
    if not response:
        print("Input cannot be empty")
        return prompt(message, **kwargs)
    return response

def run(command, capture_output=False, shell=False, input=None):
    result = subprocess.run(command, shell=shell, text=True, capture_output=capture_output, input=input)
    if result.returncode > 1:  # git diff returns 1 when there are changes, which is fine
        print(f"Command failed: {command}")
        os._exit(1)
    return result.stdout.strip() if capture_output else None


def send_pr_notification(notification_text):
    """Send an adaptive card notification to Power Automate via webhook."""
    webhook_url = CONFIG.get("Webhook_URL")
    payload = {
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": notification_text
                        }
                    ]
                }
            }
        ]
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Webhook sent ({resp.status})")
    except Exception as e:
        print(f"Webhook failed: {e}")

def wait_with_loading(future, message="Loading AI suggestion"):
    """Block until future is done, showing an animated loading message."""
    stop = threading.Event()

    def animate():
        dots = 0
        while not stop.is_set():
            print(f"\r{message}{'.' * dots}   ", end="", flush=True)
            dots = (dots + 1) % 5
            stop.wait(0.3)
        print(f"\r{' ' * (len(message) + 10)}\r", end="", flush=True)

    t = threading.Thread(target=animate, daemon=True)
    t.start()
    result = future.result()
    stop.set()
    t.join()
    return result


# ─── AI generation ───────────────────────────────────────────────────

def generate_branchname():
    diff = run(["bash", "-c", "git diff --unified=0 | grep -E '^[+-]'"], 
               capture_output=True)
    if not diff: 
        return ""
    prompt_text = f"""Role: Git branch name generator.

Rules:
- Format: <company>/<feature> or just <feature> if no company is identifiable
- Extract company from file paths or namespaces in the diff (e.g. bestdk, nordicfeel, postnord)
- Feature part: kebab-case, lowercase, 2-4 words max
- No prefixes like "feature/" — only company/ or bare name
- Examples: bestdk/scanning-changes, nordicfeel/supplier-mail, disable-send-button

Diff:
{diff}

Output: branch name only, nothing else."""
    result = run(
        ["copilot"], input=prompt_text,
        capture_output=True,
        shell=True
    )
    return result


def generate_commitmessage():
    diff = run(["bash", "-c", "git diff --unified=0 | grep -E '^[+-]'"], 
               capture_output=True)
    prompt_text = f"""Role: Git commit message generator.

Rules:
- Max 50 characters
- Imperative mood, present tense (e.g. "Add", "Fix", "Remove" — not "Added", "Fixes")
- No trailing period
- Capitalize first word
- Describe *what* the change does, not *why*

Diff:
{diff}

Output: commit message only, nothing else."""
    result = run(
        ["copilot"], input=prompt_text,
        capture_output=True,
        shell=True
    )
    return result


def generate_pr_title():
    diff = run(["bash", "-c", "git diff main... --unified=0 | grep -E '^[+-]'"], 
               capture_output=True)
    if not diff:
        return ""
    prompt_text = f"""Role: GitHub pull request title generator.

Rules:
- Max 50 characters
- Imperative mood, present tense (e.g. "Add", "Fix", "Remove" — not "Added", "Fixes")
- No trailing period
- Capitalize first word
- Summarize the overall intent of all changes, not individual lines

Diff:
{diff}

Output: PR title only, nothing else."""
    result = run(
        ["copilot"], input=prompt_text,
        capture_output=True,
        shell=True
    )
    return result

# ─── Individual step functions ───────────────────────────────────────

def step_create_branch(branchname_future, use_ai):
    """Create and switch to a new branch from main."""
    current_branch = run(["git", "branch", "--show-current"], capture_output=True)
    if current_branch != "main":
        try:
            run(["git", "switch", "main"], capture_output=True)
        except SystemExit:
            print("Create branch was in workflow but could not switch to main")
            os._exit(1)

    if use_ai:
        branchname_cp = wait_with_loading(branchname_future, "Loading AI branch name suggestion")
    else:
        branchname_cp = branchname_future.result()
    branchname = prompt("Enter branch name: ", default=branchname_cp)
    if not branchname.startswith("philip/"):
        branchname = f"philip/{branchname}"
    run(["git", "switch", "-c", branchname], shell=False)


def step_commit(commitmsg_future, use_ai):
    """Stage all changes and commit with an AI-suggested message."""
    run(["git", "status", "--short"], shell=False)
    if use_ai:
        commitmsg = wait_with_loading(commitmsg_future, "Loading AI commit message suggestion")
    else:
        commitmsg = commitmsg_future.result()
    commitmsg = prompt("Enter commit message: ", default=commitmsg)
    if not commitmsg:
        print("Empty commit message, aborting.")
        os._exit(1)
    run(["git", "add", "."])
    run(["git", "commit", "-m", commitmsg], shell=False)
    return commitmsg


def step_rebase():
    """Fetch and rebase on origin/main."""
    run(["git", "fetch"])
    try:
        run(["git", "rebase", "origin/main"])
    except SystemExit:
        print("Failed to rebase")
        os._exit(1)


def step_push():
    """Push the current branch."""
    if DEBUG:
        print("[debug] would push")
    else:
        run(["git", "push"])


def step_create_pr(pr_title_future, draft=False, use_ai=False):
    """Create a pull request via gh CLI and copy link to clipboard."""
    if use_ai:
        pr_title = wait_with_loading(pr_title_future, "Loading AI PR title suggestion")
    else:
        pr_title = pr_title_future.result()
    pr_title = prompt("Enter PR title: ", default=pr_title)
    prdesc = prompt("Enter PR description: ", default=pr_title)

    template_path = Path("./pull_request_template.md")
    if not template_path.exists():
        print("PR template not found.")
        os._exit(1)

    pr_template = template_path.read_text(encoding="utf-8-sig")
    pr_body = f"{prdesc}\n\n{pr_template}"

    if DEBUG:
        print(f"[debug] PR body:\n{pr_body}")
        return ""
    else:
        create_cmd = ["gh", "pr", "create", "--title", pr_title, "--body", pr_body]
        if draft:
            create_cmd.append("--draft")
        run(create_cmd, shell=False)

        pr_url = run(["gh", "pr", "view", "--json", "url", "--jq", ".url"], capture_output=True)
        name = CONFIG.get("Name", "John Doe")
        formatted_link = f"{name}: [{pr_title}]({pr_url})"
        run(["clip"], input=pr_url, shell=True)
        print(f"PR link copied: {pr_url}")
        return formatted_link


def step_automerge():
    """Enable squash auto-merge and delete branch after merge."""
    if DEBUG:
        print("[debug] would automerge")
    else:
        run(["gh", "pr", "merge", "--squash", "--auto", "--delete-branch"])


def step_switch_to_main():
    """Switch to main"""
    run(["git", "switch", "main"])


def step_cleanup_branches():
    """Prune remote-tracking branches that no longer exist on the remote."""
    run(["git", "fetch", "--prune"], capture_output=True)
    # Get branches that are gone
    result = run(["git", "branch", "-vv"], capture_output=True)
    branches = []
    for line in result.splitlines():
        if "gone]" in line:
            branch_name = line.split()[0]
            branches.append(branch_name)

    if not branches:
        print("No branches to remove.")
        return

    # Print branches in yellow
    print("\033[33mThe following branches are gone:\033[0m")
    for branch in branches:
        print(f"\033[33m{branch}\033[0m")

    # Ask for confirmation
    if confirm("Do you want to remove these branches?"):
        for branch in branches:
            run(["git", "branch", "-D", branch])
        print("Branches removed.")
    else:
        print("No branches were removed.")


# ─── Menu & orchestration ───────────────────────────────────────────

def choose_workflow():
    """Present the main menu and return the set of steps to execute."""
    current_branch = run(["git", "branch", "--show-current"], capture_output=True)
    _workflows = CONFIG.get("Workflows", DEFAULT_WORKFLOWS)
    if current_branch != "main":
        _workflows = [wf for wf in _workflows if "branch" not in (_workflows[wf] or set())]
    workflow = questionary.select(
        "What would you like to do?",
        choices=list(_workflows),
        instruction="(arrow keys to move, enter to select)",
    ).ask()

    if workflow is None:  # Ctrl-C
        os._exit(0)

    if workflow == "Custom":
        selected = questionary.checkbox(
            "Pick the steps to run:",
            choices=[
                questionary.Choice(title=label, value=key)
                for key, label in AVAILABLE_GIT_OPERATIONS.items()
            ],
            instruction="(space to toggle, enter to confirm)",
        ).ask()
        if selected is None:
            os._exit(0)
        return set(selected), workflow

    if "commit" in _workflows[workflow] and subprocess.run(["git", "diff", "--quiet"], capture_output=True).returncode == 0:
        print("No changes to commit, but 'commit' step was selected. Aborting.")
        os._exit(0)

    return _workflows[workflow], workflow

def num_commits():
    result = run(
    ["git", "rev-list", "--count", "origin/main..HEAD"],
    capture_output=True)
    return int(result)  

def init_config():
    """Check for config file and create with prompts if not found."""
    if not CONFIG_PATH.exists():
        name = prompt("Enter your name (for PR notifications): ")
        webhook_url = prompt("Enter your Power Automate webhook URL (for PR notifications): ")
        default_config = {
            "Name": name,
            "Webhook_URL": webhook_url,
            "Workflows": DEFAULT_WORKFLOWS,
            "No_AI_Workflows": list(NO_AI_WORKFLOWS),
            "Available_Git_Operations": AVAILABLE_GIT_OPERATIONS,
        }
        with open(CONFIG_PATH, "wb") as f:
            tomli_w.dump(default_config, f)
        
        print(f"Created gitophil_config.toml at {CONFIG_PATH}", flush=True)
    
    with open(CONFIG_PATH, "rb") as f:
        global CONFIG
        CONFIG = tomllib.load(f)

def main():
    init_config()

    # Kick off AI suggestions in background for any steps that need them
    executor = ThreadPoolExecutor(max_workers=3)
    branchname_future = executor.submit(generate_branchname)
    commitmsg_future = executor.submit(generate_commitmessage)

    selected_steps, workflow = choose_workflow()
    use_ai = workflow not in NO_AI_WORKFLOWS
    print(f"\nSteps: {', '.join(AVAILABLE_GIT_OPERATIONS[s] for s in selected_steps)}\n")

    if not use_ai:
        branchname_future.cancel()
        commitmsg_future.cancel()
        branchname_future = executor.submit(lambda: "")
        commitmsg_future = executor.submit(lambda: "")

    if "branch" in selected_steps:
        step_create_branch(branchname_future, use_ai)

    if "commit" in selected_steps:
        commitmsg = step_commit(commitmsg_future, use_ai)
    elif run(["git", "branch", "--show-current"], capture_output=True) != "main":
        commitmsg = run(["git", "log", "-1", "--pretty=%s"], capture_output=True)
    else:
        commitmsg = ""

    if num_commits() > 1 and use_ai:
        pr_title_future = executor.submit(generate_pr_title)
    else:
        pr_title_future = executor.submit(lambda: commitmsg)

    if "rebase" in selected_steps:
        step_rebase()

    if "push" in selected_steps:
        step_push()

    if "create pr" in selected_steps:
        draft = questionary.confirm("Create as draft PR?", default=False, instruction="(Enter for No)").ask()
        pr_link = step_create_pr(pr_title_future, draft=draft, use_ai=False)
        if not draft and "send webhook" in selected_steps:
            send_pr_notification(pr_link)

    if "automerge" in selected_steps:
        step_automerge()
    
    if "switch to main" in selected_steps:
        step_switch_to_main()

    if "cleanup_branches" in selected_steps:
        step_cleanup_branches()

    print("\nDone!")
    executor.shutdown(wait=False)
    os._exit(0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        os._exit(1)
