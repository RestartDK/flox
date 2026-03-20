import {
  DEFAULT_DEV_BACKEND_PORT,
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
  const configured = typeof env.VITE_BACKEND_URL === 'string' ? env.VITE_BACKEND_URL : undefined;
  const resolved = resolveBackendBaseUrl({
    explicitUrl: configured,
    isProduction: Boolean(env.PROD),
  });
  if (resolved) {
        console.log(`Using backend URL: ${resolved}`);
        return resolved;
    }
    console.warn('No backend URL configured, defaulting to localhost');

  return `http://127.0.0.1:${DEFAULT_DEV_BACKEND_PORT}`;
};

export const buildBackendUrl = (path: string) => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const base = getBackendBaseUrl();
  return base ? `${base}${normalizedPath}` : normalizedPath;
};
