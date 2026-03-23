import { defineConfig, loadEnv } from "vite";
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
  const env = loadEnv(mode, process.cwd(), "");
  const backendTarget =
    resolveBackendBaseUrl({
      explicitUrl: env.VITE_BACKEND_URL,
      isProduction: mode === "production",
    }) || DEFAULT_PRODUCTION_BACKEND_URL;

  const proxy = backendTarget
    ? {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
        },
      }
    : undefined;

  return {
    server: {
      host: "::",
      port: DEFAULT_DEV_FRONTEND_PORT,
      proxy,
      hmr: {
        overlay: false,
      },
    },
    preview: {
      host: "0.0.0.0",
      allowedHosts: true,
      proxy,
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
