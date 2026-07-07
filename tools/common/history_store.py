"""過去の会話(入力・出力)を検索可能な形でPostgreSQLに保持するストア。

LangGraph の PostgresSaver はスレッド単位のチェックポイントであり、
会話をまたいだ横断検索には向かない(スレッドごとに独立したブロブとして
保存される)。AI Agent が「以前の会話」を検索して回答できるようにする
ため、ターンごとの入力・出力を別テーブルにフラットに記録する。
"""
from __future__ import annotations

import os
from functools import lru_cache

import psycopg
import structlog

log = structlog.get_logger()

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS conversation_history (
    id BIGSERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS conversation_history_user_id_idx ON conversation_history (user_id);
"""


class ConversationHistoryStore:
    def __init__(self, db_url: str):
        self._db_url = db_url
        with psycopg.connect(self._db_url) as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.commit()

    def log_turn(self, thread_id: str, user_id: str, role: str, content: str) -> None:
        try:
            with psycopg.connect(self._db_url) as conn:
                conn.execute(
                    "INSERT INTO conversation_history (thread_id, user_id, role, content) "
                    "VALUES (%s, %s, %s, %s)",
                    (thread_id, user_id, role, content),
                )
                conn.commit()
        except Exception as e:
            log.error("conversation_history_log_failed", thread_id=thread_id, error=str(e))

    def search(self, user_id: str, query: str, limit: int = 5) -> list[dict]:
        with psycopg.connect(self._db_url) as conn:
            rows = conn.execute(
                "SELECT thread_id, role, content, created_at FROM conversation_history "
                "WHERE user_id = %s AND content ILIKE %s "
                "ORDER BY created_at DESC LIMIT %s",
                (user_id, f"%{query}%", limit),
            ).fetchall()
        return [
            {"thread_id": r[0], "role": r[1], "content": r[2], "created_at": r[3].isoformat()}
            for r in rows
        ]


@lru_cache(maxsize=1)
def get_history_store() -> ConversationHistoryStore | None:
    db_url = os.environ.get("AGENT_DB_URL")
    if not db_url:
        return None
    return ConversationHistoryStore(db_url)
