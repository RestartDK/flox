import { useEffect, useMemo, useRef, useState } from 'react';
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

interface MentionContext {
  start: number;
  end: number;
  query: string;
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

const extractMentionContext = (value: string, caretPosition: number): MentionContext | null => {
  const beforeCaret = value.slice(0, caretPosition);
  const mentionStart = beforeCaret.lastIndexOf('@');
  if (mentionStart < 0) {
    return null;
  }

  const previousChar = mentionStart > 0 ? beforeCaret[mentionStart - 1] : ' ';
  if (previousChar.trim()) {
    return null;
  }

  const query = beforeCaret.slice(mentionStart + 1);
  if (/\s/.test(query)) {
    return null;
  }

  return {
    start: mentionStart,
    end: caretPosition,
    query,
  };
};

export default function AgentPanel({ devices }: AgentPanelProps) {
  const agentChat = useAgentChat();
  const inputRef = useRef<HTMLInputElement>(null);

  const [messages, setMessages] = useState<ConversationMessage[]>([
    {
      id: nowId(),
      role: 'assistant',
      content:
        'I can investigate faults, explain likely root cause, and execute platform actions after your approval.',
    },
  ]);
  const [input, setInput] = useState('');
  const [caretPosition, setCaretPosition] = useState(0);
  const [mentionCursor, setMentionCursor] = useState(0);
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
      prompts.push(`Run node diagnosis for ${topFault.device.id} now.`);
      prompts.push(`Resolve fault ${topFault.fault.id} with note "validated during demo".`);
    }

    return prompts;
  }, [topFault]);

  const mentionContext = useMemo(
    () => extractMentionContext(input, caretPosition),
    [input, caretPosition],
  );

  const nodeSuggestions = useMemo(() => {
    const unique = new Map<string, { id: string; name: string; status: Device['status'] }>();
    for (const device of devices) {
      unique.set(device.id, {
        id: device.id,
        name: device.name,
        status: device.status,
      });
    }
    return Array.from(unique.values()).sort((a, b) => a.id.localeCompare(b.id));
  }, [devices]);

  const mentionSuggestions = useMemo(() => {
    if (!mentionContext) {
      return [];
    }

    const query = mentionContext.query.trim().toUpperCase();
    const scored = nodeSuggestions
      .filter((node) => {
        if (!query) {
          return true;
        }
        const id = node.id.toUpperCase();
        const name = node.name.toUpperCase();
        return id.includes(query) || name.includes(query);
      })
      .sort((a, b) => {
        const aStarts = a.id.toUpperCase().startsWith(query);
        const bStarts = b.id.toUpperCase().startsWith(query);
        if (aStarts !== bStarts) {
          return aStarts ? -1 : 1;
        }
        return a.id.localeCompare(b.id);
      });

    return scored.slice(0, 6);
  }, [mentionContext, nodeSuggestions]);

  useEffect(() => {
    setMentionCursor(0);
  }, [mentionContext?.start, mentionContext?.query]);

  const applyMention = (nodeId: string) => {
    if (!mentionContext) {
      return;
    }

    const trailing = input.slice(mentionContext.end);
    const needsTrailingSpace = trailing.length === 0 || !trailing.startsWith(' ');
    const inserted = `${input.slice(0, mentionContext.start + 1)}${nodeId}${needsTrailingSpace ? ' ' : ''}${trailing}`;
    const nextCaret = mentionContext.start + 1 + nodeId.length + (needsTrailingSpace ? 1 : 0);

    setInput(inserted);
    setCaretPosition(nextCaret);

    requestAnimationFrame(() => {
      if (!inputRef.current) {
        return;
      }
      inputRef.current.focus();
      inputRef.current.setSelectionRange(nextCaret, nextCaret);
    });
  };

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
    setCaretPosition(0);
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
          ref={inputRef}
          value={input}
          onChange={(event) => {
            setInput(event.target.value);
            setCaretPosition(event.target.selectionStart ?? event.target.value.length);
          }}
          onClick={(event) => {
            setCaretPosition(event.currentTarget.selectionStart ?? event.currentTarget.value.length);
          }}
          onKeyUp={(event) => {
            setCaretPosition(event.currentTarget.selectionStart ?? event.currentTarget.value.length);
          }}
          onKeyDown={(event) => {
            if (!mentionSuggestions.length) {
              return;
            }

            if (event.key === 'ArrowDown') {
              event.preventDefault();
              setMentionCursor((current) => (current + 1) % mentionSuggestions.length);
              return;
            }

            if (event.key === 'ArrowUp') {
              event.preventDefault();
              setMentionCursor((current) =>
                current === 0 ? mentionSuggestions.length - 1 : current - 1,
              );
              return;
            }

            if (event.key === 'Enter') {
              event.preventDefault();
              const selected = mentionSuggestions[mentionCursor] ?? mentionSuggestions[0];
              if (selected) {
                applyMention(selected.id);
              }
            }
          }}
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

      {mentionSuggestions.length > 0 && (
        <div className="mt-2 border border-border bg-card p-2">
          <div className="label-caps mb-1">Node mentions</div>
          <div className="space-y-1">
            {mentionSuggestions.map((node, index) => (
              <button
                key={node.id}
                type="button"
                onMouseDown={(event) => {
                  event.preventDefault();
                  applyMention(node.id);
                }}
                className={`w-full text-left px-2 py-1 text-[12px] transition-colors ${
                  mentionCursor === index ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted'
                }`}
              >
                <span className="font-medium text-foreground">@{node.id}</span>
                <span className="mx-2">-</span>
                <span>{node.name}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
