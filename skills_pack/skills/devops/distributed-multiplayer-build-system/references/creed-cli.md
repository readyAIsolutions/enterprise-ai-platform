# CREED Unified CLI Reference

## Overview
Single entry point `creed.py` replacing `creed_client/submit_task.py` with all commands:

## Commands

### Task Submission
```bash
creed submit --name "build" --prompt "..." --workdir "~/proj" \
  --target-client <id> --required-providers openrouter --required-tags gpu,eni-swarm
```

### File Sync (Remote Build Workflow)
```bash
# Push local files to remote client's WORKDIR
creed push-files --target-client <id> ./src ./include --dest-dir project/

# Pull artifacts from remote client
creed pull-files --target-client <id> --patterns "*.so,*.a" --src-dir build/

# List files on remote client
creed list-files --target-client <id> --dir-path project/
```

### Shared Workdir (SSHFS/NFS)
```bash
# Setup (once per machine)
creed shared-workdir setup --remote user@build:/shared --local ~/creed_shared

# Mount before building
creed shared-workdir mount

# Check status
creed shared-workdir status

# Unmount
creed shared-workdir unmount
```

### Monitoring
```bash
creed clients           # List connected clients with capabilities
creed list              # All tasks (queued/active/completed)
creed status <task_id>  # Detailed task status + result
```

## Architecture
- `creed.py` → calls async functions from `creed_client/submit_task.py`
- All HTTP calls go to server REST API (`/api/*`)
- Server forwards file sync via WebSocket (`FILE_SYNC_*` messages)
- Client receives files into local `WORKDIR` with hash verification

## File Sync Protocol

### Push Flow
```
Local CLI → HTTP POST /api/files/push → Server → WS FILE_SYNC_PUSH → Target Client
Target Client writes to WORKDIR/dest_dir/ → WS FILE_SYNC_ACK → Server → HTTP 200 → CLI
```

### Pull Flow
```
Local CLI → HTTP POST /api/files/pull → Server → WS FILE_SYNC_PULL → Target Client
Target Client reads WORKDIR/src_dir/ → WS FILE_SYNC_ACK(files+base64) → Server → HTTP 200 → CLI
```

### List Flow
```
Local CLI → HTTP POST /api/files/list → Server → WS FILE_SYNC_LIST → Target Client
Target Client lists WORKDIR/dir_path/ → WS FILE_SYNC_ACK(files+metadata) → Server → HTTP 200 → CLI
```

## Integration with Task Submission
```bash
# 1. Push source to target
creed push-files --target-client abc123 ./src --dest-dir project/

# 2. Submit build task (runs on target's WORKDIR/project/)
creed submit --name "build" --prompt "Build C++ project in project/" \
  --workdir "~/creed_work/project" --target-client abc123

# 3. Pull artifacts when done
creed pull-files --target-client abc123 --patterns "*.so,*.a" --src-dir project/
```