import type { ReactNode } from "react";
import { AuthProvider as OidcAuthProvider } from "react-oidc-context";

// ローカルで画面開発だけを行う場合、Keycloak無しで起動できるようにするバイパス。
// .env.local に VITE_SKIP_AUTH=true を設定すると有効になる (本番ビルドには影響しない)。
const SKIP_AUTH = import.meta.env.VITE_SKIP_AUTH === "true";

export function AppAuthProvider({ children }: { children: ReactNode }) {
  if (SKIP_AUTH) {
    return <>{children}</>;
  }

  const config = window.__APP_CONFIG__;

  const oidcConfig = {
    authority: `${config.keycloakUrl}/realms/${config.keycloakRealm}`,
    client_id: config.keycloakClientId,
    redirect_uri: window.location.origin,
    post_logout_redirect_uri: window.location.origin,
    onSigninCallback: () => {
      // 認可コード等のクエリパラメータをURLから消す
      window.history.replaceState({}, document.title, window.location.pathname);
    },
  };

  return <OidcAuthProvider {...oidcConfig}>{children}</OidcAuthProvider>;
}
