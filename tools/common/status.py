"""チャットUIの「実行中...」表示用ステータスキューを保持する contextvar。

agent/orchestrator/graph.py (ツール呼び出しループ側) と tools/* (個々のツール
実装側、複数ステップの処理の途中経過を細かく通知したい場合) の両方から使う
ため、循環importを避けられる下位モジュールに置く。

PostgresSaver チェックポインタ付きでコンパイルしたグラフでは configurable が
チェックポインタの識別キー以外を除去してしまい、ノード関数まで届かないため、
contextvars を使う(スレッド内の呼び出しスタックには伝播するため、
チェックポインタの介在を受けない)。
"""
import contextvars

status_queue_var: contextvars.ContextVar = contextvars.ContextVar(
    "status_queue", default=None
)


def push_status(message: str) -> None:
    """現在のスレッドに紐づく status queue があれば通知する。無ければ何もしない
    (ツール単体でのユニットテスト実行時など、キューが無い状況でも動くように)。"""
    queue = status_queue_var.get()
    if queue:
        queue.put(message)
