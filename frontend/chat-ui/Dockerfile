# ===== Build stage =====
FROM node:20-slim AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# ===== Runtime stage =====
# 非rootで8080を待受するイメージを使い OpenShift の任意UID実行に対応する
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
# config.js だけは /usr/share/nginx/html (root所有・読み取り専用) の外、
# /tmp (常に書き込み可能) に置いて起動時に差し替えられるようにする
# (OpenShiftのビルド・実行はいずれも任意UIDで行われ、chgrp/chmodで
#  読み取り専用ツリーを書き込み可能にすることはできないため)
COPY docker/default.conf /etc/nginx/conf.d/default.conf
COPY docker/40-inject-config.sh /docker-entrypoint.d/40-inject-config.sh
USER 101
EXPOSE 8080
