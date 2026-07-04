import type { ScheduledTask } from "../types";

interface Props {
  tasks: ScheduledTask[];
}

const STATUS_LABEL: Record<ScheduledTask["status"], string> = {
  ok: "OK",
  changed: "変更あり",
  error: "エラー",
};

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" });
}

// Agentが定期的に実行するOpenMetadataのスキーマ・品質チェックの実行履歴を表示するエリア。
// クリックで開閉するのではなく、通知が無くても常にエリア自体は表示しておく。
export function ScheduledTasksArea({ tasks }: Props) {
  return (
    <div className="scheduled-tasks-area">
      <div className="scheduled-tasks-header">定期チェック実行履歴</div>
      {tasks.length === 0 ? (
        <div className="scheduled-tasks-empty">まだ実行履歴はありません</div>
      ) : (
        <ul className="scheduled-tasks-list">
          {tasks.slice(0, 5).map((t) => (
            <li key={t.id} className="scheduled-task-item">
              <span className={`scheduled-task-status scheduled-task-status-${t.status}`}>
                {STATUS_LABEL[t.status] ?? t.status}
              </span>
              <span className="scheduled-task-message">{t.message}</span>
              <span className="scheduled-task-time">{formatTime(t.timestamp)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
