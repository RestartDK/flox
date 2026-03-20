import { useEffect, useRef, useState } from 'react';
import {
  X,
  Zap,
  Clock,
  Wrench,
  Loader2,
  ChevronDown,
  Activity,
  ExternalLink,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { type Device, type NodeFaultHistoryEntry } from '@/types/facility';
import { buildAgentRouteStateForIssue } from '@/lib/agentNavigation';
import { useNodeFaultHistory } from '@/hooks/useNodeFaultHistory';
import IssueResolveButton from '@/components/IssueResolveButton';
import Sparkline from './Sparkline';

interface DeviceDetailPanelProps {
  device: Device | null;
  mode?: 'pinned' | 'peek';
  onClose: () => void;
}

const statusStyles: Record<string, string> = {
  healthy: 'text-status-healthy',
  warning: 'text-status-warning',
  critical: 'text-status-fault',
  fault: 'text-status-fault',
  offline: 'text-status-offline',
};

const severityBadge: Record<string, string> = {
  critical: 'bg-status-fault/15 text-status-fault border-status-fault/30',
  high: 'bg-status-warning/15 text-status-warning border-status-warning/30',
  medium: 'bg-status-warning/15 text-status-warning border-status-warning/30',
  low: 'bg-muted text-muted-foreground border-border',
};

const formatAnomalyConfidence = (value: number) => `${Math.round(value * 100)}%`;

const historyStateBadge: Record<NodeFaultHistoryEntry['state'], string> = {
  open: 'bg-status-fault/15 text-status-fault border-status-fault/30',
  resolved: 'bg-status-healthy/15 text-status-healthy border-status-healthy/30',
};

const titleCase = (value: string) => value
  .split('_')
  .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
  .join(' ');

const formatTimestamp = (value: string) => {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

export default function DeviceDetailPanel({ device, mode = 'pinned', onClose }: DeviceDetailPanelProps) {
  const isPeek = mode === 'peek';
  const navigate = useNavigate();
  const lastDeviceRef = useRef<Device | null>(null);
  if (device) lastDeviceRef.current = device;
  const displayDevice = device ?? lastDeviceRef.current;
  const isOpen = !!device;
  const historyQuery = useNodeFaultHistory(device?.id ?? null, 10);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const currentDeviceId = device?.id ?? null;

  useEffect(() => {
    setIsHistoryOpen(false);
  }, [currentDeviceId]);

  return (
    <div
      className={`absolute right-0 top-0 z-30 h-full w-[360px] pointer-events-none transition-transform duration-200 ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}
      style={{ transitionTimingFunction: 'cubic-bezier(0.2,0,0,1)' }}
    >
      {displayDevice && (
        <div className={`w-[360px] h-full overflow-y-auto border-l border-border bg-card transition-shadow duration-200 ${
          isPeek ? 'shadow-xl' : 'shadow-none pointer-events-auto'
        }`}>
          <div className={`h-16 shrink-0 flex items-center justify-between border-b border-border px-5 ${isPeek ? '' : 'card-accent-top'}`}>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-display text-base tracking-tight">{displayDevice.name}</span>
                {!isPeek && (
                  <Link
                    to={`/devices/${displayDevice.id}`}
                    className="text-muted-foreground transition-colors hover:text-foreground"
                    title="View full device details"
                  >
                    <ExternalLink size={12} />
                  </Link>
                )}
              </div>
              <div className="text-[11px] text-muted-foreground">{displayDevice.id}</div>
            </div>
            {!isPeek && (
              <button onClick={onClose} className="p-1 text-muted-foreground transition-colors hover:text-foreground">
                <X size={16} />
              </button>
            )}
          </div>

          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 rounded-full ${displayDevice.status === 'healthy' ? 'bg-status-healthy' : displayDevice.status === 'warning' ? 'bg-status-warning' : 'bg-status-fault'}`} />
              <span className={`text-[13px] font-medium capitalize ${statusStyles[displayDevice.status]}`}>{displayDevice.status}</span>
            </div>
            <div className="text-right">
              <div className="label-caps">Confidence</div>
              <div className={`font-display text-lg ${displayDevice.anomalyScore > 0.7 ? 'text-status-fault' : displayDevice.anomalyScore > 0.4 ? 'text-status-warning' : 'text-status-healthy'}`}>
                {formatAnomalyConfidence(displayDevice.anomalyScore)}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 border-b border-border px-5 py-3">
            <div className="border border-border bg-background/60 px-3 py-2">
              <div className="label-caps">Faults Recorded</div>
              <div className="mt-1 font-display text-lg">{historyQuery.data?.totalFaults ?? '--'}</div>
              <div className="text-[11px] text-muted-foreground">Historical incidents</div>
            </div>
            <div className="border border-border bg-background/60 px-3 py-2">
              <div className="label-caps">Open Faults</div>
              <div className={`mt-1 font-display text-lg ${displayDevice.faults.length > 0 ? 'text-status-fault' : 'text-status-healthy'}`}>
                {historyQuery.data?.openFaults ?? displayDevice.faults.length}
              </div>
              <div className="text-[11px] text-muted-foreground">Active on this device</div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 border-b border-border px-5 py-3">
            {[
              { label: 'Zone', value: displayDevice.zone },
              { label: 'Type', value: displayDevice.type },
              { label: 'Model', value: displayDevice.model },
              { label: 'Serial', value: displayDevice.serial },
              { label: 'Installed', value: displayDevice.installedDate },
            ].map((meta) => (
              <div key={meta.label}>
                <div className="label-caps">{meta.label}</div>
                <div className="mt-0.5 text-[13px] capitalize text-secondary-foreground">{meta.value}</div>
              </div>
            ))}
          </div>

          <div className="border-b border-border px-5 py-4">
            <div className="label-caps mb-3">Live Telemetry (24h)</div>
            <div className="space-y-4">
              {[
                { label: 'Torque (Nm)', data: displayDevice.torque, color: 'hsl(var(--brand))' },
                { label: 'Position (%)', data: displayDevice.position, color: 'hsl(var(--foreground))' },
                { label: 'Temperature (°C)', data: displayDevice.temperature, color: 'hsl(var(--status-warning))' },
              ].map((telemetry) => (
                <div key={telemetry.label} className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] text-muted-foreground">{telemetry.label}</div>
                    <div className="mt-0.5 font-display text-sm">{telemetry.data[telemetry.data.length - 1]?.value.toFixed(1) ?? '--'}</div>
                  </div>
                  <Sparkline data={telemetry.data} color={telemetry.color} />
                </div>
              ))}
            </div>
          </div>

          {isPeek && (
            <div className="px-5 py-3 text-[11px] text-muted-foreground text-center border-t border-border">
              Click device to view full details
            </div>
          )}

          {!isPeek && (
            <>
              {displayDevice.faults.length > 0 && (
                <div className="border-b border-border px-5 py-4">
                  <div className="label-caps mb-3">Active Faults ({displayDevice.faults.length})</div>
                  <div className="space-y-3">
                    {displayDevice.faults.map((fault) => {
                      return (
                        <div key={fault.id} className="border border-border bg-card p-3 fault-card-accent">
                          <div className="text-[13px] font-medium">{fault.type}</div>
                          <span className={`mt-1.5 inline-block border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${severityBadge[fault.severity]}`}>
                            {fault.severity}
                          </span>

                          <div className="mt-2.5 text-[12px] leading-relaxed text-muted-foreground">{fault.diagnosis}</div>

                          <div className="mt-2.5 border-t border-border pt-2">
                            <div className="mb-2 flex items-start gap-1.5">
                              <Wrench size={11} className="mt-0.5 shrink-0 text-muted-foreground" />
                              <span className="text-[11px] leading-relaxed text-muted-foreground">{fault.recommendation}</span>
                            </div>
                            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                              <div className="flex items-center gap-3">
                                <span className="flex items-center gap-1"><Zap size={10} />{fault.energyWaste}</span>
                                <span className="flex items-center gap-1"><Clock size={10} />{new Date(fault.detectedAt).toLocaleDateString()}</span>
                              </div>
                              <IssueResolveButton
                                onClick={() => navigate('/agent', {
                                  state: buildAgentRouteStateForIssue({ device: displayDevice, fault }),
                                })}
                              />
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <Link
                    to={`/devices/${displayDevice.id}`}
                    className="mt-3 inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors border border-border px-2 py-1"
                  >
                    <ExternalLink size={10} />View all fault details
                  </Link>
                </div>
              )}

              {displayDevice.faults.length === 0 && (
                <div className="border-b border-border px-5 py-8 text-center">
                  <div className="font-display text-sm text-status-healthy">No Active Faults</div>
                  <div className="mt-1 text-[12px] text-muted-foreground">Device operating within normal parameters</div>
                </div>
              )}

              <div className="border-b border-border px-5 py-4">
                <button
                  type="button"
                  onClick={() => setIsHistoryOpen((open) => !open)}
                  className="flex w-full items-center justify-between gap-3 text-left"
                >
                  <div>
                    <div className="label-caps">Fault History</div>
                    <div className="mt-1 text-[12px] text-muted-foreground">
                      {historyQuery.data ? `${historyQuery.data.totalFaults} recorded incidents for this device` : 'Open and resolved backend incidents'}
                    </div>
                  </div>
                  <ChevronDown
                    size={16}
                    className={`shrink-0 text-muted-foreground transition-transform ${isHistoryOpen ? 'rotate-180' : ''}`}
                  />
                </button>

                {isHistoryOpen && (
                  <div className="mt-3 space-y-2">
                    {historyQuery.isLoading && (
                      <div className="inline-flex items-center gap-2 text-[12px] text-muted-foreground">
                        <Loader2 size={12} className="animate-spin" />
                        Loading history...
                      </div>
                    )}

                    {historyQuery.error instanceof Error && (
                      <div className="text-[12px] text-status-fault">
                        Could not load history ({historyQuery.error.message})
                      </div>
                    )}

                    {historyQuery.data?.faultHistory.length === 0 && (
                      <div className="text-[12px] text-muted-foreground">
                        No historical incidents recorded for this device yet.
                      </div>
                    )}

                    {historyQuery.data?.faultHistory.map((fault) => (
                      <div key={fault.id} className="border border-border bg-background/60 p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="text-[12px] font-medium text-foreground">{titleCase(fault.kind)}</div>
                            <div className="mt-1 text-[11px] text-muted-foreground">{fault.id}</div>
                          </div>
                          <span className={`inline-block border px-2 py-0.5 text-[10px] uppercase tracking-wider ${historyStateBadge[fault.state]}`}>
                            {fault.state}
                          </span>
                        </div>

                        <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
                          <span className="inline-flex items-center gap-1">
                            <Activity size={11} />
                            Likelihood {(fault.probability * 100).toFixed(0)}%
                          </span>
                          <span className="inline-flex items-center gap-1">
                            <Clock size={11} />
                            Opened {formatTimestamp(fault.openedAt)}
                          </span>
                        </div>

                        <div className="mt-2 text-[12px] leading-relaxed text-foreground/90">{fault.summary}</div>
                        <div className="mt-2 inline-flex items-start gap-1 text-[11px] text-muted-foreground">
                          <Wrench size={11} className="mt-0.5 shrink-0" />
                          {fault.recommendedAction}
                        </div>

                        {fault.state === 'resolved' && (fault.resolvedBy || fault.note) && (
                          <div className="mt-2 border-t border-border pt-2 text-[11px] text-muted-foreground">
                            {fault.resolvedBy && <div>Resolved by {fault.resolvedBy}</div>}
                            {fault.note && <div className="mt-1">{fault.note}</div>}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          </div>
      )}
    </div>
  );
}
