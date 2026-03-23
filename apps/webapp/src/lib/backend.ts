import {
  DEFAULT_PRODUCTION_BACKEND_URL,
  resolveBackendBaseUrl,
} from './backendConfig';

export const getBackendBaseUrl = () => {
  return (
    resolveBackendBaseUrl({
      explicitUrl: import.meta.env.VITE_BACKEND_URL,
      isProduction: import.meta.env.PROD,
    }) ?? DEFAULT_PRODUCTION_BACKEND_URL
  );
};

export const buildBackendUrl = (path: string) => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const base = getBackendBaseUrl();
  return base ? `${base}${normalizedPath}` : normalizedPath;
};
