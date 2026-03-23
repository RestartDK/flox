export const DEFAULT_DEV_BACKEND_PORT = "9812";
export const DEFAULT_DEV_BACKEND_URL = `http://localhost:${DEFAULT_DEV_BACKEND_PORT}`;
export const DEFAULT_PRODUCTION_BACKEND_URL: string | undefined = undefined;

type BackendBaseUrlOptions = {
  explicitUrl?: string;
  isProduction: boolean;
};

export const resolveBackendBaseUrl = ({
  explicitUrl,
  isProduction,
}: BackendBaseUrlOptions): string | undefined => {
  const trimmedExplicitUrl = explicitUrl?.trim();
  const normalizedExplicitUrl = trimmedExplicitUrl?.replace(/\/+$/, "");

  if (normalizedExplicitUrl) {
    return normalizedExplicitUrl;
  }

  if (isProduction) {
    return DEFAULT_PRODUCTION_BACKEND_URL;
  }

  return DEFAULT_DEV_BACKEND_URL;
};
