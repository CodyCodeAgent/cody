# Git Operations

Git version control operations using the git CLI.

## Prerequisites

- Git must be installed: `git --version`
- Repository must be initialized: `git init`

## Common Commands

### Check Status
```bash
git status
```

### View Diff
```bash
git diff
```

### Add Files
```bash
git add <file>
git add .  # Add all files
```

### Commit
```bash
git commit -m "commit message"
```

### Push
```bash
git push
git push origin main
```

### Pull
```bash
git pull
```

### Create Branch
```bash
git checkout -b <branch-name>
```

### Switch Branch
```bash
git checkout <branch-name>
```

## Examples

**Check what changed:**
```bash
git status
git diff
```

**Commit changes:**
```bash
git add .
git commit -m "feat: add new feature"
```

**Push to remote:**
```bash
git push origin main
```

## Notes

- Always check status before committing
- Use clear, descriptive commit messages
- Pull before pushing to avoid conflicts
