import { useQuery } from '@tanstack/react-query';
import { type NodeFaultHistoryResponse } from '@/data/mockDevices';
import { resolveBackendBaseUrl } from '@/lib/backendConfig';

const getNodeFaultHistoryUrl = (nodeId: string, limit: number) => {
  const path = `/api/nodes/${encodeURIComponent(nodeId)}/fault-history?limit=${limit}`;
  const baseUrl = resolveBackendBaseUrl({
    explicitUrl: import.meta.env.VITE_BACKEND_URL,
    isProduction: import.meta.env.PROD,
  });

  if (!baseUrl) {
    return path;
  }

  return `${baseUrl}${path}`;
};

const fetchNodeFaultHistory = async (
  nodeId: string,
  limit: number,
): Promise<NodeFaultHistoryResponse> => {
  const response = await fetch(getNodeFaultHistoryUrl(nodeId, limit), {
    cache: 'no-store',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch node fault history: ${response.status}`);
  }

  return response.json();
};

export const useNodeFaultHistory = (nodeId: string | null, limit = 25) => {
  return useQuery<NodeFaultHistoryResponse>({
    queryKey: ['node-fault-history', nodeId, limit],
    queryFn: () => fetchNodeFaultHistory(nodeId as string, limit),
    enabled: Boolean(nodeId),
    refetchInterval: 10000,
    refetchIntervalInBackground: true,
  });
};
