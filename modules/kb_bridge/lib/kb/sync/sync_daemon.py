"""
ENI Sync Daemon — CRDT-based Peer Synchronization
==================================================
Bi-directional sync across machines using merkle-tree versioning.
"""
from __future__ import annotations

import os
import sys
import json
import time
import socket
import hashlib
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor

# ─── Configuration ─────────────────────────────────────────────────────────
SYNC_DIRS = [
    Path("/home/hunter/.hermes/skills"),
    Path("/home/hunter/.hermes/memories"),
    Path("/home/hunter/Commander/eni_swarm"),
    Path("/home/hunter/Desktop/eni_compression"),
]
STATE_FILE = Path("/home/hunter/.cache/eni_sync/state.json")
PEER_CONFIG = Path("/home/hunter/.config/eni/sync_peers.json")

for d in [STATE_FILE.parent, PEER_CONFIG.parent]:
    d.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("eni_sync")
log.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
log.addHandler(handler)


# ─── Data Structures ───────────────────────────────────────────────────────
@dataclass
class FileEntry:
    path: str
    size: int
    mtime: float
    hash: str
    version: int = 1


@dataclass
class SyncState:
    files: Dict[str, FileEntry] = field(default_factory=dict)
    peer_versions: Dict[str, Dict[str, int]] = field(default_factory=dict)
    last_sync: float = 0


# ─── Core Functions ────────────────────────────────────────────────────────
def compute_hash(path: Path) -> str:
    h = hashlib.blake2b()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_sync_dirs() -> Dict[str, FileEntry]:
    entries = {}
    for sync_dir in SYNC_DIRS:
        if not sync_dir.exists():
            continue
        for f in sync_dir.rglob("*"):
            if f.is_file():
                try:
                    rel = f.relative_to(sync_dir).as_posix()
                    stat = f.stat()
                    entries[rel] = FileEntry(
                        path=rel,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                        hash=compute_hash(f),
                    )
                except Exception:
                    pass
    return entries


def load_state() -> SyncState:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            state = SyncState()
            state.files = {k: FileEntry(**v) for k, v in data.get("files", {}).items()}
            state.peer_versions = data.get("peer_versions", {})
            state.last_sync = data.get("last_sync", 0)
            return state
        except Exception:
            pass
    return SyncState()


def save_state(state: SyncState):
    data = {
        "files": {k: asdict(v) for k, v in state.files.items()},
        "peer_versions": state.peer_versions,
        "last_sync": state.last_sync,
    }
    STATE_FILE.write_text(json.dumps(data, indent=2))


def load_peers() -> List[Dict]:
    if PEER_CONFIG.exists():
        try:
            return json.loads(PEER_CONFIG.read_text())
        except Exception:
            pass
    return [
        {"name": "laptop", "host": "192.168.1.50", "port": 8766, "enabled": True},
        {"name": "server", "host": "10.0.0.10", "port": 8766, "enabled": True},
    ]


def save_peers(peers: List[Dict]):
    PEER_CONFIG.write_text(json.dumps(peers, indent=2))


def sync_with_peer(peer: Dict, state: SyncState) -> bool:
    if not peer.get("enabled", True):
        return True

    host = peer["host"]
    port = peer.get("port", 8766)

    try:
        sock = socket.create_connection((host, port), timeout=10)
        sock.settimeout(30)

        # Send our manifest
        manifest = {k: asdict(v) for k, v in state.files.items()}
        sock.sendall(json.dumps({"type": "manifest", "files": manifest}).encode() + b"\n")

        # Receive peer's manifest
        response = sock.recv(65536).decode()
        peer_manifest = json.loads(response)

        # Determine what we need
        our_versions = {k: v.version for k, v in state.files.items()}
        peer_files = peer_manifest.get("files", {})
        peer_versions = {k: v.get("version", 1) for k, v in peer_files.items()}

        # Request missing/newer files
        for fname, pver in peer_versions.items():
            our_ver = our_versions.get(fname, 0)
            if pver > our_ver:
                sock.sendall(json.dumps({"type": "request", "file": fname}).encode() + b"\n")

                # Receive file data
                data = b""
                while True:
                    chunk = sock.recv(8192)
                    if not chunk:
                        break
                    data += chunk
                    if len(chunk) < 8192:
                        break

                # Save file to first matching sync dir
                for sync_dir in SYNC_DIRS:
                    target = sync_dir / fname
                    if target.parent.exists() or target.parent.mkdir(parents=True, exist_ok=True):
                        target.write_bytes(data)
                        break

        # Update peer version tracking
        state.peer_versions[peer["name"]] = peer_versions
        state.last_sync = time.time()
        save_state(state)

        sock.close()
        log.info(f"Synced with {peer['name']} ({host}:{port})")
        return True

    except Exception as e:
        log.warning(f"Sync with {peer['name']} failed: {e}")
        return False


def run_sync_server():
    """Run the sync server that peers connect to."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 8766))
    sock.listen(5)
    log.info("Sync server listening on 0.0.0.0:8766")

    while True:
        conn, addr = sock.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


def handle_client(conn: socket.socket, addr):
    try:
        data = conn.recv(65536).decode()
        if not data:
            return
        msg = json.loads(data)

        state = load_state()

        if msg.get("type") == "manifest":
            # Send our manifest back
            manifest = {k: asdict(v) for k, v in state.files.items()}
            conn.sendall(json.dumps({"type": "manifest", "files": manifest}).encode() + b"\n")

            # Handle file requests
            while True:
                req_data = conn.recv(4096).decode()
                if not req_data:
                    break
                req = json.loads(req_data)
                if req.get("type") == "request":
                    fname = req.get("file")
                    if fname in state.files:
                        # Find the actual file
                        for sync_dir in SYNC_DIRS:
                            fpath = sync_dir / fname
                            if fpath.exists():
                                conn.sendall(fpath.read_bytes())
                                break
                    else:
                        conn.sendall(b"NOT_FOUND")
    except Exception as e:
        log.debug(f"Client error: {e}")
    finally:
        conn.close()


def sync_loop():
    state = load_state()
    peers = load_peers()

    backoff = 5
    max_backoff = 300

    while True:
        try:
            # Scan local changes
            current = scan_sync_dirs()
            for fname, entry in current.items():
                if fname not in state.files or state.files[fname].hash != entry.hash:
                    entry.version = state.files.get(fname, FileEntry("", 0, 0, "", 0)).version + 1
                    state.files[fname] = entry
            save_state(state)

            # Sync with peers
            success_count = 0
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(sync_with_peer, p, state) for p in peers]
                for f in futures:
                    if f.result():
                        success_count += 1

            if success_count > 0:
                backoff = 5
                log.info(f"Sync cycle complete: {success_count}/{len(peers)} peers OK")
            else:
                log.warning(f"All peers failed, backing off {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

        except Exception as e:
            log.error(f"Sync loop error: {e}")
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ENI Sync Daemon")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon (server + client)")
    parser.add_argument("--server", action="store_true", help="Run sync server only")
    parser.add_argument("--once", action="store_true", help="Run one sync cycle and exit")
    parser.add_argument("--peers", help="Edit peer config")
    args = parser.parse_args()

    if args.peers:
        peers = load_peers()
        print(json.dumps(peers, indent=2))
        return

    if args.server:
        run_sync_server()
    elif args.once:
        state = load_state()
        peers = load_peers()
        for p in peers:
            sync_with_peer(p, state)
    else:
        log.info("Starting ENI Sync Daemon (client + server)")
        threading.Thread(target=run_sync_server, daemon=True).start()
        sync_loop()


if __name__ == "__main__":
    main()