#!/bin/bash
set -e
# =============================================================================
# Script Name: dev.sh
# Description: Datamesh AI Agent Platform のローカル開発環境を起動する
#              (docker compose で PostgreSQL/Kafka/OpenMetadata を起動し、
#               Quarkus Business API と AI Agent をdevモードで起動する)
# Author: Datamesh AI Agent Platform Team
# Date Created: 2026-06-26
# Last Modified: 2026-07-04
# Version: 1.0
#
# Usage:
#   ./scripts/dev.sh
#
#   終了するには起動後に Ctrl+C を押す
#
# Prerequisites:
#   - Docker (docker compose) が導入・起動済みであること
#   - Python3 が導入済みであること (AI Agentの起動に使用)
#   - Maven (mvn) が導入済みであること (Business APIの起動に使用)
#   - リポジトリルートに .env ファイルがあれば自動で読み込む
#
# =============================================================================
echo "=== Datamesh AI Agent Platform - Dev Environment ==="

# 依存チェック
command -v docker &>/dev/null || { echo "docker が必要です"; exit 1; }
command -v python3 &>/dev/null || { echo "python3 が必要です"; exit 1; }
command -v mvn &>/dev/null || { echo "maven が必要です"; exit 1; }

# .env 読み込み
if [ -f .env ]; then
  export $(cat .env | grep -v '^#' | xargs)
fi

# インフラ起動
echo "インフラサービスを起動中..."
docker compose -f deployment/docker-compose.dev.yaml up -d postgresql kafka openmetadata

# 起動待ち
echo "PostgreSQL 起動待ち..."
until docker exec dev-postgresql pg_isready -U postgres; do sleep 2; done

echo "Kafka 起動待ち..."
until docker exec dev-kafka kafka-topics.sh --list --bootstrap-server localhost:9092 &>/dev/null; do sleep 2; done

echo "OpenMetadata 起動待ち..."
until curl -s http://localhost:8585/api/v1/system/status | grep -q '"status":"healthy"'; do sleep 5; done

# Quarkus API 起動 (dev mode)
echo "Quarkus Business API 起動中..."
cd backend/business-api
mvn quarkus:dev -Dquarkus.profile=dev &
cd ../..

# AI Agent 起動
echo "AI Agent 起動中..."
cd agent/orchestrator
pip install -r requirements.txt -q
uvicorn main:app --reload --port 8000 &
cd ../..

echo ""
echo "=== 起動完了 ==="
echo "  OpenMetadata:    http://localhost:8585  (admin/admin)"
echo "  Business API:    http://localhost:8080/q/swagger-ui"
echo "  AI Agent:        http://localhost:8000/docs"
echo ""
echo "終了するには Ctrl+C を押してください"
wait
