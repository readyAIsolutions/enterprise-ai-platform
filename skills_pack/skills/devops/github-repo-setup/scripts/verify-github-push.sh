#!/usr/bin/env bash
# verify-github-push.sh — Post-push verification for GitHub repository setup
# Usage: ./verify-github-push.sh [remote-name] [branch-name]
# Defaults: remote=origin, branch=main

set -euo pipefail

REMOTE="${1:-origin}"
BRANCH="${2:-main}"

echo "=== GitHub Push Verification ==="
echo "Remote: $REMOTE"
echo "Branch: $BRANCH"
echo

# 1. Check local status
echo "1. Local repository status:"
git status --short
if [[ -n $(git status --porcelain) ]]; then
    echo "   ⚠ Working tree not clean"
else
    echo "   ✓ Working tree clean"
fi
echo

# 2. Check remote configuration
echo "2. Remote configuration:"
git remote -v | grep "$REMOTE" || echo "   ⚠ Remote '$REMOTE' not found"
echo

# 3. Check branch tracking
echo "3. Branch tracking:"
git branch -vv | grep "^\* $BRANCH" || echo "   ⚠ Not on branch '$BRANCH'"
echo

# 4. Compare local vs remote
echo "4. Local vs remote commit comparison:"
LOCAL_COMMIT=$(git rev-parse HEAD)
REMOTE_COMMIT=$(git rev-parse "$REMOTE/$BRANCH" 2>/dev/null || echo "none")

echo "   Local:  $LOCAL_COMMIT"
echo "   Remote: $REMOTE_COMMIT"

if [[ "$LOCAL_COMMIT" == "$REMOTE_COMMIT" ]]; then
    echo "   ✓ Local and remote are in sync"
else
    echo "   ⚠ Local and remote differ"
    echo "   Run: git log --oneline $REMOTE/$BRANCH..HEAD  (local ahead)"
    echo "   Run: git log --oneline HEAD..$REMOTE/$BRANCH  (remote ahead)"
fi
echo

# 5. Verify GitHub accessibility (if gh CLI available)
if command -v gh &> /dev/null; then
    echo "5. GitHub CLI verification:"
    REPO_URL=$(git remote get-url "$REMOTE" 2>/dev/null | sed 's/git@github.com[-a-zA-Z0-9]*:/https:\/\/github.com\//' | sed 's/\.git$//')
    if [[ -n "$REPO_URL" ]]; then
        echo "   Repo: $REPO_URL"
        gh repo view "$REPO_URL" --json name,visibility,defaultBranchRef,updatedAt 2>/dev/null | jq -r '"   Name: \(.name)\n   Visibility: \(.visibility)\n   Default branch: \(.defaultBranchRef.name)\n   Updated: \(.updatedAt)"' || echo "   (gh auth needed or repo not accessible)"
    fi
else
    echo "5. GitHub CLI not installed — skipping remote verification"
fi
echo

# 6. Check for common issues
echo "6. Common issue checks:"

# Check for .gitignore
if [[ -f .gitignore ]]; then
    echo "   ✓ .gitignore exists"
    # Check for __pycache__ in gitignore
    if grep -q "__pycache__" .gitignore; then
        echo "   ✓ __pycache__ ignored"
    else
        echo "   ⚠ __pycache__ NOT in .gitignore"
    fi
else
    echo "   ⚠ .gitignore missing"
fi

# Check for committed bytecode
if git ls-files | grep -q "__pycache__\|\.pyc$"; then
    echo "   ⚠ Python bytecode files tracked in git"
    git ls-files | grep "__pycache__\|\.pyc$" | head -5
else
    echo "   ✓ No Python bytecode tracked"
fi

# Check for large files
LARGE_FILES=$(git ls-files -s | awk '$4 > 10000000 {print $4 " bytes: " $5}' | head -5)
if [[ -n "$LARGE_FILES" ]]; then
    echo "   ⚠ Large files (>10MB) tracked:"
    echo "$LARGE_FILES"
else
    echo "   ✓ No large files tracked"
fi

echo
echo "=== Verification Complete ==="