import { useEffect, useState } from "react";
import { fetchRecentScheduledTasks, subscribeToScheduledTasks } from "./api";
import type { ScheduledTask } from "./types";

export function useScheduledTasks() {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetchRecentScheduledTasks()
      .then((items) => {
        if (!cancelled) setTasks(items);
      })
      .catch(() => {
        // バックエンド未接続時などは黙って無視する(空のまま)
      });

    const unsubscribe = subscribeToScheduledTasks((t) => {
      setTasks((prev) => [t, ...prev].slice(0, 50));
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  return { tasks };
}
