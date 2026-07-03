import { useEffect, useRef, useState } from "react";
import type { Thread } from "../types";

interface Props {
  thread: Thread | null;
  sending: boolean;
  onSend: (message: string) => void;
}

export function ChatBody({ thread, sending, onSend }: Props) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thread?.messages.length]);

  const submit = () => {
    const trimmed = input.trim();
    if (!trimmed || sending) return;
    onSend(trimmed);
    setInput("");
  };

  return (
    <main className="chat-body">
      <div className="chat-messages">
        {!thread && (
          <div className="chat-placeholder">
            左側の「+ 新しい会話」から会話を始めてください
          </div>
        )}
        {thread?.messages.map((m) => (
          <div key={m.id} className={`chat-message chat-message-${m.role}`}>
            <div className="chat-message-bubble">{m.content}</div>
          </div>
        ))}
        {sending && (
          <div className="chat-message chat-message-assistant">
            <div className="chat-message-bubble chat-message-pending">
              考え中...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="chat-input-row">
        <textarea
          className="chat-input"
          value={input}
          placeholder="メッセージを入力..."
          rows={2}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button
          className="chat-send-button"
          onClick={submit}
          disabled={sending || !input.trim()}
        >
          送信
        </button>
      </div>
    </main>
  );
}
