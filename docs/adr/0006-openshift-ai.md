# ADR-0006: OpenShift AI (RHOAI) を LLM 基盤として採用

## ステータス

採用済み (2024-01-01)

## コンテキスト

AI エージェントが使用する LLM の実行環境を選定する。
候補: OpenShift AI (vLLM), OpenAI API (外部), Azure OpenAI, AWS Bedrock, Ollama

## 決定

**OpenShift AI (RHOAI) + vLLM を採用する**

モデル: IBM Granite 20B Code Instruct (コード・スキーマ分析), Meta Llama 3 8B Instruct (汎用会話)

## 比較

| 項目 | RHOAI + vLLM | OpenAI API | Azure OpenAI | Ollama |
|---|---|---|---|---|
| データセキュリティ | ✅ オンプレ | ❌ 外部送信 | △ Azure 上 | ✅ ローカル |
| コスト | GPU 固定費 | トークン課金 | トークン課金 | 無料 |
| エンタープライズサポート | ✅ Red Hat | ✅ OpenAI | ✅ Microsoft | ❌ |
| カスタムモデル | ✅ | ❌ | △ | ✅ |
| スケーラビリティ | ✅ | ✅ | ✅ | △ |
| OpenAI API 互換 | ✅ vLLM | ✅ (本家) | ✅ | ✅ |
| 日本語対応 | ✅ Granite | ✅ GPT-4 | ✅ GPT-4 | △ |

## 理由

1. **データセキュリティ**: 機密性の高いビジネスデータを外部 LLM API に送信しない
2. **コスト予測可能性**: トークン課金でなく GPU 固定費で予算管理が容易
3. **OpenAI API 互換**: vLLM の互換 API により LangChain コードを変更なく使用可能
4. **モデル柔軟性**: Granite / Llama など複数モデルを切り替えて使用可能
5. **Red Hat サポート**: OpenShift AI に対するエンタープライズサポート

## 結果

- LLM は `ChatOpenAI(base_url=VLLM_BASE_URL, ...)` で呼び出す（OpenAI API 互換）
- モデルは環境変数 `VLLM_MODEL` で指定し、コードに直接書かない
- GPU ノードは NVIDIA A100 (1枚/推論サービス) を使用
- 開発環境では Ollama で代替可能（API 互換のため）

## リスクと軽減策

| リスク | 軽減策 |
|---|---|
| GPU ノード障害 | vLLM を複数 GPU ノードに分散 (将来) |
| モデル精度不足 | Granite 34B への移行パスを確保 |
| GPU コスト超過 | リクエストレート制限 + モニタリング |
