FROM python:3.11-slim AS builder

WORKDIR /app

# 依存パッケージをインストール（レイヤーキャッシュを最大化）
COPY mcp-server/requirements.txt mcp-server/requirements.txt
COPY tools/requirements.txt      tools/requirements.txt
# /root 配下は OpenShift の任意 UID 実行だと辿れないため /app 配下にインストールする
ENV PYTHONUSERBASE=/app/.local
RUN pip install --no-cache-dir --user \
    -r mcp-server/requirements.txt \
    -r tools/requirements.txt

# ===== Runtime stage =====
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /app/.local /app/.local
ENV PYTHONUSERBASE=/app/.local
ENV PATH=/app/.local/bin:$PATH
# server.py が `tools.openmetadata...` を絶対importするため、
# WORKDIR (/app) を import 探索パスに含める
ENV PYTHONPATH=/app

# アプリケーションコードをコピー
COPY mcp-server/ mcp-server/
COPY tools/      tools/

# 非 root ユーザーで実行（OpenShift SCC 対応）
RUN useradd -u 1001 -r -g 0 -m appuser && \
    chown -R 1001:0 /app && \
    chmod -R g=u /app

USER 1001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/healthz').raise_for_status()"

CMD ["python", "mcp-server/server.py"]
