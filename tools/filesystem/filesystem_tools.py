"""Filesystem Tool — ローカルファイルシステム操作ツール群。

設計原則:
- AI がアクセスできるのは ALLOWED_BASE_DIRS 以下のみ
- 書き込みは requires_approval=True として扱う
- バイナリファイルは読み取り対象外
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any

import structlog
from langchain_core.tools import tool

log = structlog.get_logger(__name__)

_ALLOWED_BASE_DIRS = [
    p for p in os.getenv("FS_ALLOWED_DIRS", "/workspace").split(",") if p
]
_MAX_FILE_SIZE_BYTES = int(os.getenv("FS_MAX_FILE_SIZE", str(1 * 1024 * 1024)))  # 1MB


def _resolve_safe(path: str) -> tuple[bool, Path]:
    """パスを解決し、許可ディレクトリ内かを確認。"""
    p = Path(path).resolve()
    for base in _ALLOWED_BASE_DIRS:
        if str(p).startswith(str(Path(base).resolve())):
            return True, p
    return False, p


# ─── Read 系 ──────────────────────────────────────────────────────────────────

@tool
def read_file(file_path: str, encoding: str = "utf-8") -> dict[str, Any]:
    """ファイルの内容を読み取る。

    Args:
        file_path: 読み取るファイルの絶対パス
        encoding: 文字エンコーディング (デフォルト utf-8)
    """
    ok, p = _resolve_safe(file_path)
    if not ok:
        return {"error": f"アクセス禁止パス: {file_path}", "success": False}
    if not p.exists():
        return {"error": f"ファイルが見つかりません: {file_path}", "success": False}
    if not p.is_file():
        return {"error": f"ファイルではありません: {file_path}", "success": False}
    if p.stat().st_size > _MAX_FILE_SIZE_BYTES:
        return {"error": f"ファイルサイズが上限 ({_MAX_FILE_SIZE_BYTES} bytes) を超えています", "success": False}

    try:
        content = p.read_text(encoding=encoding)
    except UnicodeDecodeError:
        return {"error": "バイナリファイルは読み取れません", "success": False}

    log.info("read_file.success", path=str(p), size=len(content))
    return {"path": str(p), "content": content, "size": len(content), "success": True}


@tool
def search_files(
    base_dir: str,
    pattern: str,
    content_keyword: str = "",
    max_results: int = 50,
) -> dict[str, Any]:
    """ファイルを名前パターンまたはコンテンツで検索する。

    Args:
        base_dir: 検索起点ディレクトリ
        pattern: ファイル名パターン (glob 形式) 例 "*.java" "*.py"
        content_keyword: ファイル内容の検索キーワード (省略可)
        max_results: 最大結果件数
    """
    ok, base = _resolve_safe(base_dir)
    if not ok:
        return {"error": f"アクセス禁止パス: {base_dir}", "success": False}
    if not base.is_dir():
        return {"error": f"ディレクトリが見つかりません: {base_dir}", "success": False}

    matches = []
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if not fnmatch.fnmatch(p.name, pattern):
            continue
        if p.stat().st_size > _MAX_FILE_SIZE_BYTES:
            continue

        if content_keyword:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                if content_keyword not in text:
                    continue
            except Exception:
                continue

        matches.append(str(p.relative_to(base)))
        if len(matches) >= max_results:
            break

    log.info("search_files.success", pattern=pattern, keyword=content_keyword, count=len(matches))
    return {"base_dir": str(base), "pattern": pattern, "matches": matches, "count": len(matches), "success": True}


@tool
def list_directory(dir_path: str) -> dict[str, Any]:
    """ディレクトリの内容一覧を取得する。

    Args:
        dir_path: 一覧表示するディレクトリの絶対パス
    """
    ok, p = _resolve_safe(dir_path)
    if not ok:
        return {"error": f"アクセス禁止パス: {dir_path}", "success": False}
    if not p.is_dir():
        return {"error": f"ディレクトリが見つかりません: {dir_path}", "success": False}

    entries = []
    for entry in sorted(p.iterdir()):
        entries.append({
            "name": entry.name,
            "type": "dir" if entry.is_dir() else "file",
            "size": entry.stat().st_size if entry.is_file() else None,
        })

    return {"path": str(p), "entries": entries, "count": len(entries), "success": True}


# ─── Write 系 (承認が必要) ───────────────────────────────────────────────────

@tool
def write_file(file_path: str, content: str, encoding: str = "utf-8") -> dict[str, Any]:
    """ファイルに内容を書き込む (上書き)。

    ⚠️ 既存ファイルは上書きされます。承認が必要です。

    Args:
        file_path: 書き込み先ファイルの絶対パス
        content: 書き込む内容
        encoding: 文字エンコーディング
    """
    ok, p = _resolve_safe(file_path)
    if not ok:
        return {"error": f"アクセス禁止パス: {file_path}", "success": False}

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding=encoding)

    log.warning("write_file.executed", path=str(p), size=len(content))
    return {"path": str(p), "size": len(content), "success": True}
