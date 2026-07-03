import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AppAuthProvider } from "./AuthProvider";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppAuthProvider>
      <App />
    </AppAuthProvider>
  </React.StrictMode>
);
