export interface ChatResponse {
  thread_id: string;
  reply: string;
  intent: string;
  active_agent: string;
  requires_approval: boolean;
  approval_action: string;
  token_usage: number;
}

/**
 * /api/v1/chat は SSE (text/event-stream) で応答する。3秒以上かかる場合は
 * 途中経過として {"status": "..."} だけを含むイベントが挟まることがあり、
 * 最終結果には "reply" が含まれる。(frontend/chat-ui/src/api.ts と同じ実装)
 */
export async function sendChatMessage(
  baseUrl: string,
  message: string,
  threadId: string,
  onStatus?: (status: string) => void,
): Promise<ChatResponse> {
  const res = await fetch(`${baseUrl}/api/v1/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      thread_id: threadId,
      enable_thinking: false,
      max_tokens_level: 'low',
    }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`chat request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sepIndex: number;
    while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 2);
      const dataLine = rawEvent
        .split('\n')
        .find(line => line.startsWith('data:'));
      if (!dataLine) continue;
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
  throw new Error('chat request failed: empty stream');
}

export async function approveTask(
  baseUrl: string,
  threadId: string,
): Promise<{ thread_id: string; status: string; reply?: string }> {
  const res = await fetch(`${baseUrl}/api/v1/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thread_id: threadId, approved: true }),
  });
  if (!res.ok) {
    throw new Error(`approve request failed: ${res.status}`);
  }
  return res.json();
}
