from datetime import datetime, timezone
from typing import Literal

import structlog
from langchain_core.tools import tool

from tools.common.client import get_openmetadata_client

log = structlog.get_logger()

# ツール付きエージェントの max_tokens はコンテキスト長節約のため 2048 に
# クランプされている (agent/orchestrator/graph.py の _TOOL_AGENT_MAX_TOKENS_CAP)。
# プロンプトで「limitは15〜20程度に」と指示するだけではモデルが守らないことが
# あり、対象(例:1サイトの全トピック)によっては件数が多すぎて要約がこの
# トークン予算に収まらず、コンテキスト長超過で応答が途中で切れる。
# そのためモデルが指定した limit に関わらず、ここで確実に上限をかける。
_MAX_ASSETS_PER_CALL = 15

# 15件全件に説明文を付けたままだと、件数が多い場合(例:1サイトの全トピック)
# モデルが表全体を書き出すだけでmax_tokens予算を使い切ってしまい、
# コンテキスト長超過で応答が途中で切れることが確認された。
# そのため、件数が多い場合は「安全に説明文まで書ける件数」までは詳細
# (説明文付き)を返し、それ以降は名前とFQNのみ(説明文は省略)にする。
# FQN列はフロントエンド側で自動的にOpenMetadataへのリンクに変換される
# ため、説明文が無くても参照は可能。
_FULL_DETAIL_ASSET_COUNT = 8


@tool
def search_data_assets(
    query: str,
    asset_type: Literal["table", "topic", "pipeline", "data_product", "all"] = "all",
    limit: int = 10,
) -> dict:
    """
    OpenMetadata のデータ資産を自然言語クエリで検索します。

    Args:
        query: 検索クエリ (例: "顧客の注文履歴", "drone delivery")
        asset_type: 絞り込む資産タイプ。"table", "topic", "pipeline", "data_product", "all" のいずれか。
            「データプロダクト」を尋ねられた場合は必ず "data_product" を指定すること。
        limit: 最大取得件数 (1件以上を指定可能だが、実際には1回の呼び出しあたり
            最大15件までに制限される。それ以上必要な場合は複数回に分けて呼び出すこと)
    """
    log.info("search_data_assets", query=query, asset_type=asset_type)
    # NOTE: description (特にデータプロダクト/契約情報) が非常に長い場合があり、
    # 未加工のまま複数件返すと vLLM の max-model-len (8192) を容易に超えるため切り詰める
    DESCRIPTION_MAX_CHARS = 150
    effective_limit = min(max(int(limit), 1), _MAX_ASSETS_PER_CALL)
    try:
        client = get_openmetadata_client()
        results = client.search_assets(query, asset_type, effective_limit)
        assets = [
            _to_asset_dict(
                r,
                asset_type,
                DESCRIPTION_MAX_CHARS if i < _FULL_DETAIL_ASSET_COUNT else 0,
            )
            for i, r in enumerate(results)
        ]
        truncated = len(assets) == _MAX_ASSETS_PER_CALL
        result = {"assets": assets, "total": len(assets), "query": query, "success": True}
        if len(assets) > _FULL_DETAIL_ASSET_COUNT:
            result["note"] = (
                f"件数が多いため、{_FULL_DETAIL_ASSET_COUNT}件目以降は説明文を省略している"
                "(description が空文字列)。それらは名前とFQNのみを行に含め、"
                "説明文の代わりに「詳細はFQNのリンク先を参照」のように書くこと。"
            )
        if truncated:
            result["note"] = result.get("note", "") + (
                f" 1回の呼び出しにつき最大{_MAX_ASSETS_PER_CALL}件までしか返せない制限があり、"
                "他にも該当する資産が存在する可能性があります。"
            )
        return result
    except Exception as e:
        log.error("search_data_assets_failed", query=query, error=str(e))
        return {"error": f"検索エラー: {e!s}", "success": False}


def _to_asset_dict(r: dict, default_type: str, description_max_chars: int) -> dict:
    # NOTE: OpenMetadata の owner フィールドは複数所有者対応のため
    # "owners" (配列) であり、旧来の単数形 "owner" ではない。
    owners = r.get("owners") or []
    asset = {
        "fqn": r.get("fullyQualifiedName", ""),
        "name": r.get("name", ""),
        # NOTE: 検索インデックスのヒットは "entityType"、ユーザーの owns フィールドの
        # ような軽量な EntityReference は "type" というキー名を使うため両対応する。
        "type": r.get("entityType") or r.get("type") or default_type,
        "description": (r.get("description", "") or "")[:description_max_chars],
        "tags": [t.get("tagFQN", "") for t in r.get("tags", [])],
        "owners": [o.get("displayName") or o.get("name", "") for o in owners],
    }
    # NOTE: owns フィールドのような軽量な EntityReference には updatedAt が
    # 存在しない。キー自体を空文字で残すとモデルがそれらしい日付を
    # 勝手に補完してしまう(実際に発生を確認: 全く無関係な2023年の日付を
    # 表示した)ため、値が無い場合はキーごと省略する。
    # また、値がある場合も Unix epoch ミリ秒の生数値のまま渡すとモデルが
    # 日付換算を誤ることが確認された(例: 実際は2026-07-06のデータを
    # 2023-11-08と表示した)ため、ここで確実な日付文字列に変換しておく。
    updated_at = r.get("updatedAt")
    if updated_at:
        try:
            asset["updatedAt"] = datetime.fromtimestamp(
                int(updated_at) / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError, OSError):
            pass
    # NOTE: モデルに [名前](url) 形式のリンクを組み立てさせよう(あるいは
    # 事前に組み立てたリンク文字列をそのまま転記させよう)としたが、何度
    # 試してもモデルがリンク記法を削除してプレーンテキストに戻してしまう
    # ことを確認した。そのためリンク化はフロントエンド側(markdown.tsx)で
    # FQN 列の値から機械的に行う方式に変更し、ここでは行わない。
    return asset


@tool
def get_recent_activity(limit: int = 10) -> dict:
    """
    最近更新されたデータ資産の一覧を取得します（更新日時の新しい順）。

    Args:
        limit: 最大取得件数 (1-100)
    """
    log.info("get_recent_activity", limit=limit)
    DESCRIPTION_MAX_CHARS = 150
    try:
        client = get_openmetadata_client()
        results = client.get_recent_activity(limit)
        assets = [_to_asset_dict(r, "all", DESCRIPTION_MAX_CHARS) for r in results]
        return {"assets": assets, "total": len(assets), "success": True}
    except Exception as e:
        log.error("get_recent_activity_failed", error=str(e))
        return {"error": f"取得エラー: {e!s}", "success": False}


@tool
def get_topic_sample_data(topic_fqn: str, limit: int = 5) -> dict:
    """
    Kafkaトピックのサンプルメッセージを取得します（OpenMetadataの
    トピック詳細ページの「Sample Data」タブと同じ情報）。
    「Order-inトピックのサンプルを表示して」のような依頼には、まず
    topic_fqn が不明な場合は search_data_assets で該当トピックを検索して
    FQN を特定してから、このツールを呼び出すこと。

    Args:
        topic_fqn: トピックの完全修飾名 (例: "external-shop-cluster-kafka-asite:9094.orders-in")
        limit: 取得するメッセージ数 (1-20)
    """
    log.info("get_topic_sample_data", topic_fqn=topic_fqn)
    try:
        client = get_openmetadata_client()
        messages = client.get_topic_sample_data(topic_fqn, limit)
        return {"fqn": topic_fqn, "messages": messages, "total": len(messages), "success": True}
    except Exception as e:
        log.error("get_topic_sample_data_failed", topic_fqn=topic_fqn, error=str(e))
        return {"error": f"サンプルデータ取得エラー: {e!s}", "success": False}


@tool
def get_my_data_assets(owner_name: str, limit: int = 10) -> dict:
    """
    指定したユーザー (オーナー) が所有するデータ資産の一覧を取得します。
    「マイデータ」「自分のデータ」を尋ねられた場合は、会話のユーザー名を
    owner_name に指定して呼び出すこと。

    Args:
        owner_name: オーナーのユーザー名 (例: "admin")
        limit: 最大取得件数 (1-100)
    """
    log.info("get_my_data_assets", owner_name=owner_name)
    DESCRIPTION_MAX_CHARS = 150
    try:
        client = get_openmetadata_client()
        results = client.get_owned_assets(owner_name, limit)
        assets = [_to_asset_dict(r, "all", DESCRIPTION_MAX_CHARS) for r in results]
        # NOTE: この一覧は複数の資産タイプ(table/topic/dataProduct等)が
        # 1つのリストに混在しているため、資産タイプ別の内訳件数を
        # 明示的に含める。モデルが応答のタイプ別見出し「(N件)」に、
        # 全体の total 値をそのまま使ってしまう誤りを防ぐため。
        counts_by_type: dict[str, int] = {}
        for a in assets:
            counts_by_type[a["type"]] = counts_by_type.get(a["type"], 0) + 1
        return {
            "assets": assets,
            "total": len(assets),
            "counts_by_type": counts_by_type,
            "owner": owner_name,
            "success": True,
        }
    except Exception as e:
        log.error("get_my_data_assets_failed", owner_name=owner_name, error=str(e))
        return {"error": f"取得エラー: {e!s}", "success": False}
