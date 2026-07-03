export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
}

export interface Thread {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
}

export interface ChatResponse {
  thread_id: string;
  reply: string;
  intent: string;
  active_agent: string;
  requires_approval: boolean;
  approval_action: string;
}

export interface Notification {
  pipeline?: string;
  status?: string;
  message?: string;
  timestamp?: string;
  [key: string]: unknown;
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
    };
  }
}
