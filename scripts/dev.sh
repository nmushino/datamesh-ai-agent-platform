#!/bin/bash
set -e

echo "=== Enterprise AI Agent Platform - Dev Environment ==="

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
