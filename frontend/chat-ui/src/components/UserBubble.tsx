import { useState } from "react";
import type { ChatMessage } from "../types";

interface Props {
  message: ChatMessage;
  onResend?: () => void;
}

const COLLAPSE_LINE_THRESHOLD = 15;

// ユーザー送信メッセージ側の表示。長文の折りたたみ・コピー・再送信ボタンを
// AssistantBubble と揃えて提供する (アシスタント側にしか無かったものを
// 送信側にも付けてほしいという要望に対応)。
export function UserBubble({ message, onResend }: Props) {
  const content = message.content ?? "";
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const lineCount = content.split("\n").length;
  const needsCollapse = lineCount > COLLAPSE_LINE_THRESHOLD;
  const shownContent =
    needsCollapse && !expanded
      ? content.split("\n").slice(0, COLLAPSE_LINE_THRESHOLD).join("\n")
      : content;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // クリップボードAPIが使えない環境では何もしない
    }
  };

  return (
    <div>
      <div className="chat-message-bubble">{shownContent}</div>
      {needsCollapse && (
        <button
          type="button"
          className="chat-message-toggle"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "折りたたむ" : "すべて表示"}
        </button>
      )}
      <div className="chat-message-actions">
        <button type="button" className="chat-message-action" onClick={handleCopy}>
          {copied ? "コピーしました" : "コピー"}
        </button>
        {onResend && (
          <button type="button" className="chat-message-action" onClick={onResend}>
            やり直す
          </button>
        )}
      </div>
    </div>
  );
}
