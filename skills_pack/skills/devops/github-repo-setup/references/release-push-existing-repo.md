# Pushing a finished version to an EXISTING repo as a release (non-destructive)

Scenario: a repo already exists with prior content (e.g. a rough template +
manual commits), and you've built a much more finished version in a fresh
extract/git repo with UNRELATED history. You want to "release" the finished
version without silently destroying the existing branches.

## Golden rule
Never force-push over an existing remote branch to "replace" it without the
user's explicit OK. Force-push is irreversible on a real remote. The old
commits are recoverable IF you keep a clone — so if you must, keep a recovery
clone first:
```bash
git clone --depth 1 <remote> /tmp/<repo>_recovery
```

## Do this FIRST (non-destructive, delivers the release now)
1. `.gitignore` everything heavy before committing (this is critical — a naive
   `git add -A` will commit `node_modules/`, often tens of thousands of files):
   ```
   node_modules/
   .env
   *.log
   frontend/build/       # generated — rebuild with your build script
   __pycache__/
   ```
2. Commit, then push to a NEW branch + annotate the release:
   ```bash
   git init -b main
   git add -A && git commit -m "..."
   git tag -a v1.0.0 -m "..."
   git remote add origin <ssh:org>/<repo>.git
   git push origin main:release/<product>-v1.0.0   # new branch, safe
   git push origin v1.0.0
   ```
   New branch + tag always succeed (non-fast-forward is only a problem when
   pushing to an EXISTING branch). Verify with `git ls-remote --heads --tags`.
3. Never `git push -f origin master` without consent; the user's old commits
   belong to them.

## GitHub "Release" page — SSH can't create it
- SSH CAN push branches and `v1.0.0` tags.
- SSH CANNOT create the GitHub **Release** object (the page with notes/binaries),
  and a pushed tag does NOT auto-generate a Release.
- Creating a Release requires API auth: `gh auth login` (device flow, user
  clicks) OR a Fine-grained/classic PAT (`GITHUB_TOKEN`). Do NOT assume one
  exists — check `env | grep -i github`, `gh auth status`, and the credential
  store before promising a Release.
- Report honestly: "code + tag pushed; Release page needs your token / gh auth."

## SSH host alias pattern
Repos often map to per-project aliases like `git@github.com-<project>` in
`~/.ssh/config` with a dedicated `IdentityFile`. Check `~/.ssh/config` for the
matching Host before guessing the URL. Verify read access first with
`git ls-remote <remote>`.
