import { useMutation } from '@tanstack/react-query';
import { buildBackendUrl } from '@/lib/backend';
import type { SimulationRunRequest, SimulationRunResponse, BayesianView } from '@/types/facility';

const runSimulation = async (payload: SimulationRunRequest): Promise<SimulationRunResponse> => {
  const response = await fetch(buildBackendUrl('/api/simulation/run'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Failed to run simulation: ${response.status}`);
  }

  return response.json();
};

const fetchBayesianCurrent = async (): Promise<BayesianView> => {
  const response = await fetch(buildBackendUrl('/api/bayesian/current'), {
    cache: 'no-store',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch bayesian graph: ${response.status}`);
  }

  return response.json();
};

export const useSimulationRun = () => {
  return useMutation({
    mutationFn: runSimulation,
  });
};

export const getBayesianCurrent = fetchBayesianCurrent;
