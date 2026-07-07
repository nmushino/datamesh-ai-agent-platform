import { useEffect, useState } from "react";
import type { AppDisplaySettings, MaxTokensLevel, ScheduledTaskSettings } from "../types";
import { fetchScheduledTaskSettings, updateScheduledTaskSettings } from "../api";

interface Props {
  open: boolean;
  onClose: () => void;
  appSettings: AppDisplaySettings;
  onChangeAppSettings: (patch: Partial<AppDisplaySettings>) => void;
}

const MAX_TOKENS_OPTIONS: { level: MaxTokensLevel; label: string }[] = [
  { level: "low", label: "低" },
  { level: "medium", label: "中" },
  { level: "high", label: "高" },
  { level: "max", label: "最高" },
];

type Tab = "common" | "token";

// 左メニュー最下部の「設定」ボタンから開くモーダル。
// 「共通設定」(定期チェック頻度・折りたたみ行数)と「トークン」
// (応答の長さの標準値・Thinkingの標準値)の2セクションに分かれる。
export function SettingsModal({ open, onClose, appSettings, onChangeAppSettings }: Props) {
  const [tab, setTab] = useState<Tab>("common");
  const [taskSettings, setTaskSettings] = useState<ScheduledTaskSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    if (!open) return;
    fetchScheduledTaskSettings().then((s) => {
      if (s) {
        setTaskSettings(s);
        setLoadError(false);
      } else {
        setLoadError(true);
      }
    });
  }, [open]);

  if (!open) return null;

  const saveTaskSettings = (patch: Partial<ScheduledTaskSettings>) => {
    if (!taskSettings) return;
    const next = { ...taskSettings, ...patch };
    setTaskSettings(next);
    setSaving(true);
    updateScheduledTaskSettings(patch)
      .then((res) => setTaskSettings(res))
      .catch(() => setLoadError(true))
      .finally(() => setSaving(false));
  };

  return (
    <div className="settings-modal-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="settings-modal-header">
          <h2>設定</h2>
          <button
            type="button"
            className="settings-modal-close"
            onClick={onClose}
            aria-label="閉じる"
          >
            ×
          </button>
        </div>
        <div className="settings-modal-tabs" role="tablist">
          <button
            type="button"
            className={`settings-modal-tab ${tab === "common" ? "settings-modal-tab-active" : ""}`}
            onClick={() => setTab("common")}
          >
            共通設定
          </button>
          <button
            type="button"
            className={`settings-modal-tab ${tab === "token" ? "settings-modal-tab-active" : ""}`}
            onClick={() => setTab("token")}
          >
            トークン
          </button>
        </div>

        {tab === "common" && (
          <div className="settings-modal-body">
            <h3>定期チェック実行履歴</h3>
            {loadError && (
              <p className="settings-modal-error">
                設定の取得に失敗しました。バックエンドの接続を確認してください。
              </p>
            )}
            <label className="settings-field">
              <span>実行頻度(秒)</span>
              <input
                type="number"
                min={60}
                value={taskSettings?.interval_seconds ?? ""}
                disabled={!taskSettings || saving}
                onChange={(e) =>
                  saveTaskSettings({ interval_seconds: Number(e.target.value) })
                }
              />
            </label>
            <label className="settings-field">
              <span>連続エラー何回でチェック頻度を延ばすか</span>
              <input
                type="number"
                min={1}
                value={taskSettings?.backoff_failure_threshold ?? ""}
                disabled={!taskSettings || saving}
                onChange={(e) =>
                  saveTaskSettings({ backoff_failure_threshold: Number(e.target.value) })
                }
              />
            </label>
            <label className="settings-field">
              <span>延長後のチェック頻度(秒)</span>
              <input
                type="number"
                min={60}
                value={taskSettings?.backoff_interval_seconds ?? ""}
                disabled={!taskSettings || saving}
                onChange={(e) =>
                  saveTaskSettings({ backoff_interval_seconds: Number(e.target.value) })
                }
              />
            </label>

            <h3>メッセージの折りたたみ</h3>
            <label className="settings-field">
              <span>メッセージ表示(行)</span>
              <input
                type="number"
                min={1}
                value={appSettings.userMessageCollapseLines}
                onChange={(e) =>
                  onChangeAppSettings({ userMessageCollapseLines: Number(e.target.value) })
                }
              />
            </label>
            <label className="settings-field">
              <span>回答表示(行)</span>
              <input
                type="number"
                min={1}
                value={appSettings.assistantMessageCollapseLines}
                onChange={(e) =>
                  onChangeAppSettings({ assistantMessageCollapseLines: Number(e.target.value) })
                }
              />
            </label>
          </div>
        )}

        {tab === "token" && (
          <div className="settings-modal-body">
            <h3>トークン表示MAX設定</h3>
            <div className="settings-modal-level-group" role="group">
              {MAX_TOKENS_OPTIONS.map((opt) => (
                <button
                  key={opt.level}
                  type="button"
                  className={`chat-settings-level ${
                    appSettings.defaultMaxTokensLevel === opt.level
                      ? "chat-settings-level-active"
                      : ""
                  }`}
                  onClick={() => onChangeAppSettings({ defaultMaxTokensLevel: opt.level })}
                  aria-pressed={appSettings.defaultMaxTokensLevel === opt.level}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            <h3>Thinking標準値</h3>
            <button
              type="button"
              className={`chat-settings-toggle ${
                appSettings.defaultEnableThinking ? "chat-settings-toggle-on" : ""
              }`}
              onClick={() =>
                onChangeAppSettings({ defaultEnableThinking: !appSettings.defaultEnableThinking })
              }
              aria-pressed={appSettings.defaultEnableThinking}
            >
              Thinking: {appSettings.defaultEnableThinking ? "ON" : "OFF"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
