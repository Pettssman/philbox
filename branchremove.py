#!/usr/bin/env py
import subprocess

subprocess.run("git remote prune origin")
print("----------------------------------------")

# Get branches that are gone
result = subprocess.run(
    "git branch -vv", shell=True, capture_output=True, text=True
)
branches = []
for line in result.stdout.splitlines():
    if "gone]" in line:
        branch_name = line.split()[0]
        branches.append(branch_name)

if not branches:
    print("No branches to remove.")
    exit(0)

# Prune remote branches
subprocess.run("git remote prune origin")

# Print branches in yellow
print("\033[33mThe following branches are gone:\033[0m")
for branch in branches:
    print(f"\033[33m{branch}\033[0m")

# Ask for confirmation
answer = input("Do you want to remove these branches? (y/n) ").strip().lower()
if answer.startswith("y"):
    for branch in branches:
        subprocess.run(["git", "branch", "-D", branch])
    print("Branches removed.")
else:
    print("No branches were removed.")