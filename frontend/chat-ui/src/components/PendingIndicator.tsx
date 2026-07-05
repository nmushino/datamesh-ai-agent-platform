import { useEffect, useState } from "react";

// 応答待ちの間、経過時間と生成中トークン数の目安をアニメーションで表示する
// (バックエンドはトークン単位のストリーミングを返さないため、待機中である
//  ことが視覚的に伝わるよう目安の値をカウントアップ表示する)
export function PendingIndicator() {
  const [elapsedMs, setElapsedMs] = useState(0);
  const [tokenCount, setTokenCount] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    const id = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAt);
      setTokenCount((c) => c + Math.floor(Math.random() * 3) + 1);
    }, 220);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="pending-indicator">
      <span className="pending-dots" aria-hidden="true">
        <span className="pending-dot" />
        <span className="pending-dot" />
        <span className="pending-dot" />
      </span>
      <span className="pending-meta">
        考え中… {tokenCount} tokens / {(elapsedMs / 1000).toFixed(1)}s
      </span>
    </div>
  );
}
