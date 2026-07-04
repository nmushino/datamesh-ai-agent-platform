import { useCallback, useEffect, useState } from "react";
import type { ChatMessage, Thread } from "./types";

const STORAGE_KEY = "chat-ui.threads";

function loadThreads(): Thread[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Thread[]) : [];
  } catch {
    return [];
  }
}

function saveThreads(threads: Thread[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
}

export function useThreads() {
  const [threads, setThreads] = useState<Thread[]>(() => loadThreads());
  const [activeThreadId, setActiveThreadId] = useState<string | null>(
    () => loadThreads()[0]?.id ?? null
  );

  useEffect(() => {
    saveThreads(threads);
  }, [threads]);

  const createThread = useCallback((): string => {
    const now = Date.now();
    const thread: Thread = {
      id: crypto.randomUUID(),
      title: "新しい会話",
      messages: [],
      createdAt: now,
      updatedAt: now,
    };
    setThreads((prev) => [thread, ...prev]);
    setActiveThreadId(thread.id);
    return thread.id;
  }, []);

  const appendMessage = useCallback(
    (threadId: string, message: ChatMessage) => {
      setThreads((prev) =>
        prev.map((t) => {
          if (t.id !== threadId) return t;
          const title =
            t.messages.length === 0 && message.role === "user"
              ? message.content.slice(0, 24)
              : t.title;
          return {
            ...t,
            title,
            messages: [...t.messages, message],
            updatedAt: message.createdAt,
          };
        })
      );
    },
    []
  );

  const deleteThread = useCallback(
    (threadId: string) => {
      setThreads((prev) => prev.filter((t) => t.id !== threadId));
      setActiveThreadId((prev) => (prev === threadId ? null : prev));
    },
    []
  );

  const activeThread = threads.find((t) => t.id === activeThreadId) ?? null;

  return {
    threads,
    activeThread,
    activeThreadId,
    setActiveThreadId,
    createThread,
    appendMessage,
    deleteThread,
  };
}
