import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { Toaster } from "./components/ui/toast";
import { AuthProvider } from "./context/auth-context";
import { clearLegacyAccessToken } from "./lib/api";
import { createQueryClient } from "./lib/query/client";
import "./styles.css";

// Sessions are httpOnly cookies now; drop any token the old auth left behind.
clearLegacyAccessToken();

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
