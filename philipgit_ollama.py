#!/usr/bin/env python3

import subprocess
import sys
from pathlib import Path
from prompt_toolkit import prompt as pt_prompt
import webbrowser
from ollama import Client

DEBUG = True
CLIENT = Client()

def prompt(message):
    response = pt_prompt(f"{message} (y/n): ").strip().lower()
    return response == "y"

def run(command, capture_output=False, shell=True):
    result = subprocess.run(command, shell=shell, text=True, capture_output=capture_output)
    if result.returncode != 0:
        print(f"Command failed: {command}")
        sys.exit(1)
    return result.stdout.strip() if capture_output else None

def suggest_commit_message(diff):
    """Generate commit message from git diff"""
    try:
        if not diff:
            return "Update code"
            
        resp = CLIENT.chat(
            model="gemma2:2b-instruct-q4_K_M",
            messages=[
                {"role": "system", "content": """
                 You are a Git commit message generator. Generate commit message subjects where:
                    - Use imperative mood
                    - Max 50 characters
                    - No prefixes like 'fix:' or trailing periods
                    - Answer with only the commit message subject without any additional explanation
                    - Give only one suggestion
                    - Examples: 'Add user authentication', 'Update README with setup instructions', 'Refactor database connection logic'
                 """},
                {"role": "user", "content": f"Generate a commit message subject for this diff:\n\n{diff}"}
            ],
            stream=True
        )
        return resp['message']['content'].strip()
    except Exception as e:
        print(f"Error generating commit message: {e}")
        return "Update code"

def suggest_branch_name(diff):
    """Generate branch name from git diff or recent changes"""
    try:
        if not diff:
            return "feature"
            
        resp = CLIENT.chat(
            model="gemma2:2b-instruct-q4_K_M",
            messages=[
                {"role": "system", "content": 
                 """You are a Git branch name generator. Generate branch names in the format 'company/feature-description' where:
                    - 'company' is extracted from file paths or code changes (look for company/client names in file paths, class names, or variable names)
                    - 'feature-description' is a short, descriptive name using lowercase and no spaces
                    - Use kebab-case (hyphens) for multi-word descriptions
                    - Examples: 'bestdk/scanning-changes', 'nordicfeel/supplier-mail', 'postnord/freight-payer'
                    - If no clear company is found, use a descriptive feature name only"""},
                {"role": "user", "content": f"Generate a branch name for these changes:\n{diff}\n\nRespond with only the branch name (company/feature or just feature), no explanations."}
            ],
        )
        suggested = resp['message']['content'].strip().lower()
        # Clean up any extra formatting or quotes
        suggested = suggested.replace('"', '').replace("'", "").replace('`', '')
        return suggested
    except Exception as e:
        print(f"Error generating branch name: {e}")
        return "feature"

def get_diff_and_save_to_file():
    """Get git diff of staged changes and save to a temp file"""
    try:
        diff = run("git diff --unified=0 | grep -E '^[+-]'", capture_output=True)
        with open("temp_diff.txt", "w") as f:
            f.write(diff)
        return diff
    except Exception as e:
        print(f"Error getting git diff: {e}")
        return ""

def main():
    diff = get_diff_and_save_to_file()
    # Step 1: Create branch

    if prompt("Do you want to create a branch?"):
        current_branch = run("git branch --show-current", capture_output=True)
        if current_branch != "main":
            run("git checkout main", capture_output=True)
        
        suggested_name = suggest_branch_name(diff)
        print(f"Suggested branch name: philip/{suggested_name}")
        branchname = input(f"Enter branch name (or press Enter for 'philip/{suggested_name}'): ").strip().lower()
        if not branchname:
            branchname = f"philip/{suggested_name}"
        elif not branchname.startswith("philip/"):
            branchname = f"philip/{branchname}"
        run(f"git checkout -b {branchname}")
    else:
        run("git status")

    # Step 2: Commit changes
    if prompt("Do you want to commit changes?"):
        run("git add .")
        suggested_msg = suggest_commit_message(diff)
        print(f"Suggested commit message: {suggested_msg}")
        commitmsg = input(f"Enter commit message (or press Enter for '{suggested_msg}'): ").strip()
        if not commitmsg:
            commitmsg = suggested_msg
        run(f'git commit -m "{commitmsg}"')
    else:
        commitmsg = run("git log -1 --pretty=%s", capture_output=True)

    # Step 3: Rebase
    if prompt("Do you want to rebase?"):
        run("git fetch")
        try:
            run("git rebase origin/main")
        except SystemExit:
            print("Failed to rebase")
            sys.exit(1)

     # Step 4: Push branch
    if prompt("Do you want to push the branch?"):
        if DEBUG:
            print("debugging")
        else:
           run("git push")
    else:
        print("Branch not pushed.")

    # Step 5: Create PR
    if prompt("Do you want to create a PR?"):
        prdesc = pt_prompt(f"Enter PR description: ", default=commitmsg).strip()

        template_path = Path("./pull_request_template.md")
        if not template_path.exists():
            print("PR template not found.")
            sys.exit(1)

        pr_template = template_path.read_text(encoding="utf-8")
        pr_body = pr_template.replace("# Describe your changes", f"# Describe your changes\n\n{prdesc}")

        if DEBUG:
            print("debugging")
        else:
            run(["gh", "pr", "create", "--title", commitmsg, "--body", pr_body], shell=False)

        if prompt("Do you want to automerge the PR?"):
            if DEBUG:
                print(pr_body)
            else:
                run("gh pr merge --squash --auto --delete-branch")

                # Get the PR URL and open it in a new window
                pr_url = run("gh pr view --json url --jq .url", capture_output=True)
                subprocess.run("clip", text=True, input=pr_url, shell=True)  # Copy PR URL to clipboard
                # if pr_url: webbrowser.open(pr_url, new=1)  # new=1 for new window, new=2 for new tab

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
