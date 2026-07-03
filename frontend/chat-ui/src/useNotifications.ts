import { useEffect, useState } from "react";
import { fetchRecentNotifications, subscribeToNotifications } from "./api";
import type { Notification } from "./types";

export function useNotifications() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchRecentNotifications().then((items) => {
      if (!cancelled) setNotifications(items);
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

  return { notifications, unreadCount, markAllRead };
}
