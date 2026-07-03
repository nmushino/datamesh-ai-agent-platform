import type { Thread } from "../types";

interface Props {
  threads: Thread[];
  activeThreadId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
}

export function Sidebar({
  threads,
  activeThreadId,
  onSelect,
  onCreate,
  onDelete,
}: Props) {
  return (
    <aside className="sidebar">
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
            <span className="thread-item-title">{t.title || "新しい会話"}</span>
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
    </aside>
  );
}
