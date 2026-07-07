import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ChatMessage } from "../types";
import { renderMarkdown } from "../markdown";
import { CopyIcon, CheckIcon } from "./MessageIcons";

interface Props {
  message: ChatMessage;
  animate: boolean;
  onApprove?: () => void;
  collapseLines?: number;
}

function formatTokens(n: number): string {
  return `${n.toLocaleString()} tokens`;
}

const TYPE_SPEED_MS = 18;
const DEFAULT_COLLAPSE_LINES = 30;
// N行分の目安の高さ (font-size 14px * line-height 1.5 * N行 + 上下padding)。
// Markdownテーブルは1行(生テキストの改行数)がセル内容の折り返しにより
// 見た目には何行分もの高さになることがあり、生テキストの改行数だけを
// 数える方式では「表なのに規定行数と判定されない」問題があった。実際に
// レンダリングされた高さを測定する方式に変更する。
function collapseMaxHeightPx(lines: number): number {
  return 14 * 1.5 * lines + 20;
}

// AIの回答を一文字ずつ表示するタイプライター演出。
// animateは初回マウント時の値だけを使う(以後の再レンダーで再生し直さないため)。
export function AssistantBubble({ message, animate, onApprove, collapseLines }: Props) {
  const collapseMaxHeight = collapseMaxHeightPx(collapseLines ?? DEFAULT_COLLAPSE_LINES);
  // NOTE: 過去に localStorage へ保存された旧スキーマのメッセージに content が
  // 欠けているケースがあり、そのまま .length へアクセスするとアプリ全体が
  // クラッシュする (真っ白画面) ため、必ず空文字にフォールバックする。
  const content = message.content ?? "";
  const [shown, setShown] = useState(animate ? "" : content);
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [needsCollapse, setNeedsCollapse] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

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

  // 実際にレンダリングされた高さを測定して折りたたみが必要か判定する。
  // 常に全文をDOMに描画しておき、折りたたみ時は CSS の max-height で
  // 見た目の高さだけを制限する(生テキストの改行数に依存しないため)。
  useLayoutEffect(() => {
    if (isTyping) return;
    const el = contentRef.current;
    if (!el) return;
    const prevMaxHeight = el.style.maxHeight;
    el.style.maxHeight = "none";
    setNeedsCollapse(el.scrollHeight > collapseMaxHeight);
    el.style.maxHeight = prevMaxHeight;
  }, [isTyping, content, collapseMaxHeight]);

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
      <div
        className="chat-message-bubble"
        ref={contentRef}
        style={
          !isTyping && needsCollapse && !expanded
            ? { maxHeight: collapseMaxHeight, overflow: "hidden" }
            : undefined
        }
      >
        {isTyping ? shown : renderMarkdown(content)}
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
      {!isTyping && message.requiresApproval && (
        <div className="chat-task-action">
          {message.taskStatus === "running" ? (
            <span className="chat-task-status">バックグラウンドで処理中... (完了すると通知ベルに表示されます)</span>
          ) : message.taskStatus === "done" ? (
            <span className="chat-task-status chat-task-status-done">タスク完了</span>
          ) : message.taskStatus === "error" ? (
            <span className="chat-task-status chat-task-status-error">タスクの実行に失敗しました</span>
          ) : (
            <button type="button" className="chat-task-button" onClick={onApprove}>
              タスクを実行
            </button>
          )}
        </div>
      )}
      {!isTyping && (
        <div className="chat-message-actions">
          {!!message.tokenUsage && (
            <>
              <span className="chat-message-actions-text">{formatTokens(message.tokenUsage)}</span>
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
        </div>
      )}
    </div>
  );
}
