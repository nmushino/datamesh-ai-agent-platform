import { useEffect, useState } from "react";
import type { ChatMessage } from "../types";

interface Props {
  message: ChatMessage;
  animate: boolean;
}

const TYPE_SPEED_MS = 18;

// AIの回答を一文字ずつ表示するタイプライター演出。
// animateは初回マウント時の値だけを使う(以後の再レンダーで再生し直さないため)。
export function AssistantBubble({ message, animate }: Props) {
  const [shown, setShown] = useState(animate ? "" : message.content);

  useEffect(() => {
    if (!animate) return;
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      setShown(message.content.slice(0, i));
      if (i >= message.content.length) {
        window.clearInterval(id);
      }
    }, TYPE_SPEED_MS);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div className="chat-message-bubble">{shown}</div>;
}
