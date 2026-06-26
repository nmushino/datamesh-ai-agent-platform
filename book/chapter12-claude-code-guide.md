# Chapter 12: Claude Code Guide

## 概要

本プロジェクトは **Claude Code** を活用した AI 支援開発を前提として設計されています。本章では、Claude Code を使って効率的に開発するための指針を説明します。

---

## プロジェクト設定 (`.claude/`)

```
.claude/
├── project.md           ← プロジェクト概要・原則（Claude が常に参照）
├── architecture.md      ← アーキテクチャ詳細
├── principles.md        ← 設計原則チェックリスト
├── implementation-guide.md ← 実装パターン集
├── coding-rules.md      ← コーディングルール
├── tasks/               ← フェーズ別タスクリスト
│   ├── phase1.md
│   ├── phase2.md
│   └── phase3.md
└── prompts/             ← Claude への定型プロンプト
    ├── architect.md
    ├── developer.md
    ├── reviewer.md
    └── tester.md
```

### `CLAUDE.md` の設置

プロジェクトルートに `CLAUDE.md` を配置することで、Claude Code が自動的に読み込みます。

```markdown
<!-- CLAUDE.md (プロジェクトルート) -->

# Enterprise AI Agent Platform

## 最重要原則
1. Tool-First: 外部操作は必ず @tool で定義する
2. Metadata-First: OpenMetadata を Single Source of Truth とする
3. Quarkus API 経由: Business Tool は直接 DB にアクセスしない

## ディレクトリ
- `tools/openmetadata/` : OpenMetadata Tool 実装
- `tools/business/` : Business Tool 実装
- `agent/` : LangGraph エージェント
- `backend/business-api/` : Quarkus REST API

## 命名規則
- Tool 関数: snake_case, 動詞_名詞 (register_customer)
- Java クラス: PascalCase (CustomerResource)

## 禁止事項
- Business Tool から PostgreSQL への直接アクセス
- 破壊的 Tool に confirm=True なしでの実行
- Secret のハードコード
```

---

## Claude Code との効果的な協働パターン

### 1. Tool 実装の依頼

```
# 効果的なプロンプト例

「tools/business/ に在庫確認の Tool を追加してください。

Tool 名: check_inventory
引数: product_id (str), warehouse_id (str, 任意)
動作: Quarkus API の GET /api/v1/inventory/{product_id} を呼ぶ
戻り値: {"productId": str, "quantity": int, "warehouseId": str}
エラー時: {"error": str, "success": False} を返す

coding-rules.md の Tool 設計原則に従ってください。
テストも tests/integration/test_inventory_tools.py に作成してください。」
```

### 2. Agent 追加の依頼

```
「agent/inventory-agent/ に在庫管理エージェントを追加してください。

使用 Tool:
- check_inventory (tools/business/inventory_tools.py)
- search_data_assets (tools/openmetadata/schema_tools.py)

プロンプトは prompts/inventory/system.md に作成してください。
chapter11 の Agent 開発手順に従ってください。
Orchestrator の router.py への登録も忘れずに。」
```

### 3. Quarkus エンドポイント追加

```
「backend/business-api に在庫 API を追加してください。

エンドポイント:
  GET  /api/v1/inventory/{productId}
  PUT  /api/v1/inventory/{productId}/quantity

chapter08 の CustomerResource を参考に実装してください。
- Bean Validation を使う
- Keycloak 認証を必須にする
- Kafka に在庫変更イベントを発行する
- MetadataSyncService で OpenMetadata に統計を同期する」
```

### 4. コードレビューの依頼

```
「追加した tools/business/inventory_tools.py をレビューしてください。

確認ポイント:
- chapter02 の Tool-First 原則に従っているか
- 冪等性が保たれているか
- エラーハンドリングが適切か
- docstring が LLM に分かりやすいか
- テストが網羅的か」
```

---

## Claude Code プロンプト集

### `.claude/prompts/developer.md`

```markdown
# Developer プロンプト

このプロジェクトは Enterprise AI Agent Platform です。
実装する際は以下を必ず守ってください：

## Tool 実装チェックリスト
- [ ] @tool デコレータを付ける
- [ ] Args/Returns/Raises を docstring に記述する
- [ ] エラーは {"error": str, "success": False} 形式で返す
- [ ] 外部 API 呼び出しは httpx を使い timeout=10.0 を設定する
- [ ] 単体テストを作成する

## Agent 実装チェックリスト
- [ ] system prompt は prompts/ の外部ファイルから読む
- [ ] temperature=0 に設定する
- [ ] 担当ドメイン外の Tool は使わない

## Quarkus API 実装チェックリスト
- [ ] @RolesAllowed で認証を必須にする
- [ ] @Valid で入力バリデーションする
- [ ] Kafka にイベントを発行する
- [ ] MetadataSyncService で OpenMetadata に同期する
```

### `.claude/prompts/architect.md`

```markdown
# Architect プロンプト

アーキテクチャ決定を行う際は以下を参照してください：

## ADR 一覧
- ADR-0001: Tool-First → docs/adr/0001-tool-first.md
- ADR-0002: Metadata-First → docs/adr/0002-metadata-first.md
- ADR-0003: LangGraph → docs/adr/0003-langgraph.md

## 判断基準
1. この変更は既存の ADR と矛盾しないか？
2. Tool-First 原則を守っているか？
3. Business Tool は Quarkus API 経由か？（直接 DB アクセスでないか）
4. 新しい ADR が必要な場合は docs/adr/ に追加する

## 参照ドキュメント
- book/chapter02-ai-native-architecture-principles.md (9原則)
- book/chapter03-reference-architecture.md (全体図)
- docs/architecture/logical-architecture.md (詳細図)
```

### `.claude/prompts/tester.md`

```markdown
# Tester プロンプト

テストを作成する際の方針：

## Tool のテスト (tests/integration/)
- httpx.Client をモックして外部 API 呼び出しをテストする
- 正常系・異常系（404, 500, タイムアウト）を網羅する
- Tool を invoke() で呼び出す（直接呼び出しではなく）

## Agent のテスト (tests/workflow/)
- LangGraph の graph.invoke() でエンドツーエンドをテストする
- Tool をモックして決定論的なテストにする
- Human-in-the-Loop が正しく interrupt するかテストする

## Quarkus API のテスト
- @QuarkusTest + @TestHTTPEndpoint を使う
- @InjectMock でサービスをモックする
- Kafka メッセージが発行されているか確認する
```

---

## よくある Claude Code への依頼と期待する動作

| 依頼 | Claude が行う作業 |
|---|---|
| 「BOM 登録 Tool を追加して」 | `tools/business/bom_tools.py` 作成 + テスト作成 |
| 「Search Agent が lineage も返せるようにして」 | `agent/search-agent/agent.py` と `prompts/search/system.md` を更新 |
| 「Quarkus API に BOM エンドポイントを追加して」 | `BomResource.java` + `BomService.java` + `BomEntity.java` + テスト作成 |
| 「chapter07 の OpenMetadata 設定を OpenShift 4.15 向けに更新して」 | chapter07 と `deployment/openshift/openmetadata.yaml` を更新 |
| 「ADR を追加して: Kafka のシリアライザは Avro を使う」 | `docs/adr/0007-kafka-avro.md` を作成 |

---

## Claude Code の制限と注意事項

```
✅ Claude Code が得意なこと:
  - Tool / Agent / Quarkus API の実装
  - テストコードの生成
  - ドキュメントの更新
  - コードレビューと改善提案
  - ADR の作成

⚠️ 確認が必要なこと:
  - 本番 DB への直接操作
  - Secret / 認証情報の取り扱い
  - OpenShift への本番デプロイ

❌ Claude Code に依頼してはいけないこと:
  - 本番環境での `oc delete` / `oc scale 0`
  - Secret を含むコードのコミット
  - テストなしの本番 PR マージ
```
