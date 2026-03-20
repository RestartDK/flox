export const DEFAULT_DEV_BACKEND_PORT = "9812";
export const DEFAULT_PRODUCTION_BACKEND_URL =
  "https://starthack26-backend-production.up.railway.app";

type BackendBaseUrlOptions = {
  explicitUrl?: string;
  isProduction: boolean;
};

export const resolveBackendBaseUrl = ({
  explicitUrl: _explicitUrl,
  isProduction: _isProduction,
}: BackendBaseUrlOptions): string | undefined => {
  return DEFAULT_PRODUCTION_BACKEND_URL;
};
