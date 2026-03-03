# philbox

## Gitophil
Gitophil is used as a git tool to create branches, commits and PRs. Copilot is integrated in the script and will give suggestions for branch names, commit messages and PR titles (if only one commit, then commit message will be used as PR title).

Download the .exe file under releases in github and place it under for example "~/tools/gitophil.exe".\
Then run the following to bind the executable to the alias "gitophil", the alias can be set to whatever you want:\
`git config --local alias.gitophil 'PATH_TO_FILE.exe'`

Then run:\
`git gitophil`
