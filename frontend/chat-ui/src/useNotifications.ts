import { useEffect, useState } from "react";
import { fetchRecentNotifications, subscribeToNotifications } from "./api";
import type { Notification } from "./types";

export function useNotifications() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchRecentNotifications()
      .then((items) => {
        if (!cancelled) setNotifications(items);
      })
      .catch(() => {
        // バックエンド未接続時などは黙って無視する(通知が0件のまま)
      });

    const unsubscribe = subscribeToNotifications((n) => {
      setNotifications((prev) => [n, ...prev].slice(0, 50));
      setUnreadCount((c) => c + 1);
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  const markAllRead = () => setUnreadCount(0);

  // タスクボタン(承認要の長時間処理)完了時など、バックエンドの
  // Kafka経由通知を待たずにフロントエンドから直接ベルへ差し込むための入口
  const addLocalNotification = (n: Notification) => {
    setNotifications((prev) => [n, ...prev].slice(0, 50));
    setUnreadCount((c) => c + 1);
  };

  return { notifications, unreadCount, markAllRead, addLocalNotification };
}
