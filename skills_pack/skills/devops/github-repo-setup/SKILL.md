---
name: github-repo-setup
description: Complete workflow for initializing a local project as a private GitHub repository with SSH authentication, including .gitignore, commit, SSH key generation, remote configuration, conflict resolution, and push.
category: devops
tags: [git, github, ssh, repository-setup, private-repo, devops]
---

# GitHub Repository Setup with SSH Authentication

Complete workflow for taking a local project and pushing it to a new/existing private GitHub repository using SSH keys.

## Prerequisites
- Git installed and configured (user.name, user.email)
- GitHub account with access to target organization
- SSH access to GitHub (or willingness to generate keys)

## Workflow Steps

### 1. Initialize Local Repository
```bash
cd /path/to/project
git init
git config user.email "your@email.com"
git config user.name "Your Name"
```

### 2. Create .gitignore (Critical — Do Before First Commit)
```bash
cat > .gitignore << 'EOF'
# Python bytecode
__pycache__/
*.py[cod]
*$py.class

# Virtual environments
venv/
env/
.venv/

# Environment files
.env
.env.local
*.env

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Build artifacts
dist/
build/
*.egg-info/
*.whl

# Test artifacts
.coverage
htmlcov/
.pytest_cache/
.mypy_cache/
.tox/

# Docker
.dockerignore

# Data
*.sqlite
*.db

# Temporary
*.tmp
*.temp
tmp/
EOF
```

### 3. Initial Commit
```bash
git add .
git commit -m "Initial commit: descriptive message with key metrics"
git branch -M main
```

### 4. Generate SSH Key (Ed25519 Recommended)
```bash
# Replace with your GitHub email
ssh-keygen -t ed25519 -C "your@email.com" -f ~/.ssh/github_<project> -N ""
```

**Add to SSH config** (`~/.ssh/config`):
```
Host github.com-<project>
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_<project>
    IdentitiesOnly yes
```

**Add public key to GitHub**: Settings → SSH and GPG keys → New SSH key → paste `cat ~/.ssh/github_<project>.pub`

**Test**: `ssh -T git@github.com-<project>` → should show "Hi <username>!"

### 5. Create GitHub Repository (Browser)
- Go to GitHub org → New repository
- Name: `<project-name>`
- Private ✓
- **Do NOT** initialize with README, .gitignore, or license

### 6. Configure Remote and Push
```bash
git remote add origin git@github.com-<project>:<org>/<repo>.git
git push -u origin main
```

### 7. Handle Remote Conflicts (If Repository Has Existing Commits)
```bash
git fetch origin
git log --oneline -5 origin/main  # Inspect remote history

# Option A: Rebase local onto remote (preserves local commits on top)
git pull origin main --rebase
# Resolve conflicts: git checkout --ours <file> && git add <file> && GIT_EDITOR=true git rebase --continue

# Option B: Force push (DANGEROUS — only if local is authoritative)
# git push -u origin main --force-with-lease
```

## Pitfalls & Fixes

| Issue | Fix |
|-------|-----|
| "Repository not found" | Create the repo on GitHub first (browser) |
| "Permission denied (publickey)" | SSH key not added to GitHub, or wrong key in config |
| "Updates were rejected (fetch first)" | Remote has commits; use `git pull --rebase` then resolve conflicts |
| "Could not read Username" | Using HTTPS without token; switch to SSH remote |
| `__pycache__` committed | Add `.gitignore` **before** first commit, or `git rm -r --cached __pycache__/` then recommit |
| Rebasing editor hangs | Use `GIT_EDITOR=true git rebase --continue` for non-interactive continue |
| **Push rejected: `remote: GH013: ... Changes must be made through a pull request`** | The repo has **branch protection** on `main`. Direct push is blocked by design. Commit locally, then `git branch -M feature/<name>` and `git push origin feature/<name>`; the remote prints a `pull/new/<branch>` URL. Create the PR from that link. `gh pr create` needs auth (`GH_TOKEN` or `gh auth login`) — if `gh` isn't authenticated the CLI fails, so just hand the user the PR URL. |

## Merging a Protected PR (unblocking the merge button)

Once feature branches are pushed, the WORK is often only half-done — the PR sits
blocked by branch protection and the merge button won't appear. Perl-class
diagnostics that recurred on the Enterprise platform (branch-protected `main`,
no `gh` token):

- **Diagnose via the REST API first** (no token needed for public repos; SSH
  authenticates git but CANNOT create/merge PRs — that needs a token or the web
  UI). Get the real blocker:
  ```bash
  curl -s https://api.github.com/repos/<org>/<repo>/pulls?state=open \
    | python3 -c "import sys,json;[print(f\"PR #{p['number']}: {p['title']} [{p['head']['ref']}->{p['base']['ref']}] mergeable={p.get('mergeable')} state={p.get('mergeable_state')}\") for p in json.load(sys.stdin)]"
  # Then get per-check status on the head commit:
  SHA=$(curl -s .../pulls/<N> | python3 -c "import sys,json;print(json.load(sys.stdin)['head']['sha'])")
  curl -s -H "Accept: application/vnd.github+json" .../commits/$SHA/check-runs
  ```
  Reading `mergeable_state` (**unstable** vs **blocking**) + the actual check-runs
  tells you whether it's a review gate, a required-check gate, or genuinely broken.

- **`continue-on-error: true` jobs STILL appear as red "failing checks" on the PR**
  and can block merge if branch protection lists them as REQUIRED status checks.
  Marking a job advisory in the workflow does NOT automatically exempt it from the
  required-checks gate. On the Enterprise CI, `Lint (ruff)` + `Type Check (mypy)`
  were advisory (`continue-on-error`) but branch protection had them required →
  merge blocked by "2 failing checks" even though the real gate
  (`Test pytest 3.11/3.12`, `Build`, `Security Scan`, `CI Pipeline Summary`) all
  passed. Fix: in branch protection (Settings → Branches → `main` → Edit →
  "Require status checks to pass"), UNCHECK lint/mypy so only the true gates are
  required.

- **"Review required — at least 1 approving review by reviewers with write access"
  is the hard blocker** independent of checks. Relax it (uncheck "Require
  approvals") or set "Required number of approvals" to 1 and self-approve if the
  rule allows. Removing the review gate is the fastest fix for a single-owner repo.

- **A feature branch that was built on ANOTHER unmerged feature branch is a
  SUPERSET.** Check with `git log --oneline origin/main..origin/<feature2>` vs
  `...origin/<feature1>`. If branch B contains all of A's commits plus more, merging
  B alone delivers everything (A becomes redundant but still merges cleanly as an
  ancestor). Tell the user they don't need to merge both — say so explicitly before
  they click, so they don't expect content in PR #1 that lives on PR #2.

- **Creating a PR from a compare URL** when no PR exists yet: open
  `https://github.com/<org>/<repo>/compare/main...<head-branch>` → green
  **"Create pull request"** → title → Create. This is how an unpushed-PR branch
  (e.g. the gold-picks branch that was only a compare link) becomes a real PR.

- **Only the user's OWN authenticated browser can do the merge** — the sandboxed
  browser and SSH both cannot (no GitHub token on the box). Open the PR pages in
  the user's browser via `xdg-open <url>` (call them in separate foreground
  `terminal` calls — the sandbox blocks shell `&`/`setsid`/`nohup` backgrounding),
  then hand off the exact clicks. Verify PR creation from the API afterwards.

- **TRIPLE-IDENTITY ADMIN GATE (a blocker distinct from merge-unblocking):** a
  collaborator who can PUSH and even OPEN PRs still CANNOT edit branch protection,
  because `Settings → Branches` (the admin-only page that holds the rule) is
  invisible to write/contributor-level accounts. Diagnosed on the Enterprise repo:
  the SSH key authenticated as **Mimicry500** (a collaborator) and could push the
  26-commit PR + run CI, but the `settings/branches` page 404'd/never rendered —
  it needs **owner** (or Admin-role collaborator) access. Establish the identity
  map FIRST when merges are blocked and the user says "I can't see that page":
  ```bash
  curl -s https://api.github.com/repos/<org>/<repo> | python3 -c \
    "import sys,json;d=json.load(sys.stdin);print(d['owner']['login'], d['owner']['type'])"
  # owner 'type' == 'User' → it's a personal account, not an org → likely a SECOND account the user owns
  git config user.name; git config user.email            # local git identity
  ssh -T -i ~/.ssh/<key> git@github.com                  # what the SSH key authenticates as
  ```
  The classic shape is THREE identities on one repo: the **owner** account
  (`readyAIsolutions`), the **collaborator** the SSH key authenticates as
  (`Mimicry500`, push-only), and the **local git identity** (usually a personal
  email). To unlock branch-protection edits the user must either (a) sign into
  GitHub as the OWNER, or (b) have the owner add the collaborator with **Admin**
  role (Settings → Collaborators → change Write → Admin). Rule: **push access ≠
  branch-protection/admin access.** Verify who holds the owner login before
  promising the user can fix it themselves — if only a non-owner account is
  reachable, ask whether they control the owner account or need someone to elevate
  the collaborator to Admin.

## Identifying a Key from a Pasted Fingerprint
When LO pastes a `SHA256:<base64>` string (GitHub-style key fingerprint) and asks "which key is this?", match it against local keys:
```bash
cd ~/.ssh && for f in *.pub; do echo -n "$f: "; ssh-keygen -lf "$f" | awk '{print $2}'; done
```
Plain `ssh-keygen -lf <file>` prints the SHA256 fingerprint in field 2 — note some builds
error "Too many arguments" if you add `-E sha256`, so drop `-E` and match the printed
`SHA256:...` value against what LO pasted. Then confirm which remote alias uses that key via
`~/.ssh/config` and test with `ssh -T -i <key> git@github.com` → "Hi <user>!".

## Verification Checklist
- [ ] `git status` shows clean working tree
- [ ] `git log --oneline -3` shows expected commits
- [ ] `git remote -v` shows SSH remote
- [ ] GitHub repo shows files and commit history
- [ ] Branch protection rules configured (if needed)

## References
- `references/ssh-config-template.md` — SSH config patterns (per-project, multi-account, debugging)
- `references/gitignore-templates.md` — Language-specific .gitignore templates (Python, Node, Docker, Go, Rust, Java, universal)
- `references/branch-protection-pr-merge.md` — worked example: diagnosing `mergeable_state`, advisory `continue-on-error` checks still blocking merge, review-gate unblock, superset-branch insight, creating a PR from a compare URL
- `scripts/verify-github-push.sh` — Post-push verification script (run `./verify-github-push.sh` after push)

## Quick Reference Card
```
# One-liner setup (replace values)
PROJECT=my-project ORG=myorg EMAIL=me@domain.com
ssh-keygen -t ed25519 -C "$EMAIL" -f ~/.ssh/github_$PROJECT -N ""
cat >> ~/.ssh/config <<EOF
Host github.com-$PROJECT
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_$PROJECT
    IdentitiesOnly yes
EOF
cat ~/.ssh/github_$PROJECT.pub  # → Add to GitHub Settings → SSH Keys
# Create repo on GitHub (browser): private, no README/.gitignore/license
cd /path/to/project
git init && git config user.email "$EMAIL" && git config user.name "Me"
cat > .gitignore <<'EOF'  # Use references/gitignore-templates.md
__pycache__/
*.py[cod]
.env
venv/
.DS_Store
EOF
git add . && git commit -m "Initial import: $PROJECT" && git branch -M main
git remote add origin git@github.com-$PROJECT:$ORG/$PROJECT.git
git push -u origin main
```

## Pushing a FINISHED version to an EXISTING repo as a release
If the repo already has content (template + old commits) and you built a newer,
unrelated-history version: DON'T force-push. `.gitignore` heavy dirs
(node_modules!), commit, push to a NEW branch (`main:release/<x>-v1.0.0`) +
push an annotated `v1.0.0` tag (non-destructive). SSH cannot create the GitHub
Release page (needs `gh auth login` / a PAT); report tag pushed + what still
needs the user's token. Details: `references/release-push-existing-repo.md`.