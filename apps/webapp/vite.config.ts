import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";
import {
  DEFAULT_DEV_BACKEND_PORT,
  resolveBackendBaseUrl,
} from "./src/lib/backendConfig";

const DEFAULT_DEV_FRONTEND_PORT = 3000;

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendPort = env.BACKEND_PORT || DEFAULT_DEV_BACKEND_PORT;
  const explicitBackendUrl =
    mode === "production" ? undefined : env.VITE_BACKEND_URL || env.BACKEND_URL;
  const backendTarget =
    resolveBackendBaseUrl({
      explicitUrl: explicitBackendUrl,
      isProduction: mode === "production",
    }) || `http://127.0.0.1:${backendPort}`;

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
