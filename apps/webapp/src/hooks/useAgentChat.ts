import { useMutation, useQueryClient } from '@tanstack/react-query';
import { type AgentChatRequest, type AgentChatResponse } from '@/data/mockDevices';
import { buildBackendUrl } from '@/lib/backend';

const postAgentChat = async (payload: AgentChatRequest): Promise<AgentChatResponse> => {
  const response = await fetch(buildBackendUrl('/api/agent/chat'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Agent request failed: ${response.status}`);
  }

  return response.json();
};

export const useAgentChat = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: postAgentChat,
    onSuccess: (result) => {
      const hasStateMutation = result.toolEvents.some(
        (event) => event.outcome === 'executed' && ['resolve_fault', 'run_diagnosis_cycle_now'].includes(event.name),
      );

      if (hasStateMutation) {
        queryClient.invalidateQueries({ queryKey: ['facility-status'] });
      }
    },
  });
};
