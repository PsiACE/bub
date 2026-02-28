"""Message store service for proactive interaction."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Literal


@dataclass
class StoredMessage:
    """Represents a stored message."""

    id: str
    chat_id: int
    thread_id: int | None
    role: str
    name: str | None
    content: str
    tool_call_id: str | None
    tool_calls: list | None
    timestamp: float


class MessageStore:
    """SQLite-based message store with thread-safe access."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._local = threading.local()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            self._init_db(conn)
            self._local.conn = conn
            return conn
        return self._local.conn  # type: ignore[no-any-return]

    def _init_db(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                thread_id INTEGER,
                role TEXT NOT NULL,
                name TEXT,
                content TEXT,
                tool_call_id TEXT,
                tool_calls TEXT,
                timestamp REAL NOT NULL
            )
        """)
        conn.commit()

    def add_message(self, msg: StoredMessage) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO messages
            (id, chat_id, thread_id, role, name, content, tool_call_id, tool_calls, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg.id,
                msg.chat_id,
                msg.thread_id,
                msg.role,
                msg.name,
                msg.content,
                msg.tool_call_id,
                json.dumps(msg.tool_calls) if msg.tool_calls else None,
                msg.timestamp,
            ),
        )
        self._conn.commit()

    def get_messages(self, chat_id: int, thread_id: int | None = None, limit: int = 100) -> list[StoredMessage]:
        if thread_id is not None:
            rows = self._conn.execute(
                """SELECT * FROM messages WHERE chat_id = ? AND thread_id = ?
                ORDER BY timestamp DESC LIMIT ?""",
                (chat_id, thread_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM messages WHERE chat_id = ? AND thread_id IS NULL
                ORDER BY timestamp DESC LIMIT ?""",
                (chat_id, limit),
            ).fetchall()

        messages = []
        for row in reversed(rows):
            messages.append(
                StoredMessage(
                    id=row["id"],
                    chat_id=row["chat_id"],
                    thread_id=row["thread_id"],
                    role=row["role"],
                    name=row["name"],
                    content=row["content"],
                    tool_call_id=row["tool_call_id"],
                    tool_calls=json.loads(row["tool_calls"]) if row["tool_calls"] else None,
                    timestamp=row["timestamp"],
                )
            )
        return messages

    def delete_messages(self, chat_id: int, thread_id: int | None = None) -> None:
        if thread_id is not None:
            self._conn.execute("DELETE FROM messages WHERE chat_id = ? AND thread_id = ?", (chat_id, thread_id))
        else:
            self._conn.execute("DELETE FROM messages WHERE chat_id = ? AND thread_id IS NULL", (chat_id,))
        self._conn.commit()

    def get_last_message_by_role(
        self, chat_id: int, role: Literal["user", "assistant"], thread_id: int | None = None
    ) -> StoredMessage | None:
        """Get the last message by a specific role in a chat."""
        if thread_id is not None:
            row = self._conn.execute(
                """SELECT * FROM messages
                WHERE chat_id = ? AND thread_id = ? AND role = ?
                ORDER BY timestamp DESC LIMIT 1""",
                (chat_id, thread_id, role),
            ).fetchone()
        else:
            row = self._conn.execute(
                """SELECT * FROM messages
                WHERE chat_id = ? AND thread_id IS NULL AND role = ?
                ORDER BY timestamp DESC LIMIT 1""",
                (chat_id, role),
            ).fetchone()

        if row is None:
            return None

        return StoredMessage(
            id=row["id"],
            chat_id=row["chat_id"],
            thread_id=row["thread_id"],
            role=row["role"],
            name=row["name"],
            content=row["content"],
            tool_call_id=row["tool_call_id"],
            tool_calls=json.loads(row["tool_calls"]) if row["tool_calls"] else None,
            timestamp=row["timestamp"],
        )

    def has_unreplied_message(self, chat_id: int, min_age_seconds: float = 300) -> bool:
        """Check if there is a user message that has not been replied to for at least min_age_seconds."""
        last_user = self.get_last_message_by_role(chat_id, "user")
        if last_user is None:
            return False

        last_assistant = self.get_last_message_by_role(chat_id, "assistant")
        if last_assistant is None:
            return (time.time() - last_user.timestamp) >= min_age_seconds

        if last_user.timestamp > last_assistant.timestamp:
            return (time.time() - last_user.timestamp) >= min_age_seconds

        return False

    def get_active_chats(self, since: float) -> list[int]:
        """Get list of chat_ids that have messages since the given timestamp."""
        rows = self._conn.execute(
            "SELECT DISTINCT chat_id FROM messages WHERE timestamp >= ?",
            (since,),
        ).fetchall()
        return [row["chat_id"] for row in rows]

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
