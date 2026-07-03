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

CMD ["uvicorn", "agent.orchestrator.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]
