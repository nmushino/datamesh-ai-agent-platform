# ADR-0004: Quarkus を Business API フレームワークとして採用

## ステータス

採用済み (2024-01-01)

## コンテキスト

Business Tool が呼び出す REST API のフレームワークを選定する。
候補: Quarkus, Spring Boot, FastAPI (Python), Node.js (Express)

## 決定

**Quarkus (Java) を採用する**

## 比較

| 項目 | Quarkus | Spring Boot | FastAPI |
|---|---|---|---|
| 起動時間 | < 1秒 (JVM) / < 0.1秒 (Native) | 5-15秒 | < 1秒 |
| メモリ使用量 | 低 (Native) | 高 | 低 |
| OpenShift 統合 | ✅ ネイティブ対応 | △ | △ |
| Kubernetes 生成 | ✅ 自動 | △ | ❌ |
| エンタープライズ実績 | ✅ | ✅ | △ |
| Kafka 統合 | ✅ SmallRye Reactive Messaging | ✅ Spring Kafka | △ |
| OpenAPI 生成 | ✅ SmallRye OpenAPI | ✅ SpringDoc | ✅ |

## 理由

1. **OpenShift ネイティブ**: `quarkus-openshift` 拡張で Deployment/Service を自動生成
2. **Kafka 統合**: SmallRye Reactive Messaging で宣言的な Kafka 接続
3. **Native コンパイル**: GraalVM Native Image でコールドスタート問題を解消
4. **Java エンタープライズ標準**: JAX-RS, CDI, JPA, Bean Validation をサポート
5. **Red Hat サポート**: エンタープライズサポートが受けられる

## 結果

- Business API はすべて Quarkus で実装する
- Python Agent から Quarkus API を REST で呼び出す
- `quarkus.kubernetes.deployment-target=openshift` で OpenShift マニフェストを自動生成する
- 本番環境では Native ビルドを使用する
