import type { Notification } from "../types";

interface Props {
  notifications: Notification[];
  onClose: () => void;
}

export function NotificationPanel({ notifications, onClose }: Props) {
  return (
    <div className="notification-panel">
      <div className="notification-panel-header">
        <span>通知</span>
        <button className="link-button" onClick={onClose}>
          閉じる
        </button>
      </div>
      {notifications.length === 0 ? (
        <div className="notification-empty">通知はありません</div>
      ) : (
        <ul className="notification-list">
          {notifications.map((n, idx) => {
            const statusLower = (n.status ?? "info").toLowerCase();
            const isError = statusLower === "error" || statusLower === "failed";
            return (
              <li key={idx} className="notification-item">
                <div className="notification-item-top">
                  <span className={`notification-status notification-status-${statusLower}`}>
                    {n.status ?? "INFO"}
                  </span>
                  {n.pipeline && (
                    <span className="notification-pipeline">{n.pipeline}</span>
                  )}
                </div>
                <div
                  className={`notification-message${isError ? " notification-message-error" : ""}`}
                >
                  {n.message}
                </div>
                {n.timestamp && (
                  <div className="notification-timestamp">{n.timestamp}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
