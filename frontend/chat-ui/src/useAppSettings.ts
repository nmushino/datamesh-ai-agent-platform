import { useCallback, useEffect, useState } from "react";
import type { AppDisplaySettings } from "./types";

const STORAGE_KEY = "chat-ui.app-display-settings";

export const DEFAULT_APP_DISPLAY_SETTINGS: AppDisplaySettings = {
  userMessageCollapseLines: 15,
  assistantMessageCollapseLines: 30,
  defaultMaxTokensLevel: "low",
  defaultEnableThinking: false,
};

function loadAppDisplaySettings(): AppDisplaySettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_APP_DISPLAY_SETTINGS;
    return { ...DEFAULT_APP_DISPLAY_SETTINGS, ...(JSON.parse(raw) as Partial<AppDisplaySettings>) };
  } catch {
    return DEFAULT_APP_DISPLAY_SETTINGS;
  }
}

// 折りたたみ行数・トークン/Thinkingの標準値は個人のブラウザごとの表示設定
// なので、共通の定期チェック設定とは異なりバックエンドには保存せず
// localStorage に保存する。
export function useAppSettings() {
  const [appSettings, setAppSettings] = useState<AppDisplaySettings>(() => loadAppDisplaySettings());

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(appSettings));
  }, [appSettings]);

  const updateAppSettings = useCallback((patch: Partial<AppDisplaySettings>) => {
    setAppSettings((prev) => ({ ...prev, ...patch }));
  }, []);

  return { appSettings, updateAppSettings };
}
