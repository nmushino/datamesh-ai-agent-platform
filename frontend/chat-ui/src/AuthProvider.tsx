import type { ReactNode } from "react";
import { AuthProvider as OidcAuthProvider } from "react-oidc-context";

export function AppAuthProvider({ children }: { children: ReactNode }) {
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
