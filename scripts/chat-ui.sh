#!/bin/bash
set -e
# =============================================================================
# Script Name: chat-ui.sh
# Description: chat-ui (フロントエンド) をローカルで起動する
#              (画面の開発に専念できるよう、Keycloak/バックエンドへの認証は
#               自動でバイパスする。VITE_SKIP_AUTH=true を .env.local に設定)
# Author: Datamesh AI Agent Platform Team
# Date Created: 2026-07-04
# Last Modified: 2026-07-04
# Version: 1.0
#
# Usage:
#   ./scripts/chat-ui.sh
#
#   終了するには起動後に Ctrl+C を押す
#
# Prerequisites:
#   - Node.js / npm が導入済みであること
#
# =============================================================================
echo "=== Datamesh AI Agent Platform - chat-ui Dev Server ==="

# 依存チェック
command -v npm &>/dev/null || { echo "npm が必要です"; exit 1; }

CHAT_UI_DIR="../frontend/chat-ui"
if [ ! -d "$CHAT_UI_DIR" ]; then
  echo "エラー: $CHAT_UI_DIR が見つかりません。リポジトリルートから実行してください。"
  exit 1
fi

cd "$CHAT_UI_DIR"

# 初回のみ依存インストール
if [ ! -d node_modules ]; then
  echo "依存パッケージをインストール中..."
  npm install
fi

# 画面開発だけを行うため、Keycloak認証をバイパスする設定を用意する
# (既存の .env.local があれば尊重し、上書きしない)
if [ ! -f .env.local ]; then
  echo "VITE_SKIP_AUTH=true" > .env.local
  echo ".env.local を作成しました (VITE_SKIP_AUTH=true)"
fi

echo ""
echo "=== 起動中 ==="
echo "  chat-ui: http://localhost:5173  (Keycloak認証はスキップされます)"
echo ""
echo "終了するには Ctrl+C を押してください"
npm run dev
