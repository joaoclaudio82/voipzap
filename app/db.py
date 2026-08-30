import contextlib
import sqlite3
from pathlib import Path

from app.phones import variants

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    voice_message TEXT NOT NULL,
    context TEXT,
    status TEXT NOT NULL,
    nvoip_response TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(self._connect()) as conn, conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def save_notification(self, phone: str, voice_message: str, context: str | None,
                          status: str, nvoip_response: str) -> int:
        with contextlib.closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "INSERT INTO notifications (phone, voice_message, context, status, nvoip_response) "
                "VALUES (?, ?, ?, ?, ?)",
                (phone, voice_message, context, status, nvoip_response),
            )
            return cur.lastrowid

    def recent_notifications(self, phone: str, limit: int = 3) -> list[dict]:
        # Aceita o número com e sem o nono dígito: o WhatsApp entrega os dois.
        formatos = variants(phone)
        marcadores = ",".join("?" * len(formatos))
        with contextlib.closing(self._connect()) as conn, conn:
            rows = conn.execute(
                f"SELECT * FROM notifications WHERE phone IN ({marcadores}) "
                "ORDER BY id DESC LIMIT ?",
                (*formatos, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_message(self, phone: str, direction: str, text: str) -> int:
        with contextlib.closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "INSERT INTO messages (phone, direction, text) VALUES (?, ?, ?)",
                (phone, direction, text),
            )
            return cur.lastrowid

    def recent_messages(self, phone: str, limit: int = 20) -> list[dict]:
        formatos = variants(phone)
        marcadores = ",".join("?" * len(formatos))
        with contextlib.closing(self._connect()) as conn, conn:
            rows = conn.execute(
                f"SELECT * FROM messages WHERE phone IN ({marcadores}) "
                "ORDER BY id DESC LIMIT ?",
                (*formatos, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]
