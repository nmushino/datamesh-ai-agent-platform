import type { ChatSettings, MaxTokensLevel } from "../types";

interface Props {
  settings: ChatSettings;
  onChange: (settings: ChatSettings) => void;
}

const MAX_TOKENS_OPTIONS: { level: MaxTokensLevel; label: string }[] = [
  { level: "low", label: "低" },
  { level: "medium", label: "中" },
  { level: "high", label: "高" },
  { level: "max", label: "最高" },
];

// Thinkingモードのオン/オフ、応答の長さ(max_tokens)を4段階から
// チャット画面で毎回選べるようにする設定バー。
export function ChatSettingsBar({ settings, onChange }: Props) {
  return (
    <div className="chat-settings-bar">
      <button
        type="button"
        className={`chat-settings-toggle ${settings.enableThinking ? "chat-settings-toggle-on" : ""}`}
        onClick={() => onChange({ ...settings, enableThinking: !settings.enableThinking })}
        aria-pressed={settings.enableThinking}
        title="Thinkingモード(推論過程の表示)のオン/オフ"
      >
        Thinking: {settings.enableThinking ? "ON" : "OFF"}
      </button>
      <div className="chat-settings-max-tokens" role="group" aria-label="応答の長さ">
        {MAX_TOKENS_OPTIONS.map((opt) => (
          <button
            key={opt.level}
            type="button"
            className={`chat-settings-level ${
              settings.maxTokensLevel === opt.level ? "chat-settings-level-active" : ""
            }`}
            onClick={() => onChange({ ...settings, maxTokensLevel: opt.level })}
            aria-pressed={settings.maxTokensLevel === opt.level}
            title={`応答の長さ: ${opt.label}`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}
