import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { Toaster } from "./components/ui/toast";
import { AuthProvider } from "./context/auth-context";
import { authApi, clearLegacyAccessToken } from "./lib/api";
import { cameFromEklink } from "./lib/eklink";
import { createQueryClient } from "./lib/query/client";
import "./styles.css";

// Sessions are httpOnly cookies now; drop any token the old auth left behind.
clearLegacyAccessToken();

// Opened from the EkLink dashboard: sign in through EkLink so the session is
// whoever is signed in there, even if another account was signed in here.
if (document.referrer && window.location.pathname !== "/auth/callback") {
  authApi
    .eklinkConfig()
    .then((config) => {
      if (config.enabled && cameFromEklink(document.referrer, config.eklink_url)) {
        window.location.replace(authApi.eklinkLoginUrl);
      }
    })
    .catch(() => undefined);
}

const queryClient = createQueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
          <Toaster />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
