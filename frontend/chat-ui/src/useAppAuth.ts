import { useAuth as useOidcAuth } from "react-oidc-context";

// ローカルで画面開発だけを行う場合、Keycloak無しで起動できるようにするバイパス。
// .env.local に VITE_SKIP_AUTH=true を設定すると有効になる (本番ビルドには影響しない)。
const SKIP_AUTH = import.meta.env.VITE_SKIP_AUTH === "true";

export interface AppAuth {
  isLoading: boolean;
  isAuthenticated: boolean;
  activeNavigator?: string;
  error?: Error;
  user?: {
    access_token?: string;
    profile?: { preferred_username?: string; name?: string };
  } | null;
  signinRedirect: () => Promise<void>;
  signoutRedirect: () => Promise<void>;
}

const mockAuth: AppAuth = {
  isLoading: false,
  isAuthenticated: true,
  activeNavigator: undefined,
  error: undefined,
  user: { access_token: undefined, profile: { preferred_username: "dev-user" } },
  signinRedirect: async () => {},
  signoutRedirect: async () => {},
};

export function useAppAuth(): AppAuth {
  if (SKIP_AUTH) return mockAuth;
  // SKIP_AUTH は起動時に固定される環境変数のため、実行中に条件が変わることはない
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useOidcAuth();
}
