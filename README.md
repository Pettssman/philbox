# philbox
philbox contains scripts that I use for different purposes.

## Gitophil
Gitophil is used as a git tool to create branches, commits and PRs. Copilot is integrated in the script and will give suggestions for branch names, commit messages and PR titles (if only one commit, then commit message will be used as PR title).

Download the .exe file under releases in github and place it under for example "~/tools/gitophil.exe".\
Then run the following command inside of the repository to bind the executable to the alias "gitophil", the alias can be set to whatever you want:\
`git config --local alias.gitophil '!PATH_TO_FILE/gitophil.exe'`

Then run `git gitophil` to launch the program. You will be asked to give:

1. Your name that is used for PR notification in Teams.
2. A webhook URL that allows to publish a message in a Teams chat.

To generate a webhook URL, right-click a Teams chat and press "Workflows". Then search for "Send webhook alerts to a chat" and create that workflow and then you will be able to copy the link to that webhook.

### Customizing workflows
When running the script, a "gitophil_config.TOML" file is created containing the PR name and webhook as well as a default set of workflows. It is possible to modify and create new workflows in the toml file as long as they contain any of the avalible git operations that is also stored in the toml file. The avalible git operations are there only as a guide for what operations are avalible and will not have any effect if it is modified.

Note that the operations will always run in a designated order, thus, even if "commit" is placed in front of "create branch", it will run "create branch" before "commit".
