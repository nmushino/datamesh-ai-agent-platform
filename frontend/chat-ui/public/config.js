// 本番コンテナでは entrypoint.sh が API_BASE_URL 環境変数からこのファイルを
// 実行時に書き換える。ローカル開発時はこのデフォルト値が使われる。
window.__APP_CONFIG__ = {
  apiBaseUrl: "http://localhost:8000",
  keycloakUrl: "http://localhost:8180",
  keycloakRealm: "ai-agent",
  keycloakClientId: "chat-ui",
  openMetadataUrl: "http://localhost:8585",
  developerHubUrl: "http://localhost:7007",
};
