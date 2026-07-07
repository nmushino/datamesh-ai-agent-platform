"""アプリ全体で共有する設定値(定期チェック頻度等)を PostgreSQL に保持するストア。

ユーザーごとではなく全ユーザー共通の設定であるため、ブラウザの
localStorage ではなくバックエンドの DB に永続化し、Pod 再起動後も
設定値を維持する。
"""
from __future__ import annotations

import os
from functools import lru_cache

import psycopg
import structlog

log = structlog.get_logger()

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class SettingsStore:
    def __init__(self, db_url: str):
        self._db_url = db_url
        with psycopg.connect(self._db_url) as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.commit()

    def get(self, key: str, default: str | None = None) -> str | None:
        with psycopg.connect(self._db_url) as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = %s", (key,)).fetchone()
        return row[0] if row else default

    def set(self, key: str, value: str) -> None:
        with psycopg.connect(self._db_url) as conn:
            conn.execute(
                "INSERT INTO app_settings (key, value, updated_at) VALUES (%s, %s, now()) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                (key, value),
            )
            conn.commit()


@lru_cache(maxsize=1)
def get_settings_store() -> SettingsStore | None:
    db_url = os.environ.get("AGENT_DB_URL")
    if not db_url:
        return None
    return SettingsStore(db_url)
