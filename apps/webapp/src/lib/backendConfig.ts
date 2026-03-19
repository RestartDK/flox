export const DEFAULT_DEV_BACKEND_PORT = "9812";
export const DEFAULT_PRODUCTION_BACKEND_URL =
  "https://starthack26-backend-production.up.railway.app";

type BackendBaseUrlOptions = {
  explicitUrl?: string;
  isProduction: boolean;
};

const trimTrailingSlash = (value?: string) => value?.replace(/\/$/, "");

export const resolveBackendBaseUrl = ({
  explicitUrl,
  isProduction,
}: BackendBaseUrlOptions): string | undefined => {
  const normalizedExplicitUrl = trimTrailingSlash(explicitUrl);
  if (normalizedExplicitUrl) {
    return normalizedExplicitUrl;
  }

  if (isProduction) {
    return DEFAULT_PRODUCTION_BACKEND_URL;
  }

  return undefined;
};
