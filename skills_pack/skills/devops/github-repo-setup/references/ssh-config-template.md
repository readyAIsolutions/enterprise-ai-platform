# SSH Config Templates

## Per-Project SSH Config (Recommended)
Isolates keys per project — prevents key confusion across multiple GitHub orgs/accounts.

```
Host github.com-<project>
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_<project>
    IdentitiesOnly yes
```

Usage: `git@github.com-<project>:org/repo.git`

## Global GitHub Config (Simple)
Single key for all GitHub repos.

```
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

## Multiple GitHub Accounts
Separate identities for work vs personal.

```
# Work account
Host github.com-work
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_work
    IdentitiesOnly yes

# Personal account
Host github.com-personal
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_personal
    IdentitiesOnly yes
```

## Key Generation Commands
```bash
# Ed25519 (modern, fast, small)
ssh-keygen -t ed25519 -C "email@domain.com" -f ~/.ssh/key_name -N ""

# RSA 4096 (legacy compatibility)
ssh-keygen -t rsa -b 4096 -C "email@domain.com" -f ~/.ssh/key_name -N ""
```

## Test Commands
```bash
# Test specific host alias
ssh -T git@github.com-<project>

# Test with verbose output for debugging
ssh -vvv -T git@github.com-<project>

# List keys in agent
ssh-add -l
```