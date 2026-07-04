# Book: Datamesh AI Agent Platform 設計ドキュメント

本ディレクトリは、プラットフォームの設計思想から実装詳細まで体系的に記述したドキュメント集です。

## 章一覧

| 章 | タイトル | 概要 |
|---|---|---|
| [Chapter 0](chapter00-executive-summary.md) | Executive Summary | ビジネス価値・フェーズ計画 |
| [Chapter 1](chapter01-vision.md) | Vision | ビジョン・Before/After・KPI |
| [Chapter 2](chapter02-ai-native-architecture-principles.md) | AI-Native Architecture Principles | 9つの設計原則 |
| [Chapter 3](chapter03-reference-architecture.md) | Reference Architecture | 全体アーキテクチャ図・データフロー |
| [Chapter 4](chapter04-platform-architecture.md) | Platform Architecture | OpenShift AI 構成・観測性・スケーリング |
| [Chapter 5](chapter05-ai-agent-framework.md) | AI Agent Framework | LangGraph 実装・Human-in-the-Loop |
| [Chapter 6](chapter06-tool-framework.md) | Tool Framework | Tool 設計原則・OpenMetadata/Business Tool 群 |
| [Chapter 7](chapter07-openmetadata.md) | OpenMetadata | メタデータ統合・Python クライアント |
| [Chapter 8](chapter08-business-services.md) | Business Services | Quarkus API 設計・Kafka イベント |
| [Chapter 9](chapter09-openshift.md) | OpenShift | vLLM/Granite デプロイ・NetworkPolicy |
| [Chapter 10](chapter10-deployment.md) | Deployment | GitOps・ArgoCD・Tekton パイプライン |
| [Chapter 11](chapter11-developer-guide.md) | Developer Guide | 開発環境・Tool/Agent/API の追加手順 |
| [Chapter 12](chapter12-claude-code-guide.md) | Claude Code Guide | Claude Code との協働パターン |

## 付録

| 付録 | 内容 |
|---|---|
| [Coding Rules](appendix/coding-rules.md) | Python/Java/Kafka の詳細コーディングルール |
| [Glossary](appendix/glossary.md) | 用語集 |
| [ADR Index](appendix/adr-index.md) | アーキテクチャ決定記録一覧 |
| [Roadmap](appendix/roadmap.md) | フェーズ計画・バックログ |

## アーキテクチャの一言サマリー

```
OpenShift AI (Granite/Llama) → AI Agent (LangGraph)
  ├── OpenMetadata Tool → OpenMetadata REST API → OpenMetadata
  └── Business Tool     → Quarkus REST API      → PostgreSQL / Kafka / 他システム
```
