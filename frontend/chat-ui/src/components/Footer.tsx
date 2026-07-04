import { RedHatIcon } from "./RedHatIcon";

export function Footer() {
  const config = window.__APP_CONFIG__;
  const year = new Date().getFullYear();

  return (
    <footer className="app-footer">
      <div className="app-footer-brand">
        <RedHatIcon size={34} />
        <span>Red Hat</span>
      </div>
      <div className="app-footer-links">
        <span>Copyright © {year} Red Hat</span>
        {config.openMetadataUrl && (
          <>
            <span className="app-footer-sep">|</span>
            <a href={config.openMetadataUrl} target="_blank" rel="noreferrer">
              OpenMetadata
            </a>
          </>
        )}
        {config.developerHubUrl && (
          <>
            <span className="app-footer-sep">|</span>
            <a href={config.developerHubUrl} target="_blank" rel="noreferrer">
              Datamesh Hub
            </a>
          </>
        )}
      </div>
    </footer>
  );
}
