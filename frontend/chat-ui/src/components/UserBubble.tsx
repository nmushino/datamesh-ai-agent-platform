import { useState } from "react";
import type { ChatMessage } from "../types";
import { CopyIcon, CheckIcon, RedoIcon, EyeIcon } from "./MessageIcons";

interface Props {
  message: ChatMessage;
  onResend?: () => void;
}

const COLLAPSE_LINE_THRESHOLD = 30;

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
    <div className="chat-message-user-inner">
      <div className="chat-message-bubble">{shownContent}</div>
      <div className="chat-message-actions">
        {needsCollapse && (
          <>
            <button
              type="button"
              className="chat-message-icon-action"
              onClick={() => setExpanded((v) => !v)}
              aria-label={expanded ? "折りたたむ" : "すべて表示"}
              title={expanded ? "折りたたむ" : "すべて表示"}
            >
              <EyeIcon open={expanded} />
            </button>
            <span className="chat-message-actions-sep">|</span>
          </>
        )}
        <button
          type="button"
          className="chat-message-icon-action"
          onClick={handleCopy}
          aria-label="コピー"
          title={copied ? "コピーしました" : "コピー"}
        >
          {copied ? <CheckIcon /> : <CopyIcon />}
        </button>
        {onResend && (
          <>
            <span className="chat-message-actions-sep">|</span>
            <button
              type="button"
              className="chat-message-icon-action"
              onClick={onResend}
              aria-label="やり直す"
              title="やり直す(入力欄にコピー)"
            >
              <RedoIcon />
            </button>
          </>
        )}
      </div>
    </div>
  );
}
