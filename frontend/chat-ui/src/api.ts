import type {
  ChatResponse,
  ChatSettings,
  Notification,
  ScheduledTask,
  ScheduledTaskSettings,
} from "./types";

function apiBaseUrl(): string {
  return window.__APP_CONFIG__?.apiBaseUrl ?? "";
}

export async function sendChatMessage(
  message: string,
  threadId: string,
  accessToken?: string,
  onStatus?: (status: string) => void,
  settings?: ChatSettings
): Promise<ChatResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }
  const res = await fetch(`${apiBaseUrl()}/api/v1/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      message,
      thread_id: threadId,
      enable_thinking: settings?.enableThinking ?? false,
      max_tokens_level: settings?.maxTokensLevel ?? "low",
    }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`chat request failed: ${res.status}`);
  }

  // 推論に時間がかかっても手前のロードバランサのアイドルタイムアウトで
  // 切断されないよう、サーバーはSSE(text/event-stream)でkeep-aliveを
  // 送りながら最終結果を "data: {...}" として返す。3秒以上かかる場合は
  // 途中経過として {"status": "..."} だけを含むイベントが挟まることがある
  // (最終結果には "reply" が含まれる)
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sepIndex: number;
    while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 2);
      const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data:"));
      if (!dataLine) continue; // keep-aliveコメント行は無視
      const payload = JSON.parse(dataLine.slice(5).trim());
      if (payload.error) {
        throw new Error(payload.error);
      }
      if (payload.status && !payload.reply) {
        onStatus?.(payload.status);
        continue;
      }
      return payload as ChatResponse;
    }
  }
  throw new Error("chat request failed: empty stream");
}

export async function approveTask(
  threadId: string,
  accessToken?: string
): Promise<{ thread_id: string; status: string; reply?: string }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }
  const res = await fetch(`${apiBaseUrl()}/api/v1/approve`, {
    method: "POST",
    headers,
    body: JSON.stringify({ thread_id: threadId, approved: true }),
  });
  if (!res.ok) {
    throw new Error(`approve request failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchRecentNotifications(): Promise<Notification[]> {
  const res = await fetch(`${apiBaseUrl()}/api/v1/notifications/recent`);
  if (!res.ok) {
    return [];
  }
  const data = await res.json();
  return data.notifications ?? [];
}

export function subscribeToNotifications(
  onNotification: (n: Notification) => void
): () => void {
  const source = new EventSource(
    `${apiBaseUrl()}/api/v1/notifications/stream`
  );
  source.onmessage = (event) => {
    try {
      onNotification(JSON.parse(event.data));
    } catch {
      // 不正なペイロードは無視する
    }
  };
  return () => source.close();
}

export async function fetchRecentScheduledTasks(): Promise<ScheduledTask[]> {
  const res = await fetch(`${apiBaseUrl()}/api/v1/scheduled-tasks/recent`);
  if (!res.ok) {
    return [];
  }
  const data = await res.json();
  return data.tasks ?? [];
}

export function subscribeToScheduledTasks(
  onTask: (t: ScheduledTask) => void
): () => void {
  const source = new EventSource(
    `${apiBaseUrl()}/api/v1/scheduled-tasks/stream`
  );
  source.onmessage = (event) => {
    try {
      onTask(JSON.parse(event.data));
    } catch {
      // 不正なペイロードは無視する
    }
  };
  return () => source.close();
}

export async function fetchScheduledTaskSettings(): Promise<ScheduledTaskSettings | null> {
  const res = await fetch(`${apiBaseUrl()}/api/v1/settings/scheduled-task`);
  if (!res.ok) {
    return null;
  }
  return res.json();
}

export async function updateScheduledTaskSettings(
  patch: Partial<ScheduledTaskSettings>
): Promise<ScheduledTaskSettings> {
  const res = await fetch(`${apiBaseUrl()}/api/v1/settings/scheduled-task`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    throw new Error(`settings update failed: ${res.status}`);
  }
  return res.json();
}
