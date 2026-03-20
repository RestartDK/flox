import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";
import {
  DEFAULT_PRODUCTION_BACKEND_URL,
  resolveBackendBaseUrl,
} from "./src/lib/backendConfig";

const DEFAULT_DEV_FRONTEND_PORT = 3000;

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const backendTarget =
    resolveBackendBaseUrl({
      explicitUrl: undefined,
      isProduction: mode === "production",
    }) || DEFAULT_PRODUCTION_BACKEND_URL;

  return {
    server: {
      host: "::",
      port: DEFAULT_DEV_FRONTEND_PORT,
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
        },
      },
      hmr: {
        overlay: false,
      },
    },
    preview: {
      host: "0.0.0.0",
      allowedHosts: true,
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
        },
      },
    },
    plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
      dedupe: ["react", "react-dom", "react/jsx-runtime", "@use-gesture/react"],
    },
  };
});
