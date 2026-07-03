import type { ChatResponse, Notification } from "./types";

function apiBaseUrl(): string {
  return window.__APP_CONFIG__?.apiBaseUrl ?? "";
}

export async function sendChatMessage(
  message: string,
  threadId: string,
  accessToken?: string
): Promise<ChatResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }
  const res = await fetch(`${apiBaseUrl()}/api/v1/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message, thread_id: threadId }),
  });
  if (!res.ok) {
    throw new Error(`chat request failed: ${res.status}`);
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
