export const DEFAULT_DEV_BACKEND_PORT = "9812";
export const DEFAULT_PRODUCTION_BACKEND_URL =
  "https://starthack26-backend-production.up.railway.app";

type BackendBaseUrlOptions = {
  explicitUrl?: string;
  isProduction: boolean;
};

const trimTrailingSlash = (value?: string) => value?.replace(/\/$/, "");

const stripWrappingQuotes = (value?: string) => {
  if (!value) {
    return value;
  }

  const trimmed = value.trim();
  return trimmed.replace(/^['\"]|['\"]$/g, "");
};

const normalizeExplicitUrl = (value?: string) => {
  const normalized = trimTrailingSlash(stripWrappingQuotes(value));
  if (!normalized) {
    return undefined;
  }

  return /^https?:\/\//.test(normalized) ? normalized : undefined;
};

export const resolveBackendBaseUrl = ({
  explicitUrl,
  isProduction,
}: BackendBaseUrlOptions): string | undefined => {
  const normalizedExplicitUrl = normalizeExplicitUrl(explicitUrl);
  if (normalizedExplicitUrl) {
    return normalizedExplicitUrl;
  }

  if (isProduction) {
    return DEFAULT_PRODUCTION_BACKEND_URL;
  }

  return undefined;
};
