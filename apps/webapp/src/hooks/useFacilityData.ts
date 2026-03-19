import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { type FacilityStatusResponse } from '@/types/facility';
import { buildBackendUrl } from '@/lib/backend';

const BACKEND_TIMEOUT_MS = 8000;

const fetchWithTimeout = async (input: string, init?: RequestInit) => {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), BACKEND_TIMEOUT_MS);

  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(`Backend request timed out after ${BACKEND_TIMEOUT_MS / 1000}s: ${input}`);
    }

    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
};

const fetchFacilityStatus = async (): Promise<FacilityStatusResponse> => {
  const url = buildBackendUrl('/api/status');
  const response = await fetchWithTimeout(url, {
    cache: 'no-store',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch facility status: ${response.status}`);
  }

  return response.json();
};

export const useFacilityData = () => {
  const query = useQuery<FacilityStatusResponse>({
    queryKey: ['facility-status'],
    queryFn: fetchFacilityStatus,
    refetchInterval: 5000,
    refetchIntervalInBackground: true,
  });

  const data = query.data;

  return {
    ...query,
    ahuUnits: data?.catalog.ahuUnits ?? [],
    buildingStats: data?.derived.buildingStats ?? null,
    devices: data?.derived.devices ?? [],
    nodePositions: data?.derived.nodePositions ?? {},
    generatedAt: data?.generatedAt ?? null,
    catalog: data?.catalog ?? null,
    historyByNodeId: data?.historyByNodeId ?? {},
    meta: data?.meta ?? null,
  };
};

export const useResolveFault = () => {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (faultId: string) =>
      fetchWithTimeout(buildBackendUrl(`/api/faults/${encodeURIComponent(faultId)}/resolve`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolvedBy: 'operator' }),
      }).then(r => {
        if (!r.ok) {
          throw new Error(`Failed to resolve fault: ${r.status}`);
        }

        return r.json();
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['facility-status'] }),
        queryClient.invalidateQueries({ queryKey: ['node-fault-history'] }),
      ]);
    },
  });

  return {
    ...mutation,
    /** The fault id currently being resolved, or null when idle. */
    pendingFaultId: mutation.isPending ? (mutation.variables ?? null) : null,
  };
};
