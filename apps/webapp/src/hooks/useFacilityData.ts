import { useQuery } from '@tanstack/react-query';
import {
  type FacilityStatusResponse,
} from '@/data/mockDevices';

const DEFAULT_PRODUCTION_BACKEND_URL = 'https://starthack26-backend-production.up.railway.app';

const getStatusUrl = () => {
  const baseUrl = import.meta.env.VITE_BACKEND_URL?.replace(/\/$/, '');
  if (baseUrl) {
    return `${baseUrl}/api/status`;
  }

  if (import.meta.env.PROD) {
    return `${DEFAULT_PRODUCTION_BACKEND_URL}/api/status`;
  }

  return '/api/status';
};

const fetchFacilityStatus = async (): Promise<FacilityStatusResponse> => {
  const response = await fetch(getStatusUrl(), {
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
