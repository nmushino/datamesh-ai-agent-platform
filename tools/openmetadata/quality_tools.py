from typing import Literal
import structlog
from langchain_core.tools import tool
from tools.common.client import get_openmetadata_client

log = structlog.get_logger()

QualityRuleType = Literal[
    "columnNotNull",
    "columnValuesToBeUnique",
    "columnValuesToBeBetween",
    "columnValuesToMatchRegex",
    "columnValuesToNotMatchRegex",
    "tableRowCountToBeBetween",
    "tableColumnCountToBeBetween",
]


@tool
def create_quality_rule(
    table_fqn: str,
    column_name: str,
    rule_type: QualityRuleType,
    params: dict,
) -> dict:
    """
    データ品質ルールを作成します。

    Args:
        table_fqn: テーブルの完全修飾名
        column_name: 対象カラム名（テーブルレベルのルールは空文字）
        rule_type: ルールタイプ
            - "columnNotNull": NULL 禁止
            - "columnValuesToBeUnique": ユニーク制約
            - "columnValuesToBeBetween": 範囲チェック (params: {"minValue": N, "maxValue": N})
            - "columnValuesToMatchRegex": 正規表現チェック (params: {"regex": "..."})
            - "tableRowCountToBeBetween": 行数チェック (params: {"minValue": N, "maxValue": N})
        params: ルールパラメータ (rule_type に応じて異なる)
    """
    log.info("create_quality_rule", table_fqn=table_fqn, column=column_name, rule=rule_type)
    try:
        client = get_openmetadata_client()
        rule_name = f"{table_fqn.replace('.', '_')}_{column_name}_{rule_type}" if column_name \
            else f"{table_fqn.replace('.', '_')}_{rule_type}"

        entity_link = (
            f"<#E::table::{table_fqn}::columns::{column_name}>"
            if column_name
            else f"<#E::table::{table_fqn}>"
        )

        test_case = {
            "name": rule_name,
            "entityLink": entity_link,
            "testDefinition": rule_type,
            "parameterValues": [
                {"name": k, "value": str(v)} for k, v in params.items()
            ],
        }
        result = client.create_test_case(test_case)
        return {"ruleName": rule_name, "created": True, "result": result, "success": True}
    except Exception as e:
        log.error("create_quality_rule_failed", error=str(e))
        return {"error": f"品質ルール作成エラー: {str(e)}", "success": False}


@tool
def get_quality_metrics(table_fqn: str) -> dict:
    """
    テーブルのデータ品質テストケース(OpenMetadataのData Quality画面と同じ情報)を
    取得します。テストがまだ一度も実行されていない場合、個々のルールの
    lastResult は "未実行" になる(これは異常ではない)。

    Args:
        table_fqn: テーブルの完全修飾名
    """
    log.info("get_quality_metrics", table_fqn=table_fqn)
    try:
        client = get_openmetadata_client()
        test_cases = client.get_quality_test_cases(table_fqn)
        if not test_cases:
            return {
                "fqn": table_fqn,
                "totalRules": 0,
                "rules": [],
                "success": True,
                "message": "このテーブルにはデータ品質テストが定義されていません。",
            }

        rules = []
        passed = failed = not_run = 0
        for tc in test_cases:
            result = tc.get("testCaseResult") or {}
            status = result.get("testCaseStatus", "未実行")
            if status == "Success":
                passed += 1
            elif status == "Failed":
                failed += 1
            else:
                not_run += 1
                status = "未実行"
            rules.append({
                "name": tc.get("name", ""),
                "testDefinition": (tc.get("testDefinition") or {}).get("name", ""),
                "lastResult": status,
            })

        return {
            "fqn": table_fqn,
            "totalRules": len(rules),
            "passedRules": passed,
            "failedRules": failed,
            "notRunRules": not_run,
            "rules": rules,
            "success": True,
        }
    except Exception as e:
        log.error("get_quality_metrics_failed", table_fqn=table_fqn, error=str(e))
        return {"error": str(e), "success": False}
