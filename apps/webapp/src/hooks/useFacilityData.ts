import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ahuUnits,
  buildBuildingStats,
  buildDevicesFromNodes,
  initialFacilityNodesResponse,
  type FacilityNodesResponse,
} from '@/data/mockDevices';

const fetchFacilityNodes = async (): Promise<FacilityNodesResponse> => {
  const response = await fetch('/mock/nodes.json', {
    cache: 'no-store',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch facility nodes: ${response.status}`);
  }

  return response.json();
};

export const useFacilityData = () => {
  const query = useQuery({
    queryKey: ['facility-nodes'],
    queryFn: fetchFacilityNodes,
    initialData: initialFacilityNodesResponse,
    refetchInterval: 5000,
    refetchIntervalInBackground: true,
  });

  const devices = useMemo(() => buildDevicesFromNodes(query.data), [query.data]);
  const buildingStats = useMemo(() => buildBuildingStats(devices), [devices]);
  const nodePositions = useMemo(
    () => Object.fromEntries(query.data.nodes.map(n => [n.id, n.position])),
    [query.data],
  );

  return {
    ...query,
    ahuUnits,
    buildingStats,
    devices,
    nodePositions,
    generatedAt: query.data.generatedAt,
  };
};
