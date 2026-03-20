import {
  DEFAULT_PRODUCTION_BACKEND_URL,
  resolveBackendBaseUrl,
} from './backendConfig';

const getRuntimeEnv = (): Record<string, string | boolean | undefined> => {
  const withEnv = import.meta as ImportMeta & {
    env?: Record<string, string | boolean | undefined>;
  };
  return withEnv.env ?? {};
};

export const getBackendBaseUrl = () => {
  const env = getRuntimeEnv();
  return (
    resolveBackendBaseUrl({
      explicitUrl: typeof env.VITE_BACKEND_URL === 'string' ? env.VITE_BACKEND_URL : undefined,
      isProduction: Boolean(env.PROD),
    }) ?? DEFAULT_PRODUCTION_BACKEND_URL
  );
};

export const buildBackendUrl = (path: string) => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const base = getBackendBaseUrl();
  return base ? `${base}${normalizedPath}` : normalizedPath;
};
