#!/usr/bin/env python3

import subprocess
import sys
from pathlib import Path
from prompt_toolkit import prompt as pt_prompt
import webbrowser

DEBUG = False

def prompt(message):
    response = pt_prompt(f"{message} (y/n): ").strip().lower()
    return response == "y"

def run(command, capture_output=False, shell=True):
    result = subprocess.run(command, shell=shell, text=True, capture_output=capture_output)
    if result.returncode != 0:
        print(f"Command failed: {command}")
        sys.exit(1)
    return result.stdout.strip() if capture_output else None

def get_diff_and_save_to_file():
    """Get git diff of staged changes and save to a temp file"""
    try:
        diff = run("git diff --unified=0 | grep -E '^[+-]'", capture_output=True)
        if diff == "" or diff is None: return ""
        with open("temp_diff.txt", "w") as f:
            f.write(diff)
        return diff
    except Exception as e:
        print(f"Error getting git diff: {e}")
        return ""

def main():
    # diff = get_diff_and_save_to_file()
    # Step 1: Create branch

    if prompt("Do you want to create a branch?"):
        current_branch = run("git branch --show-current", capture_output=True)
        if current_branch != "main":
            run("git switch main", capture_output=True)

        branchname = input(f"Enter branch name: ").strip().lower()
        if not branchname.startswith("philip/"):
            branchname = f"philip/{branchname}"
        run(f"git checkout -b {branchname}")
    else:
        run("git status")

    # Step 2: Commit changes
    if prompt("Do you want to commit changes?"):
        run("git add .")
        commitmsg = input(f"Enter commit message: ").strip()
        if not commitmsg: return
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
    create_pr_resp = pt_prompt("Do you want to create a PR? (y/n/d): ").strip().lower()
    if create_pr_resp in ("y", "d"):
        prtitle = pt_prompt(f"Enter PR title: ", default=commitmsg).strip()
        prdesc = pt_prompt(f"Enter PR description: ", default=prtitle).strip()

        template_path = Path("./pull_request_template.md")
        if not template_path.exists():
            print("PR template not found.")
            sys.exit(1)

        # Read template with BOM handling to avoid leading invisible char
        pr_template = template_path.read_text(encoding="utf-8-sig")
        pr_body = f"{prdesc}\n\n{pr_template}"

        if DEBUG:
            print("debugging")
        else:
            create_cmd = ["gh", "pr", "create", "--title", prtitle, "--body", pr_body]
            if create_pr_resp == "d":
                create_cmd.append("--draft")
            run(create_cmd, shell=False)

            # Get the PR URL and open it in a new window
            pr_url = run("gh pr view --json url --jq .url", capture_output=True)
            formatted_link = f"{prtitle}: {pr_url}"
            subprocess.run("clip", text=True, input=formatted_link, shell=True)
            # if pr_url: webbrowser.open(pr_url, new=1)  # new=1 for new window, new=2 for new tab

        if prompt("Do you want to automerge the PR?"):
            if DEBUG:
                print(pr_body)
            else:
                run("gh pr merge --squash --auto --delete-branch")

                

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
