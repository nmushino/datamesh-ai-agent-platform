import { useEffect, useState } from "react";
import type { ChatMessage } from "../types";
import { renderMarkdown } from "../markdown";

interface Props {
  message: ChatMessage;
  animate: boolean;
  onRegenerate?: () => void;
}

const TYPE_SPEED_MS = 18;
const COLLAPSE_LINE_THRESHOLD = 15;

// AIの回答を一文字ずつ表示するタイプライター演出。
// animateは初回マウント時の値だけを使う(以後の再レンダーで再生し直さないため)。
export function AssistantBubble({ message, animate, onRegenerate }: Props) {
  // NOTE: 過去に localStorage へ保存された旧スキーマのメッセージに content が
  // 欠けているケースがあり、そのまま .length へアクセスするとアプリ全体が
  // クラッシュする (真っ白画面) ため、必ず空文字にフォールバックする。
  const content = message.content ?? "";
  const [shown, setShown] = useState(animate ? "" : content);
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!animate) return;
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      setShown(content.slice(0, i));
      if (i >= content.length) {
        window.clearInterval(id);
      }
    }, TYPE_SPEED_MS);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isTyping = shown.length < content.length;
  const lineCount = content.split("\n").length;
  const needsCollapse = lineCount > COLLAPSE_LINE_THRESHOLD;
  const collapsedContent =
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
      <div className="chat-message-bubble">
        {isTyping ? shown : renderMarkdown(collapsedContent)}
      </div>
      {!isTyping && needsCollapse && (
        <button
          type="button"
          className="chat-message-toggle"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "折りたたむ" : "すべて表示"}
        </button>
      )}
      {!isTyping && (
        <div className="chat-message-actions">
          <button type="button" className="chat-message-action" onClick={handleCopy}>
            {copied ? "コピーしました" : "コピー"}
          </button>
          {onRegenerate && (
            <button type="button" className="chat-message-action" onClick={onRegenerate}>
              やり直す
            </button>
          )}
        </div>
      )}
    </div>
  );
}
