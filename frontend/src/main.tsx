import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import App from "./App";
import "./index.css";
import { registerServiceWorker } from "./pwa";
import { SessionProvider } from "./session";

// The service worker belongs to the built app only: `npm run dev` must never be cached.
if (import.meta.env.PROD) registerServiceWorker();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <SessionProvider>
        <App />
      </SessionProvider>
    </BrowserRouter>
  </StrictMode>,
);
