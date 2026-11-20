"""Small SQLite persistence layer; each operation owns its connection."""

import sqlite3
from pathlib import Path


def database_path(database_url: str) -> str:
    """Convert the documented sqlite URL into a filesystem path."""
    if not database_url.startswith("sqlite:///"):
        raise ValueError("DATABASE_URL must use SQLite (sqlite:///...)")
    path = database_url[len("sqlite:///"):]
    # Four slashes mean an absolute Unix path (for example /data/app.db).
    if database_url.startswith("sqlite:////"):
        path = "/" + path.lstrip("/")
    return path


class Database:
    """Create the required messages table and provide simple history queries."""

    def __init__(self, url: str):
        self.path = database_path(url)
        self._uri = self.path == ":memory:"
        if not self._uri:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, uri=self._uri, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        """Build schema automatically and index chronological session reads."""
        with self.connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)")
            connection.execute("""CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                system_prompt TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )""")

    def history(self, session_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def session_exists(self, session_id: str) -> bool:
        with self.connect() as connection:
            return connection.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)).fetchone() is not None

    def get_system_prompt(self, session_id: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute("SELECT system_prompt FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return row[0] if row else None

    def save_turn(self, session_id: str, user_message: str, reply: str, metadata: dict, system_prompt: str) -> None:
        """Persist both sides only after inference succeeds, in one transaction."""
        import json

        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sessions(session_id, system_prompt) VALUES (?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET system_prompt = excluded.system_prompt",
                (session_id, system_prompt),
            )
            connection.execute("INSERT INTO messages(session_id, role, content) VALUES (?, 'user', ?)", (session_id, user_message))
            connection.execute(
                "INSERT INTO messages(session_id, role, content, metadata) VALUES (?, 'assistant', ?, ?)",
                (session_id, reply, json.dumps(metadata)),
            )
