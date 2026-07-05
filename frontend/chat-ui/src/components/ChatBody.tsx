import { useEffect, useRef, useState } from "react";
import type { Thread } from "../types";
import { NetworkBackground } from "./NetworkBackground";
import { PendingIndicator } from "./PendingIndicator";
import { AssistantBubble } from "./AssistantBubble";

interface Props {
  thread: Thread | null;
  sending: boolean;
  statusText?: string | null;
  showQuickActions?: boolean;
  onSend: (message: string) => void;
}

const TEXTAREA_MIN_HEIGHT = 44; // .chat-input の min-height と一致させる (送信ボタンとの縦位置ズレ防止)
const TEXTAREA_COLLAPSED_MAX_HEIGHT = 160;
// line-height 1.4 * font-size 14px * 15行 + 上下padding(10px*2)
const TEXTAREA_EXPANDED_MAX_HEIGHT = 15 * 14 * 1.4 + 20;

const QUICK_ACTIONS = [
  "現在ある、データ資産一覧",
  "データプロダクト一覧",
  "最近のアクティビティ",
  "マイデータの一覧",
  "データ品質",
];

export function ChatBody({ thread, sending, statusText, showQuickActions, onSend }: Props) {
  const [input, setInput] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [needsExpand, setNeedsExpand] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // Enterキーを3回連続で押すと送信する(Shift+Enterや他のキー入力を挟むとリセット)
  const enterStreakRef = useRef(0);

  // スレッド切り替え時に既存メッセージのidを全て「既読」として登録し、
  // 履歴表示ではタイプライター演出を再生しない(新規に届いた回答だけ再生する)
  const seenIdsRef = useRef<Set<string>>(new Set());
  const prevThreadIdRef = useRef<string | undefined>(undefined);
  if (thread?.id !== prevThreadIdRef.current) {
    prevThreadIdRef.current = thread?.id;
    seenIdsRef.current = new Set(thread?.messages.map((m) => m.id) ?? []);
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thread?.messages.length]);

  // 入力された文字数(行数)に応じて送信エリアの高さを自動で広げる
  // (展開時は最大15行分、折りたたみ時は従来通りの高さまで)
  // "auto"へのリセットだと前の高さの影響が残り縮小されないことがあるため、
  // 一度"0px"まで完全に潰してから必要な高さを測り直す。
  // 「展開ボタンが必要か」もこの実測値をもとにstateへ反映する
  // (レンダー時にrefから直接読むと、直前の描画時点の高さを参照してしまい
  //  ちょうど15行を超えた瞬間に反映されない1テンポ遅れが起きるため)
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "0px";
    const contentHeight = el.scrollHeight;
    setNeedsExpand(contentHeight > TEXTAREA_COLLAPSED_MAX_HEIGHT);
    const maxHeight = expanded
      ? TEXTAREA_EXPANDED_MAX_HEIGHT
      : TEXTAREA_COLLAPSED_MAX_HEIGHT;
    el.style.height = `${Math.max(Math.min(contentHeight, maxHeight), TEXTAREA_MIN_HEIGHT)}px`;
  }, [input, expanded]);

  // 折りたたみ最大高を超える入力があるときだけ展開/折りたたみボタンを表示する
  const canExpand = needsExpand || expanded;

  const submit = () => {
    const trimmed = input.trim();
    if (!trimmed || sending) return;
    onSend(trimmed);
    setInput("");
  };

  // Enterキーを3回連続で押すと送信する。Shift+Enterや他キーを挟むと
  // 通常通り改行として扱われ、連続回数はリセットされる
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Enter" || e.shiftKey) {
      enterStreakRef.current = 0;
      return;
    }
    enterStreakRef.current += 1;
    if (enterStreakRef.current >= 3) {
      e.preventDefault();
      enterStreakRef.current = 0;
      submit();
    }
  };

  return (
    <main className="chat-body">
      <NetworkBackground />
      <div className="chat-body-overlay" aria-hidden="true" />
      <div className="chat-messages">
        {(!thread || thread.messages.length === 0) && (
          <div className="chat-placeholder">
            {showQuickActions ? (
              <>
                <div>下記のメニューから始めてください</div>
                <div className="chat-quick-actions">
                  {QUICK_ACTIONS.map((action) => (
                    <button
                      key={action}
                      type="button"
                      className="chat-quick-action"
                      onClick={() => onSend(action)}
                    >
                      {action}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <div>左側の「+ 新しい会話」から会話を始めてください</div>
            )}
          </div>
        )}
        {thread?.messages.map((m, idx) => (
          <div key={m.id} className={`chat-message chat-message-${m.role}`}>
            {m.role === "assistant" ? (
              <AssistantBubble
                message={m}
                animate={!seenIdsRef.current.has(m.id)}
                onRegenerate={() => {
                  const precedingUser = thread.messages
                    .slice(0, idx)
                    .reverse()
                    .find((pm) => pm.role === "user");
                  if (precedingUser) onSend(precedingUser.content);
                }}
              />
            ) : (
              <div className="chat-message-bubble">{m.content}</div>
            )}
            {m.role === "assistant" && m.errorReason && (
              <div className="chat-message-error-reason">{m.errorReason}</div>
            )}
            {m.role === "assistant" && !!m.tokenUsage && (
              <div className="chat-message-tokens">{m.tokenUsage.toLocaleString()} tokens</div>
            )}
          </div>
        ))}
        {sending && (
          <div className="chat-message chat-message-assistant">
            <div className="chat-message-bubble chat-message-pending">
              <PendingIndicator />
              {statusText && <div className="chat-status-text">{statusText}</div>}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      {window.__APP_CONFIG__?.modelName && (
        <div className="chat-model-label">利用モデル: {window.__APP_CONFIG__.modelName}</div>
      )}
      <div className="chat-input-row">
        <div className="chat-input-wrapper">
          <textarea
            ref={textareaRef}
            className="chat-input"
            value={input}
            placeholder="メッセージを入力... (Enterキーを3回連続で送信、またはボタンをクリック)"
            rows={1}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          {canExpand && (
            <button
              type="button"
              className="chat-input-toggle"
              onClick={() => setExpanded((v) => !v)}
              aria-label={expanded ? "入力欄を折りたたむ" : "入力欄を展開する"}
              title={expanded ? "折りたたむ" : "展開する(最大15行)"}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <path
                  d={expanded ? "M6 15l6-6l6 6" : "M6 9l6 6l6-6"}
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          )}
        </div>
        <button
          className="chat-send-button"
          onClick={submit}
          disabled={sending || !input.trim()}
          aria-label="送信"
          title="送信"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path
              d="M4 20L21 12L4 4L4 10.5L15 12L4 13.5L4 20Z"
              fill="currentColor"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
    </main>
  );
}
