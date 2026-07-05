import { useState } from "react";
import { useAppAuth } from "../useAppAuth";
import { Logo } from "./Logo";
import { OpenMetadataIcon } from "./OpenMetadataIcon";
import { DatameshHubIcon } from "./DatameshHubIcon";
import { NotificationPanel } from "./NotificationPanel";
import type { Notification } from "../types";

interface Props {
  onToggleSidebar: () => void;
  notifications: Notification[];
  unreadCount: number;
  markAllRead: () => void;
}

export function Header({
  onToggleSidebar,
  notifications,
  unreadCount,
  markAllRead,
}: Props) {
  const [open, setOpen] = useState(false);
  const auth = useAppAuth();
  const config = window.__APP_CONFIG__;

  const toggle = () => {
    setOpen((v) => !v);
    if (!open) markAllRead();
  };

  const username =
    (auth.user?.profile?.preferred_username as string | undefined) ??
    (auth.user?.profile?.name as string | undefined) ??
    "";

  return (
    <header className="app-header">
      <div className="app-header-brand">
        <button
          className="sidebar-toggle-button"
          onClick={onToggleSidebar}
          aria-label="メニューの表示/非表示"
          title="メニューの表示/非表示"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path
              d="M3 6h18M3 12h18M3 18h18"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
        </button>
        <Logo size={36} />
        <span className="app-header-title">Data Integration Modernization</span>
      </div>
      <div className="app-header-actions">
        {config.openMetadataUrl && (
          <a
            className="header-icon-link"
            href={config.openMetadataUrl}
            target="_blank"
            rel="noreferrer"
            title="OpenMetadata"
            aria-label="OpenMetadata"
          >
            <OpenMetadataIcon size={22} />
          </a>
        )}
        {config.developerHubUrl && (
          <a
            className="header-icon-link"
            href={config.developerHubUrl}
            target="_blank"
            rel="noreferrer"
            title="Datamesh Hub"
            aria-label="Datamesh Hub"
          >
            <DatameshHubIcon size={20} />
          </a>
        )}
        <span className="header-divider" aria-hidden="true" />
        <button
          className="notification-bell"
          onClick={toggle}
          aria-label="通知"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 3a5 5 0 0 0-5 5v3.2c0 .5-.2 1-.5 1.4L5 14.5c-.7.9-.1 2.5 1 2.5h12c1.1 0 1.7-1.6 1-2.5l-1.5-2c-.3-.4-.5-.9-.5-1.4V8a5 5 0 0 0-5-5Z"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
            <path
              d="M9.5 19a2.5 2.5 0 0 0 5 0"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          </svg>
          {unreadCount > 0 && (
            <span className="notification-badge">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </button>
        {open && (
          <NotificationPanel
            notifications={notifications}
            onClose={() => setOpen(false)}
          />
        )}
        {username && (
          <div className="header-user">
            <span className="header-user-name">{username}</span>
            <button
              className="link-button"
              onClick={() => auth.signoutRedirect()}
            >
              ログアウト
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
