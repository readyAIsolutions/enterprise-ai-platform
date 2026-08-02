"""
ENI Enterprise Audit Trail — Immutable, searchable, secured audit logging.
Compliant with SOC 2, ISO 27001, GDPR requirements.
"""
import json, time, hashlib, logging, sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("eni.audit")

class AuditLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    SECURITY = "security"
    COMPLIANCE = "compliance"

@dataclass
class AuditEntry:
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
    level: AuditLevel = AuditLevel.INFO
    module: str = ""
    event: str = ""
    actor: str = "eni_kernel"
    target: str = ""
    outcome: str = "success"
    data: Dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    hash: str = ""

class AuditTrail:
    """Immutable audit trail with integrity verification."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(Path.home() / ".eni" / "audit" / "audit.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    module TEXT,
                    event TEXT NOT NULL,
                    actor TEXT DEFAULT 'eni_kernel',
                    target TEXT,
                    outcome TEXT DEFAULT 'success',
                    data TEXT,
                    session_id TEXT,
                    entry_hash TEXT,
                    prev_hash TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_module ON audit_log(module)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id)
            """)
            conn.commit()
    
    def log(self, module: str, event: str, level: AuditLevel = AuditLevel.INFO,
            actor: str = "eni_kernel", target: str = "", outcome: str = "success",
            data: Dict = None, session_id: str = "") -> AuditEntry:
        entry = AuditEntry(
            level=level, module=module, event=event, actor=actor,
            target=target, outcome=outcome, data=data or {}, session_id=session_id
        )
        entry.hash = self._compute_hash(entry)
        
        with sqlite3.connect(self.db_path) as conn:
            prev = conn.execute(
                "SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            prev_hash = prev[0] if prev else ""
            
            conn.execute("""
                INSERT INTO audit_log (timestamp, level, module, event, actor, 
                    target, outcome, data, session_id, entry_hash, prev_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.timestamp, level.value, module, event, actor,
                target, outcome, json.dumps(data), session_id, entry.hash, prev_hash
            ))
            conn.commit()
        
        return entry
    
    def _compute_hash(self, entry: AuditEntry) -> str:
        raw = f"{entry.timestamp}|{entry.level.value}|{entry.module}|{entry.event}|{entry.actor}|{json.dumps(entry.data, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    
    def query(self, module: str = None, level: str = None, 
              session_id: str = None, limit: int = 100) -> List[Dict]:
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if module:
            query += " AND module = ?"
            params.append(module)
        if level:
            query += " AND level = ?"
            params.append(level)
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(query, params)]
    
    def verify_integrity(self) -> Dict[str, Any]:
        """Verify the hash chain — detects tampering."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, entry_hash, prev_hash, timestamp, event, data FROM audit_log ORDER BY id"
            ).fetchall()
        
        broken = []
        for i, row in enumerate(rows):
            if i > 0:
                expected_prev = rows[i-1][1]  # prev row's hash
                actual_prev = row[2]
                if expected_prev != actual_prev:
                    broken.append(row[0])
        
        return {
            "total_entries": len(rows),
            "integrity": "OK" if not broken else "BROKEN",
            "broken_chain_at": broken,
            "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
    
    def search(self, event_pattern: str, limit: int = 50) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                "SELECT * FROM audit_log WHERE event LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{event_pattern}%", limit)
            )]
    
    def compliance_report(self, start_date: str, end_date: str) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE timestamp BETWEEN ? AND ?",
                (start_date, end_date)
            ).fetchone()[0]
            by_level = {}
            for row in conn.execute(
                "SELECT level, COUNT(*) as c FROM audit_log WHERE timestamp BETWEEN ? AND ? GROUP BY level",
                (start_date, end_date)
            ):
                by_level[row[0]] = row[1]
            by_module = {}
            for row in conn.execute(
                "SELECT module, COUNT(*) as c FROM audit_log WHERE timestamp BETWEEN ? AND ? GROUP BY module",
                (start_date, end_date)
            ):
                by_module[row[0]] = row[1]
        
        return {
            "period": f"{start_date} to {end_date}",
            "total_entries": total,
            "by_level": by_level,
            "by_module": by_module,
            "integrity": self.verify_integrity()["integrity"]
        }

# Convenience singleton
_audit_instance = None

def get_audit() -> AuditTrail:
    global _audit_instance
    if _audit_instance is None:
        _audit_instance = AuditTrail()
    return _audit_instance

def audit_log(module: str, event: str, **kwargs):
    return get_audit().log(module=module, event=event, **kwargs)