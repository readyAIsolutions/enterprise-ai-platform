# Known Daemon Processes That Recreate Folders

## ENI KB Daemon
- **Process**: `python3 -m daemon.eni_kb_daemon --daemon`
- **Recreates**: `~/Desktop/ENI_KB/`
- **Kill**: `pkill -9 -f "eni_kb_daemon"`

## ENI Compression Swarm
- **Processes**:
  - `python3 eni_master_compression_driver.py`
  - `python3 eni_impossible_swarm.py`
  - Fork server children (multiple PIDs with same cmdline)
- **Recreates**: `~/Desktop/eni_compression/`
- **Kill**: `pkill -9 -f "eni_master_compression_driver.py" && pkill -9 -f "eni_impossible_swarm.py"`

## ENI Swarm Floor Scripts
- **Processes**: `bash /tmp/eni_opt/run_*.sh` (D3D, SB, NAS, LUM workers)
- **Recreates**: Working directories under `~/Desktop/` if launched from there
- **Kill**: `pkill -9 -f "run_.*\.sh"`

## Detection Pattern
```bash
# Find processes holding a path open
lsof | grep <folder_name>

# Find processes by cwd
ls -la /proc/*/cwd 2>/dev/null | grep <folder_name>
```