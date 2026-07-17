"""Platform Ops Agent — OpenShift/Git/Filesystem ツールを使うプラットフォーム運用エージェント。

責任範囲:
- OpenShift クラスターの状態確認・Pod ログ取得・Deployment 再起動
- ソースコード検索・ブランチ作成
- ローカルファイルの読み取り・検索

設計原則:
- AI は推論と指示のみを行い、クラスター操作は Tool 経由
- 破壊的操作 (scale/restart/apply) は必ず Human-in-the-Loop で承認を経る
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.prebuilt import create_react_agent

from agent.common.llm import get_llm
from tools.openshift.openshift_tools import (
    apply_manifest,
    get_deployment_status,
    get_events,
    get_pod_logs,
    get_pods,
    list_namespaces,
    list_routes,
    list_services,
    list_sites,
    restart_deployment,
    scale_deployment,
)
from tools.git.git_tools import (
    git_commit,
    git_create_branch,
    git_list_branches,
    git_log,
    git_read_file,
    git_search_source,
)
from tools.filesystem.filesystem_tools import (
    list_directory,
    read_file,
    search_files,
    write_file,
)

_SYSTEM_PROMPT = """\
あなたは Datamesh AI Agent Platform のプラットフォーム運用エージェントです。

## 責任
- OpenShift クラスターの状態監視と障害対応支援 (自身のドメインおよびA/B/Cサイト)
- ソースコードの検索・調査
- ファイルシステムの読み取り・検索

## サイトについて
このAI Agent自身が動いているクラスター(「自身のドメイン」)に加えて、
quarkusdroneshop-demo が稼働するA/Bサイト/Cサイトの3クラスターについても
問い合わせできる。get_pods / list_namespaces / list_services / list_routes は
`site` 引数を受け付ける:
  - 指定しない(空文字) → 自身のドメイン(このAI Agentが動いているクラスター)
  - "asite" → Aサイト
  - "bsite" → Bサイト
  - "csite" → Cサイト
ユーザーがどのサイトを指しているか曖昧な場合は、まず list_sites で
問い合わせ可能なサイト一覧(接続情報が設定済みかどうかも含む)を確認し、
必要であればユーザーに確認すること。接続情報が未設定のサイトを問い合わせると
エラーになるので、その場合はエラー内容(どの環境変数が必要か)をそのまま伝えること。

## 厳守ルール
1. **クラスター変更操作** (restart_deployment, scale_deployment, apply_manifest) は
   必ずユーザーに操作内容と影響を説明してから実行すること
2. write_file, git_commit, git_create_branch は承認必須
3. 本番環境 (namespace が *-prod) への変更は二重確認すること
4. ログやソースコードに含まれる機密情報 (パスワード/トークン) は出力しないこと
5. restart_deployment / scale_deployment / apply_manifest は自身のドメインのみに
   対応しており、A/B/Cサイトへの書き込み操作はできない(閲覧のみ)

## 調査の進め方
1. まず get_pods / get_deployment_status / list_namespaces / list_services /
   list_routes で現状把握 (対象サイトが不明な場合は list_sites で確認)
2. 異常があれば get_pod_logs / get_events で原因調査 (自身のドメインのみ)
3. ソースコードを確認する場合は git_search_source → git_read_file の順
4. 調査結果と推奨アクションを明確に報告してから操作を提案する
"""

# 読み取り専用ツール (自動実行可)
_READ_TOOLS = [
    list_sites,
    list_namespaces,
    get_pods,
    list_services,
    list_routes,
    get_pod_logs,
    get_deployment_status,
    get_events,
    git_search_source,
    git_read_file,
    git_log,
    git_list_branches,
    read_file,
    search_files,
    list_directory,
]

# 書き込み系ツール (Human-in-the-Loop で承認後に実行)
_WRITE_TOOLS = [
    restart_deployment,
    scale_deployment,
    apply_manifest,
    git_create_branch,
    git_commit,
    write_file,
]

# 承認が必要なツール名セット (orchestrator の human_approval_node で参照)
APPROVAL_REQUIRED_TOOLS = {
    "restart_deployment",
    "scale_deployment",
    "apply_manifest",
    "git_commit",
    "git_create_branch",
    "write_file",
}


@lru_cache(maxsize=1)
def create_platform_ops_agent():
    """Platform Ops Agent を生成して返す。LRU キャッシュで1インスタンスのみ保持。"""
    llm = get_llm()
    all_tools = _READ_TOOLS + _WRITE_TOOLS

    return create_react_agent(
        model=llm,
        tools=all_tools,
        state_modifier=_SYSTEM_PROMPT,
    )
