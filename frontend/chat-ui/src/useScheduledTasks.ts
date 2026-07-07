import { useEffect, useState } from "react";
import { fetchRecentScheduledTasks, subscribeToScheduledTasks } from "./api";
import type { ScheduledTask } from "./types";

// Pod再起動のたびに定期チェックのベースライン記録("初回チェック: ...")が
// 再度発生し、同一内容のエントリが連続で並んでしまう(見た目の時刻表示は
// 同じ秒に見えても実際には別タイミングのことがある)。内容が同じ連続エントリは
// 履歴上まとめて1件だけ表示する。
function isSameCheck(a: ScheduledTask, b: ScheduledTask): boolean {
  return a.task_name === b.task_name && a.fqn === b.fqn && a.status === b.status && a.message === b.message;
}

function dedupeConsecutive(items: ScheduledTask[]): ScheduledTask[] {
  const result: ScheduledTask[] = [];
  for (const item of items) {
    if (result.length > 0 && isSameCheck(result[result.length - 1], item)) continue;
    result.push(item);
  }
  return result;
}

export function useScheduledTasks() {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetchRecentScheduledTasks()
      .then((items) => {
        if (!cancelled) setTasks(dedupeConsecutive(items));
      })
      .catch(() => {
        // バックエンド未接続時などは黙って無視する(空のまま)
      });

    const unsubscribe = subscribeToScheduledTasks((t) => {
      setTasks((prev) => {
        if (prev.length > 0 && isSameCheck(prev[0], t)) return prev;
        return [t, ...prev].slice(0, 50);
      });
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  const deleteTask = (id: string) => {
    setTasks((prev) => prev.filter((t) => t.id !== id));
  };

  return { tasks, deleteTask };
}
