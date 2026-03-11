# philbox
philbox contains scripts that I use for different purposes.

## Gitophil
Gitophil is used as a git tool to create branches, commits and PRs. Copilot is integrated in the script and will give suggestions for branch names, commit messages and PR titles (if only one commit, then commit message will be used as PR title). The link to the PR can then be pubished to a teams chat via a webhook.

1. Download the .exe file under releases in github and place it under for example "~/tools/gitophil.exe".\
2. Mark the file in the file explorer and press ctrl+shift+c to copy the full path
3. Open git bash and paste the path and run.

You will be asked to provide:
1. Your name that is used for PR notification in Teams.
2. A webhook URL that allows to publish a message in a Teams chat.
3. If you want to create a git alias to be able to run using, for example ´git gitophil´ to launch the CLI

After the alias is created, the alias should be able to run in either powershell or git bash (as long as git is in your PATH).

### How to generate a webhook URL
To generate a webhook URL, right-click a Teams chat and press "Workflows". Then search for "Send webhook alerts to a chat" and create that workflow and then you will be able to copy the link to that webhook.

### Customizing workflows
When running the script, a "gitophil_config.toml" file is created containing the PR name and webhook as well as a default set of workflows. It is possible to modify and create new workflows in the toml file as long as they contain any of the available git operations that is also stored in the toml file. The available git operations are there only as a guide for what operations are available and will not have any effect if it is modified.

Note that the operations will always run in a designated order, thus, even if "commit" is placed in front of "create branch", it will run "create branch" before "commit".
