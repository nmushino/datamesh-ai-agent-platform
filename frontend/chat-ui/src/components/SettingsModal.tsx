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
  enabled: true,
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
// 手元(ドラフト)で編集し、タブ下部の「保存」ボタンを押すまでは確定させない。
function SettingField({
  label,
  value,
  min,
  disabled,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <label className="settings-field">
      <span>{label}</span>
      <input
        type="number"
        min={min}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}

// 左メニュー最下部の「設定」ボタンから開くモーダル。
// 「共通設定」(定期チェック頻度・折りたたみ行数)と「トークン」
// (応答の長さの標準値・Thinkingの標準値)の2セクションに分かれる。
// 各タブの下部に1つだけ「保存」ボタンがあり、そのタブ内の未保存項目を
// まとめて確定させる(項目ごとの個別保存ボタンは持たない)。
export function SettingsModal({ open, onClose, appSettings, onChangeAppSettings }: Props) {
  const [tab, setTab] = useState<Tab>("common");
  const [taskSettings, setTaskSettings] = useState<ScheduledTaskSettings>(FALLBACK_TASK_SETTINGS);
  const [taskDraft, setTaskDraft] = useState<ScheduledTaskSettings>(FALLBACK_TASK_SETTINGS);
  const [taskSaving, setTaskSaving] = useState(false);
  const [taskLoadError, setTaskLoadError] = useState(false);

  const [maxTokensSettings, setMaxTokensSettings] = useState<MaxTokensSettings>(
    FALLBACK_MAX_TOKENS_SETTINGS
  );
  const [maxTokensDraft, setMaxTokensDraft] = useState<MaxTokensSettings>(
    FALLBACK_MAX_TOKENS_SETTINGS
  );
  const [maxTokensSaving, setMaxTokensSaving] = useState(false);
  const [maxTokensLoadError, setMaxTokensLoadError] = useState(false);

  const [appDraft, setAppDraft] = useState<AppDisplaySettings>(appSettings);

  const [commonSaved, setCommonSaved] = useState(false);
  const [tokenSaved, setTokenSaved] = useState(false);

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

  // ON/OFFトグル類はタブの保存ボタンを待たず即時反映する(数値項目のみ
  // ドラフト→保存ボタンでまとめて確定する対象)。
  const toggleTaskEnabled = () => {
    const nextEnabled = !taskSettings.enabled;
    setTaskSettings((prev) => ({ ...prev, enabled: nextEnabled }));
    setTaskDraft((prev) => ({ ...prev, enabled: nextEnabled }));
    updateScheduledTaskSettings({ enabled: nextEnabled })
      .then((res) => {
        setTaskSettings(res);
        setTaskDraft(res);
        setTaskLoadError(false);
      })
      .catch(() => setTaskLoadError(true));
  };

  // 「共通設定」タブの保存ボタン: 定期チェック設定(数値項目)とメッセージ
  // 折りたたみ設定(ローカル表示設定)をまとめて確定する。
  const saveCommonTab = () => {
    setAppDraft((current) => {
      onChangeAppSettings({
        userMessageCollapseLines: current.userMessageCollapseLines,
        assistantMessageCollapseLines: current.assistantMessageCollapseLines,
      });
      return current;
    });

    const patch: Partial<ScheduledTaskSettings> = {
      interval_seconds: taskDraft.interval_seconds,
      backoff_failure_threshold: taskDraft.backoff_failure_threshold,
      backoff_interval_seconds: taskDraft.backoff_interval_seconds,
    };
    setTaskSettings((prev) => ({ ...prev, ...patch }));
    setTaskSaving(true);
    updateScheduledTaskSettings(patch)
      .then((res) => {
        setTaskSettings(res);
        setTaskDraft(res);
        setTaskLoadError(false);
        setCommonSaved(true);
        window.setTimeout(() => setCommonSaved(false), 1500);
      })
      .catch(() => setTaskLoadError(true))
      .finally(() => setTaskSaving(false));
  };

  // 「トークン」タブの保存ボタン: 各レベルのトークン数上限をまとめて確定する。
  const saveTokenTab = () => {
    setMaxTokensSettings((prev) => ({ ...prev, ...maxTokensDraft }));
    setMaxTokensSaving(true);
    updateMaxTokensSettings(maxTokensDraft)
      .then((res) => {
        setMaxTokensSettings(res);
        setMaxTokensDraft(res);
        setMaxTokensLoadError(false);
        setTokenSaved(true);
        window.setTimeout(() => setTokenSaved(false), 1500);
      })
      .catch(() => setMaxTokensLoadError(true))
      .finally(() => setMaxTokensSaving(false));
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
            <label className="settings-field">
              <span>定期実行</span>
              <button
                type="button"
                className={`chat-settings-toggle ${
                  taskSettings.enabled ? "chat-settings-toggle-on" : ""
                }`}
                onClick={toggleTaskEnabled}
                aria-pressed={taskSettings.enabled}
              >
                定期実行: {taskSettings.enabled ? "ON" : "OFF"}
              </button>
            </label>
            <SettingField
              label="実行頻度(秒)"
              value={taskDraft.interval_seconds}
              min={60}
              disabled={taskSaving || !taskSettings.enabled}
              onChange={(v) => setTaskDraft((prev) => ({ ...prev, interval_seconds: v }))}
            />
            <SettingField
              label="連続エラー何回でチェック頻度を延ばすか"
              value={taskDraft.backoff_failure_threshold}
              min={1}
              disabled={taskSaving || !taskSettings.enabled}
              onChange={(v) => setTaskDraft((prev) => ({ ...prev, backoff_failure_threshold: v }))}
            />
            <SettingField
              label="延長後のチェック頻度(秒)"
              value={taskDraft.backoff_interval_seconds}
              min={60}
              disabled={taskSaving || !taskSettings.enabled}
              onChange={(v) => setTaskDraft((prev) => ({ ...prev, backoff_interval_seconds: v }))}
            />

            <h3>メッセージの折りたたみ</h3>
            <SettingField
              label="メッセージ表示(行)"
              value={appDraft.userMessageCollapseLines}
              min={1}
              onChange={(v) => setAppDraft((prev) => ({ ...prev, userMessageCollapseLines: v }))}
            />
            <SettingField
              label="回答表示(行)"
              value={appDraft.assistantMessageCollapseLines}
              min={1}
              onChange={(v) =>
                setAppDraft((prev) => ({ ...prev, assistantMessageCollapseLines: v }))
              }
            />

            <div className="settings-modal-save-row">
              <button
                type="button"
                className="settings-modal-save"
                onClick={saveCommonTab}
                disabled={taskSaving}
              >
                {commonSaved ? "保存済み" : "保存"}
              </button>
            </div>
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

            <div className="settings-modal-save-row">
              <button
                type="button"
                className="settings-modal-save"
                onClick={saveTokenTab}
                disabled={maxTokensSaving}
              >
                {tokenSaved ? "保存済み" : "保存"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
