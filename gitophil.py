#!/usr/bin/env python3

import subprocess
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from prompt_toolkit import prompt as pt_prompt
import questionary

DEBUG = False

# ─── Workflow presets ────────────────────────────────────────────────
# Each preset maps to a set of step keys that will run automatically.
WORKFLOWS = {
    "Full workflow":   {"branch", "commit", "rebase", "push", "create_pr", "automerge", "switch to main"},
    "Full workflow, no AI":   {"branch", "commit", "rebase", "push", "create_pr", "automerge", "switch to main"},
    "Commit only":     {"commit"},
    "Push & PR":       {"push", "create_pr"},
    "Custom":          None,   # user picks steps interactively
}

NO_AI_WORKFLOWS = {"Full workflow, no AI"}

ALL_STEPS = [
    ("branch",    "Create branch"),
    ("commit",    "Commit changes"),
    ("rebase",    "Rebase on origin/main"),
    ("push",      "Push branch"),
    ("create_pr", "Create PR"),
    ("automerge", "Auto-merge PR"),
]


# ─── Helpers ─────────────────────────────────────────────────────────

def confirm(message):
    response = pt_prompt(f"{message} (y/n): ").strip().lower()
    return response == "y"


def run(command, capture_output=False, shell=True):
    result = subprocess.run(command, shell=shell, text=True, capture_output=capture_output)
    if result.returncode != 0:
        print(f"Command failed: {command}")
        os._exit(1)
    return result.stdout.strip() if capture_output else None


def run_cmd(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()


# ─── AI generation ───────────────────────────────────────────────────

def generate_branchname():
    diff = run_cmd(["bash", "-c", "git diff --unified=0 | grep -E '^[+-]'"])
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
    result = subprocess.run(
        ["copilot"], input=prompt_text,
        capture_output=True, text=True, shell=True,
    )
    return result.stdout.strip()


def generate_commitmessage():
    diff = run_cmd(["bash", "-c", "git diff --unified=0 | grep -E '^[+-]'"])
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
    result = subprocess.run(
        ["copilot"], input=prompt_text,
        capture_output=True, text=True, shell=True,
    )
    return result.stdout.strip()


def generate_pr_title():
    diff = run_cmd(["bash", "-c", "git diff main... --unified=0 | grep -E '^[+-]'"])
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
    result = subprocess.run(
        ["copilot"], input=prompt_text,
        capture_output=True, text=True, shell=True,
    )
    return result.stdout.strip()

# ─── Individual step functions ───────────────────────────────────────

def step_create_branch(branchname_future):
    """Create and switch to a new branch from main."""
    current_branch = run("git branch --show-current", capture_output=True)
    if current_branch != "main":
        try:
            run("git switch main", capture_output=True)
        except SystemExit:
            print("Create branch was in workflow but could not switch to main")
            os._exit(1)

    branchname_cp = branchname_future.result()
    branchname = pt_prompt("Enter branch name: ", default=branchname_cp).strip()
    if not branchname.startswith("philip/"):
        branchname = f"philip/{branchname}"
    run(f"git switch -c {branchname}")


def step_commit(commitmsg_future):
    """Stage all changes and commit with an AI-suggested message."""
    run("git status --short")
    commitmsg = commitmsg_future.result()
    commitmsg = pt_prompt("Enter commit message: ", default=commitmsg).strip()
    if not commitmsg:
        print("Empty commit message, aborting.")
        os._exit(1)
    run("git add .")
    run(f'git commit -m "{commitmsg}"')
    return commitmsg


def step_rebase():
    """Fetch and rebase on origin/main."""
    run("git fetch")
    try:
        run("git rebase origin/main")
    except SystemExit:
        print("Failed to rebase")
        os._exit(1)


def step_push():
    """Push the current branch."""
    if DEBUG:
        print("[debug] would push")
    else:
        run("git push")


def step_create_pr(pr_title_future, draft=False):
    """Create a pull request via gh CLI and copy link to clipboard."""
    pr_title = pr_title_future.result()
    pr_title = pt_prompt("Enter PR title: ", default=pr_title).strip()
    prdesc = pt_prompt("Enter PR description: ", default=pr_title).strip()

    template_path = Path("./pull_request_template.md")
    if not template_path.exists():
        print("PR template not found.")
        os._exit(1)

    pr_template = template_path.read_text(encoding="utf-8-sig")
    pr_body = f"{prdesc}\n\n{pr_template}"

    if DEBUG:
        print(f"[debug] PR body:\n{pr_body}")
    else:
        create_cmd = ["gh", "pr", "create", "--title", pr_title, "--body", pr_body]
        if draft:
            create_cmd.append("--draft")
        run(create_cmd, shell=False)

        pr_url = run("gh pr view --json url --jq .url", capture_output=True)
        formatted_link = f"{pr_title}: {pr_url}"
        subprocess.run("clip", text=True, input=formatted_link, shell=True)
        print(f"PR link copied: {formatted_link}")


def step_automerge():
    """Enable squash auto-merge and delete branch after merge."""
    if DEBUG:
        print("[debug] would automerge")
    else:
        run("gh pr merge --squash --auto --delete-branch")

def step_switch_to_main():
    """Switch to main"""
    run("git switch main")


# ─── Menu & orchestration ───────────────────────────────────────────

def choose_workflow():
    """Present the main menu and return the set of steps to execute."""
    current_branch = run("git branch --show-current", capture_output=True)
    if current_branch == "main":
        _workflows = WORKFLOWS.keys()
    else:
        _workflows = [wf for wf in WORKFLOWS.keys() if "full workflow" not in wf.lower()]  # Do not offer full workflow if not on main
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
                questionary.Choice(title=label, value=key, checked=(key in {"commit", "push", "create_pr"}))
                for key, label in ALL_STEPS
            ],
            instruction="(space to toggle, enter to confirm)",
        ).ask()
        if selected is None:
            os._exit(0)
        return set(selected)

    return WORKFLOWS[workflow], workflow

def num_commits():
    result = subprocess.run(
    ["git", "rev-list", "--count", "main..HEAD"],
    capture_output=True,
    text=True)
    return int(result.stdout.strip())  


def main():
    # Kick off AI suggestions in background for any steps that need them
    executor = ThreadPoolExecutor(max_workers=3)
    branchname_future = executor.submit(generate_branchname)
    commitmsg_future = executor.submit(generate_commitmessage)

    selected_steps, workflow = choose_workflow()
    use_ai = workflow not in NO_AI_WORKFLOWS
    print(f"\n→ Steps: {', '.join(s for s, _ in ALL_STEPS if s in selected_steps)}\n")

    if not use_ai:
        branchname_future.cancel()
        commitmsg_future.cancel()
        branchname_future = executor.submit(lambda: "")
        commitmsg_future = executor.submit(lambda: "")

    if "branch" in selected_steps:
        step_create_branch(branchname_future)

    if "commit" in selected_steps:
        commitmsg = step_commit(commitmsg_future)
    else:
        commitmsg = run("git log -1 --pretty=%s", capture_output=True)

    if num_commits() > 1 and use_ai:
        pr_title_future = executor.submit(generate_pr_title)
    else:
        pr_title_future = executor.submit(lambda: commitmsg)

    if "rebase" in selected_steps:
        step_rebase()

    if "push" in selected_steps:
        step_push()

    if "create_pr" in selected_steps:
        draft = questionary.confirm("Create as draft PR?", default=False).ask()
        step_create_pr(pr_title_future, draft=draft)

    if "automerge" in selected_steps:
        step_automerge()
    
    if "switch to main" in selected_steps:
        step_switch_to_main()

    print("\nDone!")
    os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        os._exit(1)
