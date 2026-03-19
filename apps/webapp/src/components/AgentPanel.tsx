import { useMemo, useState } from 'react';
import { Bot, Check, Loader2, Send, ShieldAlert, X } from 'lucide-react';
import { type AgentChatMessage, type AgentToolEvent, type AgentPendingAction, type Device } from '@/data/mockDevices';
import { useAgentChat } from '@/hooks/useAgentChat';

interface AgentPanelProps {
  devices: Device[];
}

interface ConversationMessage {
  id: string;
  role: AgentChatMessage['role'];
  content: string;
}

const severityWeight: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

const toPayloadMessages = (messages: ConversationMessage[]): AgentChatMessage[] =>
  messages.map((message) => ({
    role: message.role,
    content: message.content,
  }));

const nowId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

export default function AgentPanel({ devices }: AgentPanelProps) {
  const agentChat = useAgentChat();

  const [messages, setMessages] = useState<ConversationMessage[]>([
    {
      id: nowId(),
      role: 'assistant',
      content:
        'I can investigate faults, explain likely root cause, and execute platform actions after your approval.',
    },
  ]);
  const [input, setInput] = useState('');
  const [pendingAction, setPendingAction] = useState<AgentPendingAction | null>(null);
  const [latestToolEvents, setLatestToolEvents] = useState<AgentToolEvent[]>([]);

  const topFault = useMemo(() => {
    const faultEntries = devices
      .flatMap((device) =>
        device.faults.map((fault) => ({
          device,
          fault,
        })),
      )
      .sort((a, b) => severityWeight[a.fault.severity] - severityWeight[b.fault.severity]);
    return faultEntries[0] ?? null;
  }, [devices]);

  const quickPrompts = useMemo(() => {
    const prompts = ['Give me a live system overview and top active faults.'];

    if (topFault) {
      prompts.push(`Why is node ${topFault.device.id} reporting ${topFault.fault.type}?`);
      prompts.push(`Show fault history for node ${topFault.device.id}.`);
      prompts.push(`Resolve fault ${topFault.fault.id} with note "validated during demo".`);
    }

    return prompts;
  }, [topFault]);

  const sendPrompt = (text: string) => {
    const prompt = text.trim();
    if (!prompt || agentChat.isPending) {
      return;
    }

    const userMessage: ConversationMessage = {
      id: nowId(),
      role: 'user',
      content: prompt,
    };

    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setInput('');
    setPendingAction(null);

    agentChat.mutate(
      {
        messages: toPayloadMessages(nextMessages),
        actor: 'facility-manager',
      },
      {
        onSuccess: (response) => {
          setMessages((current) => [
            ...current,
            {
              id: nowId(),
              role: 'assistant',
              content: response.reply,
            },
          ]);
          setPendingAction(response.pendingAction);
          setLatestToolEvents(response.toolEvents);
        },
        onError: (error) => {
          const message = error instanceof Error ? error.message : 'Unknown error';
          setMessages((current) => [
            ...current,
            {
              id: nowId(),
              role: 'assistant',
              content: `I could not reach the backend agent (${message}).`,
            },
          ]);
          setPendingAction(null);
          setLatestToolEvents([]);
        },
      },
    );
  };

  const decidePendingAction = (decision: 'approve' | 'reject') => {
    if (!pendingAction || agentChat.isPending) {
      return;
    }

    agentChat.mutate(
      {
        messages: toPayloadMessages(messages),
        actor: 'facility-manager',
        pendingActionId: pendingAction.id,
        pendingActionDecision: decision,
      },
      {
        onSuccess: (response) => {
          setMessages((current) => [
            ...current,
            {
              id: nowId(),
              role: 'assistant',
              content: response.reply,
            },
          ]);
          setPendingAction(response.pendingAction);
          setLatestToolEvents(response.toolEvents);
        },
        onError: (error) => {
          const message = error instanceof Error ? error.message : 'Unknown error';
          setMessages((current) => [
            ...current,
            {
              id: nowId(),
              role: 'assistant',
              content: `Action decision failed (${message}).`,
            },
          ]);
        },
      },
    );
  };

  return (
    <div className="flex-1 p-6 overflow-hidden flex flex-col">
      <div className="mb-4">
        <h1 className="font-display text-lg tracking-tight">Operations Agent</h1>
        <p className="text-[13px] text-muted-foreground mt-0.5">
          Ask for diagnosis, fault history, and approved state-changing actions.
        </p>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {quickPrompts.map((prompt) => (
          <button
            key={prompt}
            onClick={() => sendPrompt(prompt)}
            disabled={agentChat.isPending}
            className="border border-border bg-card px-3 py-1.5 text-[12px] text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
          >
            {prompt}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0 border border-border bg-card p-4 overflow-y-auto space-y-3">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`max-w-[80%] px-3 py-2 text-[13px] leading-relaxed ${
              message.role === 'user'
                ? 'ml-auto bg-secondary text-secondary-foreground'
                : 'bg-muted text-foreground'
            }`}
          >
            <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
              {message.role === 'assistant' ? <Bot size={11} /> : <Send size={11} />}
              {message.role}
            </div>
            <div>{message.content}</div>
          </div>
        ))}

        {agentChat.isPending && (
          <div className="inline-flex items-center gap-2 px-3 py-2 text-[12px] bg-muted text-muted-foreground">
            <Loader2 size={13} className="animate-spin" />
            Agent working...
          </div>
        )}
      </div>

      {latestToolEvents.length > 0 && (
        <div className="mt-3 border border-border bg-card p-3">
          <div className="label-caps mb-2">Latest tool activity</div>
          <div className="space-y-1.5">
            {latestToolEvents.map((event, index) => (
              <div key={`${event.name}-${index}`} className="text-[12px] text-muted-foreground">
                <span className="font-medium text-foreground">{event.name}</span>
                <span className="mx-1">-</span>
                <span className="capitalize">{event.outcome.replace('_', ' ')}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {pendingAction && (
        <div className="mt-3 border border-status-warning/40 bg-status-warning/10 p-3">
          <div className="flex items-center gap-2 text-status-warning text-[12px] uppercase tracking-wider font-medium">
            <ShieldAlert size={14} />
            Approval required
          </div>
          <div className="mt-1 text-[13px] text-foreground">{pendingAction.summary}</div>
          <div className="mt-3 flex items-center gap-2">
            <button
              onClick={() => decidePendingAction('approve')}
              disabled={agentChat.isPending}
              className="inline-flex items-center gap-1.5 border border-status-healthy/40 bg-status-healthy/15 px-3 py-1.5 text-[12px] text-status-healthy disabled:opacity-50"
            >
              <Check size={12} />
              Approve
            </button>
            <button
              onClick={() => decidePendingAction('reject')}
              disabled={agentChat.isPending}
              className="inline-flex items-center gap-1.5 border border-status-fault/40 bg-status-fault/15 px-3 py-1.5 text-[12px] text-status-fault disabled:opacity-50"
            >
              <X size={12} />
              Reject
            </button>
          </div>
        </div>
      )}

      <form
        className="mt-4 border border-border bg-card p-3 flex items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          sendPrompt(input);
        }}
      >
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          className="flex-1 bg-transparent text-[13px] outline-none"
          placeholder="Ask why a fault happened, request history, or ask to run an action"
        />
        <button
          type="submit"
          disabled={agentChat.isPending || !input.trim()}
          className="inline-flex items-center gap-1.5 border border-border px-3 py-1.5 text-[12px] hover:border-foreground transition-colors disabled:opacity-50"
        >
          <Send size={12} />
          Send
        </button>
      </form>
    </div>
  );
}
