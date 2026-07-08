import { useEffect, useState } from "react";
import type {
  AppDisplaySettings,
  MaxTokensLevel,
  MaxTokensSettings,
  ScheduledTaskSettings,
} from "../types";
import {
  fetchMaxTokensSettings,
  fetchScheduledTaskSettings,
  updateMaxTokensSettings,
  updateScheduledTaskSettings,
} from "../api";

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

// バックエンドが未応答でも入力欄には触れるようにしておくための初期値
// (接続が回復し次第PUTが送られ、実際の値に反映される)。
const FALLBACK_TASK_SETTINGS: ScheduledTaskSettings = {
  interval_seconds: 600,
  backoff_failure_threshold: 5,
  backoff_interval_seconds: 3600,
};

const FALLBACK_MAX_TOKENS_SETTINGS: MaxTokensSettings = {
  low: 1024,
  medium: 2048,
  high: 4096,
  max: 8192,
};

type Tab = "common" | "token";

// 入力してすぐ保存されると意図せず値が変わってしまうため、各項目は
// 手元(ドラフト)で編集してから「保存」ボタンを押すまでは確定させない。
function SettingField({
  label,
  value,
  min,
  disabled,
  onChange,
  onSave,
  saved,
}: {
  label: string;
  value: number;
  min: number;
  disabled?: boolean;
  onChange: (value: number) => void;
  onSave: () => void;
  saved: boolean;
}) {
  return (
    <label className="settings-field">
      <span>{label}</span>
      <span className="settings-field-input-row">
        <input
          type="number"
          min={min}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <button type="button" className="settings-field-save" onClick={onSave} disabled={disabled}>
          {saved ? "保存済み" : "保存"}
        </button>
      </span>
    </label>
  );
}

// 左メニュー最下部の「設定」ボタンから開くモーダル。
// 「共通設定」(定期チェック頻度・折りたたみ行数)と「トークン」
// (応答の長さの標準値・Thinkingの標準値)の2セクションに分かれる。
export function SettingsModal({ open, onClose, appSettings, onChangeAppSettings }: Props) {
  const [tab, setTab] = useState<Tab>("common");
  const [taskSettings, setTaskSettings] = useState<ScheduledTaskSettings>(FALLBACK_TASK_SETTINGS);
  const [taskDraft, setTaskDraft] = useState<ScheduledTaskSettings>(FALLBACK_TASK_SETTINGS);
  const [taskSaving, setTaskSaving] = useState(false);
  const [taskLoadError, setTaskLoadError] = useState(false);
  const [taskSavedField, setTaskSavedField] = useState<string | null>(null);

  const [maxTokensSettings, setMaxTokensSettings] = useState<MaxTokensSettings>(
    FALLBACK_MAX_TOKENS_SETTINGS
  );
  const [maxTokensDraft, setMaxTokensDraft] = useState<MaxTokensSettings>(
    FALLBACK_MAX_TOKENS_SETTINGS
  );
  const [maxTokensSaving, setMaxTokensSaving] = useState(false);
  const [maxTokensLoadError, setMaxTokensLoadError] = useState(false);
  const [maxTokensSavedField, setMaxTokensSavedField] = useState<string | null>(null);

  const [appDraft, setAppDraft] = useState<AppDisplaySettings>(appSettings);
  const [appSavedField, setAppSavedField] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    fetchScheduledTaskSettings().then((s) => {
      if (s) {
        setTaskSettings(s);
        setTaskDraft(s);
        setTaskLoadError(false);
      } else {
        setTaskLoadError(true);
      }
    });
    fetchMaxTokensSettings().then((s) => {
      if (s) {
        setMaxTokensSettings(s);
        setMaxTokensDraft(s);
        setMaxTokensLoadError(false);
      } else {
        setMaxTokensLoadError(true);
      }
    });
    setAppDraft(appSettings);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  // バックエンドの接続状況に関わらず、値の入力・変更自体は常に受け付ける
  // (保存ボタンを押した時点でPUTを送る。接続が復旧していればそこで
  // 実際に反映される)。
  const saveTaskField = (field: keyof ScheduledTaskSettings) => {
    const patch = { [field]: taskDraft[field] } as Partial<ScheduledTaskSettings>;
    setTaskSettings((prev) => ({ ...prev, ...patch }));
    setTaskSaving(true);
    updateScheduledTaskSettings(patch)
      .then((res) => {
        setTaskSettings(res);
        setTaskDraft(res);
        setTaskLoadError(false);
        setTaskSavedField(field);
        window.setTimeout(() => setTaskSavedField(null), 1500);
      })
      .catch(() => setTaskLoadError(true))
      .finally(() => setTaskSaving(false));
  };

  const saveMaxTokensField = (level: MaxTokensLevel) => {
    const patch = { [level]: maxTokensDraft[level] } as Partial<MaxTokensSettings>;
    setMaxTokensSettings((prev) => ({ ...prev, ...patch }));
    setMaxTokensSaving(true);
    updateMaxTokensSettings(patch)
      .then((res) => {
        setMaxTokensSettings(res);
        setMaxTokensDraft(res);
        setMaxTokensLoadError(false);
        setMaxTokensSavedField(level);
        window.setTimeout(() => setMaxTokensSavedField(null), 1500);
      })
      .catch(() => setMaxTokensLoadError(true))
      .finally(() => setMaxTokensSaving(false));
  };

  const saveAppField = (field: keyof AppDisplaySettings) => {
    onChangeAppSettings({ [field]: appDraft[field] } as Partial<AppDisplaySettings>);
    setAppSavedField(field);
    window.setTimeout(() => setAppSavedField(null), 1500);
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
            {taskLoadError && (
              <p className="settings-modal-error">
                設定の取得に失敗しました。バックエンドの接続を確認してください。
                (値を入力し保存しておけば、接続復旧時に反映されます)
              </p>
            )}
            <SettingField
              label="実行頻度(秒)"
              value={taskDraft.interval_seconds}
              min={60}
              disabled={taskSaving}
              onChange={(v) => setTaskDraft((prev) => ({ ...prev, interval_seconds: v }))}
              onSave={() => saveTaskField("interval_seconds")}
              saved={taskSavedField === "interval_seconds"}
            />
            <SettingField
              label="連続エラー何回でチェック頻度を延ばすか"
              value={taskDraft.backoff_failure_threshold}
              min={1}
              disabled={taskSaving}
              onChange={(v) => setTaskDraft((prev) => ({ ...prev, backoff_failure_threshold: v }))}
              onSave={() => saveTaskField("backoff_failure_threshold")}
              saved={taskSavedField === "backoff_failure_threshold"}
            />
            <SettingField
              label="延長後のチェック頻度(秒)"
              value={taskDraft.backoff_interval_seconds}
              min={60}
              disabled={taskSaving}
              onChange={(v) => setTaskDraft((prev) => ({ ...prev, backoff_interval_seconds: v }))}
              onSave={() => saveTaskField("backoff_interval_seconds")}
              saved={taskSavedField === "backoff_interval_seconds"}
            />

            <h3>メッセージの折りたたみ</h3>
            <SettingField
              label="メッセージ表示(行)"
              value={appDraft.userMessageCollapseLines}
              min={1}
              onChange={(v) => setAppDraft((prev) => ({ ...prev, userMessageCollapseLines: v }))}
              onSave={() => saveAppField("userMessageCollapseLines")}
              saved={appSavedField === "userMessageCollapseLines"}
            />
            <SettingField
              label="回答表示(行)"
              value={appDraft.assistantMessageCollapseLines}
              min={1}
              onChange={(v) =>
                setAppDraft((prev) => ({ ...prev, assistantMessageCollapseLines: v }))
              }
              onSave={() => saveAppField("assistantMessageCollapseLines")}
              saved={appSavedField === "assistantMessageCollapseLines"}
            />
          </div>
        )}

        {tab === "token" && (
          <div className="settings-modal-body">
            <h3>トークン表示MAX設定(各レベルの設定値)</h3>
            {maxTokensLoadError && (
              <p className="settings-modal-error">
                設定の取得に失敗しました。バックエンドの接続を確認してください。
                (値を入力し保存しておけば、接続復旧時に反映されます)
              </p>
            )}
            {MAX_TOKENS_OPTIONS.map((opt) => (
              <SettingField
                key={opt.level}
                label={`${opt.label}　現在の設定値`}
                value={maxTokensDraft[opt.level]}
                min={1}
                disabled={maxTokensSaving}
                onChange={(v) =>
                  setMaxTokensDraft((prev) => ({ ...prev, [opt.level]: v }))
                }
                onSave={() => saveMaxTokensField(opt.level)}
                saved={maxTokensSavedField === opt.level}
              />
            ))}

            <h3>既定の応答の長さ</h3>
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
