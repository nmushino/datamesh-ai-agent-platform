export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  tokenUsage?: number;
  errorReason?: string;
  requiresApproval?: boolean;
  approvalAction?: string;
  taskStatus?: "idle" | "running" | "done" | "error";
}

export interface Thread {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

export type MaxTokensLevel = "low" | "medium" | "high" | "max";

export interface ChatSettings {
  enableThinking: boolean;
  maxTokensLevel: MaxTokensLevel;
}

// ブラウザに保存する表示関連の共通設定(折りたたみ行数・トークン/Thinkingの標準値)。
export interface AppDisplaySettings {
  userMessageCollapseLines: number;
  assistantMessageCollapseLines: number;
  defaultMaxTokensLevel: MaxTokensLevel;
  defaultEnableThinking: boolean;
}

// バックエンドの定期チェックスレッドを制御する、全ユーザー共通の設定。
export interface ScheduledTaskSettings {
  interval_seconds: number;
  backoff_failure_threshold: number;
  backoff_interval_seconds: number;
}

// 低/中/高/最高 それぞれの実際のmax_tokens値(全ユーザー共通のバックエンド設定)。
export interface MaxTokensSettings {
  low: number;
  medium: number;
  high: number;
  max: number;
}

export interface ChatResponse {
  thread_id: string;
  reply: string;
  intent: string;
  active_agent: string;
  requires_approval: boolean;
  approval_action: string;
  token_usage: number;
}

export interface Notification {
  pipeline?: string;
  status?: string;
  message?: string;
  timestamp?: string;
  [key: string]: unknown;
}

export interface ScheduledTask {
  id: string;
  task_name: string;
  fqn: string;
  status: "ok" | "changed" | "error";
  message: string;
  timestamp: string;
}

declare global {
  interface Window {
    __APP_CONFIG__: {
      apiBaseUrl: string;
      keycloakUrl: string;
      keycloakRealm: string;
      keycloakClientId: string;
      openMetadataUrl: string;
      developerHubUrl: string;
      modelName?: string;
    };
  }
}
