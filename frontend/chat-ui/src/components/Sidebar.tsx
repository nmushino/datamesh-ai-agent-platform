import { useCallback, useRef } from "react";
import type { ScheduledTask, Thread } from "../types";
import { ScheduledTasksArea } from "./ScheduledTasksArea";

interface Props {
  threads: Thread[];
  activeThreadId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  open: boolean;
  width: number;
  onResizeWidth: (width: number) => void;
  scheduledTasks: ScheduledTask[];
}

const MIN_WIDTH = 180;
const MAX_WIDTH = 440;

function formatUpdatedAt(timestamp: number): string {
  const date = new Date(timestamp);
  const datePart = date.toLocaleDateString("ja-JP", {
    month: "short",
    day: "numeric",
  });
  const timePart = date.toLocaleTimeString("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${datePart} ${timePart}`;
}

function totalTokens(thread: Thread): number {
  return thread.messages.reduce((sum, m) => sum + (m.tokenUsage ?? 0), 0);
}

export function Sidebar({
  threads,
  activeThreadId,
  onSelect,
  onCreate,
  onDelete,
  open,
  width,
  onResizeWidth,
  scheduledTasks,
}: Props) {
  const draggingRef = useRef(false);

  const startResize = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      draggingRef.current = true;
      const startX = e.clientX;
      const startWidth = width;

      const onMouseMove = (moveEvent: MouseEvent) => {
        if (!draggingRef.current) return;
        const next = startWidth + (moveEvent.clientX - startX);
        onResizeWidth(Math.min(Math.max(next, MIN_WIDTH), MAX_WIDTH));
      };
      const onMouseUp = () => {
        draggingRef.current = false;
        window.removeEventListener("mousemove", onMouseMove);
        window.removeEventListener("mouseup", onMouseUp);
      };

      window.addEventListener("mousemove", onMouseMove);
      window.addEventListener("mouseup", onMouseUp);
    },
    [width, onResizeWidth]
  );

  return (
    <aside
      className={`sidebar ${open ? "" : "sidebar-collapsed"}`}
      style={{ width: open ? width : 0 }}
    >
      <div className="sidebar-inner" style={{ width }}>
        <ScheduledTasksArea tasks={scheduledTasks} />
        <button className="new-thread-button" onClick={onCreate}>
          + 新しい会話
        </button>
        <ul className="thread-list">
          {threads.map((t) => (
            <li
              key={t.id}
              className={`thread-item ${
                t.id === activeThreadId ? "thread-item-active" : ""
              }`}
              onClick={() => onSelect(t.id)}
            >
              <div className="thread-item-main">
                <span className="thread-item-title">{t.title || "新しい会話"}</span>
                <span className="thread-item-updated">
                  <span>{formatUpdatedAt(t.updatedAt ?? t.createdAt)}</span>
                  {totalTokens(t) > 0 && (
                    <span>{totalTokens(t).toLocaleString()} tokens</span>
                  )}
                </span>
              </div>
              <button
                className="thread-item-delete"
                aria-label="削除"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(t.id);
                }}
              >
                ×
              </button>
            </li>
          ))}
          {threads.length === 0 && (
            <li className="thread-empty">会話履歴はまだありません</li>
          )}
        </ul>
      </div>
      {open && (
        <div
          className="sidebar-resize-handle"
          onMouseDown={startResize}
          role="separator"
          aria-orientation="vertical"
          aria-label="メニュー幅の調整"
        />
      )}
    </aside>
  );
}
