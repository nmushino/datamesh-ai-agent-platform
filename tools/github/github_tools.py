"""GitHub REST/Search API を使ったソースコード調査ツール。

organization 内の各マイクロサービスリポジトリのソースコード・READMEから、
テーブル・トピックの実際の意味(説明文)を推定するために使う。
ローカルチェックアウト済みリポジトリを操作する tools/git/git_tools.py とは異なり、
こちらは GitHub API 経由でリモートリポジトリを直接検索する。
"""
from __future__ import annotations

import os

import httpx
import structlog
from langchain_core.tools import tool

log = structlog.get_logger()

_GITHUB_ORG = os.environ.get("GITHUB_ORG", "quarkusdroneshop")
_API_BASE = "https://api.github.com"


def _headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _default_branch(repo: str) -> str:
    resp = httpx.get(f"{_API_BASE}/repos/{_GITHUB_ORG}/{repo}", headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json().get("default_branch", "main")


@tool
def find_github_files_by_name(repo: str, name_keyword: str, max_results: int = 20) -> dict:
    """
    リポジトリ内の全ファイルパスを取得し、ファイル名にキーワードを含むものを
    絞り込みます。GitHub の Code Search API はこの組織のリポジトリでは
    インデックス遅延により機能しないため、代わりにこちらを使うこと。
    新しく見つかったテーブル・トピックに対応する Entity クラスや Avro
    スキーマファイルを探す際に使う(例: "orders-in" トピック なら
    name_keyword="OrderIn" で検索する)。

    Args:
        repo: リポジトリ名 (例: "quarkusdroneshop-web"。org プレフィックス不要)
        name_keyword: ファイル名に含まれるべきキーワード(大文字小文字を区別しない)
        max_results: 最大取得件数 (1-50)
    """
    log.info("find_github_files_by_name", repo=repo, name_keyword=name_keyword)
    try:
        branch = _default_branch(repo)
        resp = httpx.get(
            f"{_API_BASE}/repos/{_GITHUB_ORG}/{repo}/git/trees/{branch}",
            headers=_headers(), params={"recursive": "1"}, timeout=15,
        )
        resp.raise_for_status()
        tree = resp.json().get("tree", [])
        keyword_lower = name_keyword.lower()
        matches = [
            t["path"] for t in tree
            if t.get("type") == "blob" and keyword_lower in t["path"].lower()
        ]
        return {"repo": repo, "paths": matches[:max_results], "total": len(matches), "success": True}
    except Exception as e:
        log.error("find_github_files_by_name_failed", repo=repo, name_keyword=name_keyword, error=str(e))
        return {"error": f"ファイル検索エラー: {e!s}", "success": False}


@tool
def get_github_file_content(repo: str, path: str) -> dict:
    """
    GitHub リポジトリ内の特定ファイルの内容を取得します。
    search_github_org_code で見つけたファイルの実際の中身(コメント・
    フィールド定義等)を確認するために使う。

    Args:
        repo: リポジトリ名 (例: "quarkusdroneshop-web"。org プレフィックス不要)
        path: ファイルパス (例: "src/main/java/.../Order.java")
    """
    log.info("get_github_file_content", repo=repo, path=path)
    try:
        resp = httpx.get(
            f"{_API_BASE}/repos/{_GITHUB_ORG}/{repo}/contents/{path}",
            headers=_headers(), timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        import base64
        content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
        MAX_CHARS = 4000
        return {"repo": repo, "path": path, "content": content[:MAX_CHARS], "success": True}
    except Exception as e:
        log.error("get_github_file_content_failed", repo=repo, path=path, error=str(e))
        return {"error": f"ファイル取得エラー: {e!s}", "success": False}


@tool
def get_github_readme(repo: str) -> dict:
    """
    GitHub リポジトリの README.md の内容を取得します。
    そのリポジトリ(マイクロサービス)が何を担当しているかの概要を
    把握するために使う。

    Args:
        repo: リポジトリ名 (例: "quarkusdroneshop-web"。org プレフィックス不要)
    """
    log.info("get_github_readme", repo=repo)
    try:
        resp = httpx.get(
            f"{_API_BASE}/repos/{_GITHUB_ORG}/{repo}/readme",
            headers=_headers(), timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        import base64
        content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
        MAX_CHARS = 3000
        return {"repo": repo, "content": content[:MAX_CHARS], "success": True}
    except Exception as e:
        log.error("get_github_readme_failed", repo=repo, error=str(e))
        return {"error": f"README取得エラー: {e!s}", "success": False}


@tool
def list_github_org_repos() -> dict:
    """
    GitHub organization 内の全リポジトリ一覧を取得します。
    どのリポジトリが関連しているか分からない場合に、まずこれで一覧を
    確認してから対象を絞り込むために使う。
    """
    log.info("list_github_org_repos")
    try:
        resp = httpx.get(
            f"{_API_BASE}/orgs/{_GITHUB_ORG}/repos",
            headers=_headers(), params={"per_page": 100}, timeout=15,
        )
        resp.raise_for_status()
        repos = [{"name": r.get("name"), "description": r.get("description") or ""} for r in resp.json()]
        return {"repos": repos, "total": len(repos), "success": True}
    except Exception as e:
        log.error("list_github_org_repos_failed", error=str(e))
        return {"error": f"リポジトリ一覧取得エラー: {e!s}", "success": False}
