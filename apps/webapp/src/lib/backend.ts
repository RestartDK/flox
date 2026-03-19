const DEFAULT_PRODUCTION_BACKEND_URL = 'https://starthack26-backend-production.up.railway.app';

const getRuntimeEnv = (): Record<string, string | boolean | undefined> => {
  const withEnv = import.meta as ImportMeta & {
    env?: Record<string, string | boolean | undefined>;
  };
  return withEnv.env ?? {};
};

export const getBackendBaseUrl = () => {
  const env = getRuntimeEnv();
  const configured = typeof env.VITE_BACKEND_URL === 'string' ? env.VITE_BACKEND_URL.replace(/\/$/, '') : '';
  if (configured) {
    return configured;
  }

  if (env.PROD) {
    return DEFAULT_PRODUCTION_BACKEND_URL;
  }

  return '';
};

export const buildBackendUrl = (path: string) => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const base = getBackendBaseUrl();
  return base ? `${base}${normalizedPath}` : normalizedPath;
};
