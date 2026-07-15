FROM python:3.11-slim AS builder

WORKDIR /app

# 依存パッケージをインストール（レイヤーキャッシュを最大化）
COPY agent/requirements.txt agent/requirements.txt
COPY tools/requirements.txt  tools/requirements.txt
# /root 配下は OpenShift の任意 UID 実行だと辿れないため /app 配下にインストールする
ENV PYTHONUSERBASE=/app/.local
RUN pip install --no-cache-dir --user \
    -r agent/requirements.txt \
    -r tools/requirements.txt

# ===== Runtime stage =====
FROM python:3.11-slim

WORKDIR /app

# Kafka Admin操作(トピック作成等)は、KRaftブローカーとのAPIVersionネゴシエーション
# 非互換が確認された Python クライアントライブラリを使わず、実績のある
# kafka-topics.sh (CLI) を subprocess 経由で呼び出す方式にしている
# (tools/kafka/admin_tools.py 参照)。そのため CLI 実行に必要な JRE と
# Kafka クライアント配布物をここで用意する。
ARG KAFKA_DIST_VERSION=4.1.0
ARG KAFKA_SCALA_VERSION=2.13
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-21-jre-headless curl && \
    curl -fsSL "https://archive.apache.org/dist/kafka/${KAFKA_DIST_VERSION}/kafka_${KAFKA_SCALA_VERSION}-${KAFKA_DIST_VERSION}.tgz" \
      -o /tmp/kafka.tgz && \
    mkdir -p /opt/kafka && \
    tar -xzf /tmp/kafka.tgz -C /opt/kafka --strip-components=1 && \
    rm /tmp/kafka.tgz && \
    apt-get purge -y curl && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/kafka/bin:$PATH

# ビルドステージの依存パッケージをコピー
COPY --from=builder /app/.local /app/.local
ENV PYTHONUSERBASE=/app/.local
ENV PATH=/app/.local/bin:$PATH

# アプリケーションコードをコピー
COPY agent/    agent/
COPY tools/    tools/
COPY prompts/  prompts/

# 非 root ユーザーで実行（OpenShift SCC 対応）
RUN useradd -u 1001 -r -g 0 -m appuser && \
    chown -R 1001:0 /app && \
    chmod -R g=u /app

USER 1001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

# Kafka通知ブリッジ/LangGraphチェックポイントの状態をプロセス内メモリで保持しているため
# 複数ワーカーだとワーカーごとに状態が分裂してしまう。単一ワーカーで動かす
CMD ["uvicorn", "agent.orchestrator.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info"]
