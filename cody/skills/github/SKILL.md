# GitHub CLI Operations

Interact with GitHub repositories, issues, and pull requests using the `gh` CLI.

## Prerequisites

- GitHub CLI must be installed: `gh --version`
- Must be authenticated: `gh auth status`

## Repository Operations

### Clone a repository
```bash
gh repo clone owner/repo
```

### View repository info
```bash
gh repo view
gh repo view owner/repo --web
```

### Create a repository
```bash
gh repo create my-repo --public --source=. --remote=origin
```

## Issue Operations

### List issues
```bash
gh issue list
gh issue list --state closed
gh issue list --label "bug"
gh issue list --assignee @me
```

### Create an issue
```bash
gh issue create --title "Bug report" --body "Description of the bug"
gh issue create --title "Feature" --label "enhancement" --assignee @me
```

### View an issue
```bash
gh issue view 123
gh issue view 123 --comments
```

### Close/reopen an issue
```bash
gh issue close 123
gh issue reopen 123
```

## Pull Request Operations

### List pull requests
```bash
gh pr list
gh pr list --state merged
gh pr list --author @me
```

### Create a pull request
```bash
gh pr create --title "Add feature X" --body "Description"
gh pr create --fill  # Auto-fill title and body from commits
gh pr create --draft
```

### View a pull request
```bash
gh pr view 456
gh pr view 456 --comments
```

### Review a pull request
```bash
gh pr diff 456
gh pr review 456 --approve
gh pr review 456 --request-changes --body "Please fix..."
```

### Merge a pull request
```bash
gh pr merge 456
gh pr merge 456 --squash
gh pr merge 456 --rebase
```

### Check out a PR locally
```bash
gh pr checkout 456
```

## Workflow / Actions

### List workflow runs
```bash
gh run list
gh run view 789
```

### View workflow logs
```bash
gh run view 789 --log
gh run view 789 --log-failed
```

## Search

### Search issues
```bash
gh search issues "memory leak" --repo owner/repo
```

### Search code
```bash
gh search code "func main" --language go
```

## Release Operations

### List releases
```bash
gh release list
```

### Create a release
```bash
gh release create v1.0.0 --title "v1.0.0" --notes "Release notes"
gh release create v1.0.0 --generate-notes
```

## Notes

- Always check `gh auth status` before operations
- Use `--json` flag for machine-readable output: `gh issue list --json number,title,state`
- Use `--jq` for filtering JSON output: `gh pr list --json title --jq '.[].title'`
- For API calls: `gh api repos/owner/repo/issues`
