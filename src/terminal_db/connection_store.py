import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional
from terminal_db.config import ConnectionProfile, DbConfig, DbType, SshConfig

logger = logging.getLogger(__name__)


class ConnectionStore:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            config_dir = Path.home() / ".terminal_db"
            config_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(config_dir / "connections.db")
        
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    db_type TEXT NOT NULL DEFAULT 'oracle',
                    db_host TEXT NOT NULL,
                    db_port INTEGER NOT NULL DEFAULT 1521,
                    db_service_name TEXT,
                    db_sid TEXT,
                    db_username TEXT NOT NULL,
                    db_password TEXT NOT NULL,
                    db_mode TEXT DEFAULT 'NORMAL',
                    ssh_enabled INTEGER DEFAULT 0,
                    ssh_host TEXT,
                    ssh_port INTEGER DEFAULT 22,
                    ssh_username TEXT,
                    ssh_key_path TEXT,
                    ssh_password TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Migrate: add db_type column if missing (existing databases)
            try:
                conn.execute("ALTER TABLE connections ADD COLUMN db_type TEXT NOT NULL DEFAULT 'oracle'")
            except sqlite3.OperationalError:
                pass
            conn.commit()

    def save(self, profile: ConnectionProfile) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT OR REPLACE INTO connections (
                    name, db_type, db_host, db_port, db_service_name, db_sid,
                    db_username, db_password, db_mode,
                    ssh_enabled, ssh_host, ssh_port, ssh_username, ssh_key_path, ssh_password
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                profile.name,
                profile.db.db_type.value,
                profile.db.host,
                profile.db.port,
                profile.db.service_name,
                profile.db.sid,
                profile.db.username,
                profile.db.password,
                profile.db.mode,
                1 if profile.ssh.enabled else 0,
                profile.ssh.host,
                profile.ssh.port,
                profile.ssh.username,
                profile.ssh.key_path,
                profile.ssh.password,
            ))
            conn.commit()
            return cursor.lastrowid

    def load(self, name: str) -> Optional[ConnectionProfile]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM connections WHERE name = ?", (name,)).fetchone()
            
            if row is None:
                return None
            
            return ConnectionProfile(
                name=row["name"],
                db=DbConfig(
                    db_type=DbType(row["db_type"]),
                    host=row["db_host"],
                    port=row["db_port"],
                    service_name=row["db_service_name"] or "",
                    sid=row["db_sid"],
                    username=row["db_username"],
                    password=row["db_password"],
                    mode=row["db_mode"],
                ),
                ssh=SshConfig(
                    enabled=bool(row["ssh_enabled"]),
                    host=row["ssh_host"] or "",
                    port=row["ssh_port"],
                    username=row["ssh_username"] or "",
                    key_path=row["ssh_key_path"],
                    password=row["ssh_password"],
                ),
            )

    def list_all(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT id, name, db_host, db_port, ssh_enabled FROM connections ORDER BY name").fetchall()
            return [dict(row) for row in rows]

    def delete(self, name: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM connections WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0

    def update_timestamp(self, name: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE connections SET updated_at = CURRENT_TIMESTAMP WHERE name = ?", (name,))
            conn.commit()
