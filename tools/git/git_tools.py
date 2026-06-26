"""Git Tool — ソースコードリポジトリ操作ツール群。

設計原則:
- AI はソースコードを直接編集せず、ツール経由で検索・読み取りのみ行う
- コミット・ブランチ作成は requires_approval=True として扱う
- リポジトリパスはホワイトリストで制限する
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import structlog
from langchain_core.tools import tool

log = structlog.get_logger(__name__)

# 許可するリポジトリルートパス (環境変数でカンマ区切りで追加可能)
_ALLOWED_ROOTS = [
    p for p in os.getenv("GIT_ALLOWED_ROOTS", "/workspace").split(",") if p
]

_GIT_CMD = "git"


def _validate_repo_path(repo_path: str) -> tuple[bool, str]:
    """リポジトリパスがホワイトリスト内かチェック。"""
    p = Path(repo_path).resolve()
    for root in _ALLOWED_ROOTS:
        if str(p).startswith(str(Path(root).resolve())):
            return True, str(p)
    return False, f"リポジトリパス '{repo_path}' は許可されていません (allowed: {_ALLOWED_ROOTS})"


def _run_git(args: list[str], cwd: str, timeout: int = 30) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [_GIT_CMD, *args], cwd=cwd,
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, f"git コマンドタイムアウト ({timeout}s)"
    except FileNotFoundError:
        return False, "git コマンドが見つかりません"


# ─── Read 系 ──────────────────────────────────────────────────────────────────

@tool
def git_search_source(
    repo_path: str,
    keyword: str,
    file_pattern: str = "",
    max_results: int = 20,
) -> dict[str, Any]:
    """ソースコードをキーワード検索する (git grep)。

    Args:
        repo_path: 検索対象リポジトリのパス
        keyword: 検索キーワード (正規表現可)
        file_pattern: ファイルパターン例 "*.java" "*.py"
        max_results: 最大結果件数
    """
    ok, path = _validate_repo_path(repo_path)
    if not ok:
        return {"error": path, "success": False}

    args = ["grep", "-n", "--color=never", keyword]
    if file_pattern:
        args += ["--", file_pattern]

    ok, output = _run_git(args, cwd=path)
    if not ok and "did not match" in output:
        return {"matches": [], "count": 0, "success": True}
    if not ok:
        return {"error": output, "success": False}

    lines = output.splitlines()[:max_results]
    log.info("git_search_source.success", keyword=keyword, matches=len(lines))
    return {"matches": lines, "count": len(lines), "success": True}


@tool
def git_read_file(repo_path: str, file_path: str, ref: str = "HEAD") -> dict[str, Any]:
    """指定ブランチ/タグのファイル内容を取得する。

    Args:
        repo_path: リポジトリパス
        file_path: リポジトリルートからの相対パス
        ref: ブランチ/タグ/コミットハッシュ (デフォルト HEAD)
    """
    ok, path = _validate_repo_path(repo_path)
    if not ok:
        return {"error": path, "success": False}

    args = ["show", f"{ref}:{file_path}"]
    ok, output = _run_git(args, cwd=path)
    if not ok:
        return {"error": output, "success": False}

    log.info("git_read_file.success", file=file_path, ref=ref)
    return {"file": file_path, "ref": ref, "content": output, "success": True}


@tool
def git_log(repo_path: str, branch: str = "HEAD", max_count: int = 10) -> dict[str, Any]:
    """コミット履歴を取得する。

    Args:
        repo_path: リポジトリパス
        branch: ブランチ名 (デフォルト HEAD)
        max_count: 取得件数
    """
    ok, path = _validate_repo_path(repo_path)
    if not ok:
        return {"error": path, "success": False}

    args = [
        "log", branch,
        f"--max-count={max_count}",
        "--pretty=format:%H|%an|%ae|%ad|%s",
        "--date=short",
    ]
    ok, output = _run_git(args, cwd=path)
    if not ok:
        return {"error": output, "success": False}

    commits = []
    for line in output.splitlines():
        parts = line.split("|", 4)
        if len(parts) == 5:
            commits.append({
                "hash": parts[0],
                "author": parts[1],
                "email": parts[2],
                "date": parts[3],
                "message": parts[4],
            })

    return {"branch": branch, "commits": commits, "success": True}


@tool
def git_list_branches(repo_path: str) -> dict[str, Any]:
    """ローカル・リモートブランチ一覧を取得する。

    Args:
        repo_path: リポジトリパス
    """
    ok, path = _validate_repo_path(repo_path)
    if not ok:
        return {"error": path, "success": False}

    ok, output = _run_git(["branch", "-a", "--format=%(refname:short)"], cwd=path)
    if not ok:
        return {"error": output, "success": False}

    branches = [b for b in output.splitlines() if b]
    return {"branches": branches, "count": len(branches), "success": True}


# ─── Write 系 (承認が必要) ───────────────────────────────────────────────────

@tool
def git_create_branch(repo_path: str, branch_name: str, base_ref: str = "HEAD") -> dict[str, Any]:
    """新しいブランチを作成する。

    ⚠️ リポジトリの状態を変更します。承認が必要です。

    Args:
        repo_path: リポジトリパス
        branch_name: 新しいブランチ名 (feature/xxx 形式推奨)
        base_ref: 起点ブランチ/コミット
    """
    ok, path = _validate_repo_path(repo_path)
    if not ok:
        return {"error": path, "success": False}

    # ブランチ名バリデーション
    import re
    if not re.match(r'^[a-zA-Z0-9/_-]+$', branch_name):
        return {"error": f"ブランチ名に使用できない文字が含まれています: {branch_name}", "success": False}

    ok, output = _run_git(["checkout", "-b", branch_name, base_ref], cwd=path)
    if not ok:
        return {"error": output, "success": False}

    log.warning("git_create_branch.executed", branch=branch_name, base=base_ref, repo=path)
    return {
        "branch": branch_name,
        "base": base_ref,
        "message": f"ブランチ '{branch_name}' を作成しました",
        "success": True,
    }


@tool
def git_commit(repo_path: str, message: str, files: list[str] | None = None) -> dict[str, Any]:
    """変更をコミットする。

    ⚠️ リポジトリの履歴を変更します。承認が必要です。

    Args:
        repo_path: リポジトリパス
        message: コミットメッセージ
        files: ステージするファイル (None の場合 git add -A)
    """
    ok, path = _validate_repo_path(repo_path)
    if not ok:
        return {"error": path, "success": False}

    # ステージング
    stage_args = ["add"] + (files if files else ["-A"])
    ok, out = _run_git(stage_args, cwd=path)
    if not ok:
        return {"error": f"git add 失敗: {out}", "success": False}

    ok, output = _run_git(["commit", "-m", message], cwd=path)
    if not ok:
        return {"error": output, "success": False}

    log.warning("git_commit.executed", message=message, repo=path)
    return {"message": message, "output": output, "success": True}
