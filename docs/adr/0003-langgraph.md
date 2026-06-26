# ADR-0003: LangGraph をエージェントフレームワークとして採用

## ステータス

採用済み (2024-01-01)

## コンテキスト

AI エージェントのオーケストレーションに使用するフレームワークを選定する必要がある。
候補: LangGraph, CrewAI, AutoGen, 独自実装

## 決定

**LangGraph を採用する**

## 比較

| 項目 | LangGraph | CrewAI | AutoGen | 独自実装 |
|---|---|---|---|---|
| ステートフル会話 | ✅ | △ | △ | 要実装 |
| Human-in-the-Loop | ✅ ネイティブ | △ | △ | 要実装 |
| チェックポイント | ✅ PostgreSQL | ❌ | △ | 要実装 |
| グラフ定義 | ✅ 明示的 | ❌ ブラックボックス | △ | 要実装 |
| デバッグ性 | ✅ LangSmith 連携 | △ | △ | 要実装 |
| OpenAI API 互換 | ✅ | ✅ | ✅ | ✅ |

## 理由

1. **Human-in-the-Loop**: `interrupt()` による自然な承認フローが必須要件
2. **チェックポイント**: PostgreSQL に会話状態を保存し、再開が可能
3. **明示的なグラフ定義**: エージェントの制御フローが可視化・テスト可能
4. **プロダクション実績**: LangChain エコシステムで最も成熟している

## 結果

- エージェントは LangGraph の `StateGraph` または `create_react_agent` で実装
- チェックポイントは `PostgresSaver` を使用
- 会話 ID は `thread_id` で管理し、複数ユーザーの並行会話をサポート
- LangSmith でトレース・デバッグを実施（オプション）
