import { motion, AnimatePresence } from 'framer-motion';
import { X, AlertTriangle, Zap, Clock, Wrench, Check, Loader2 } from 'lucide-react';
import { type Device } from '@/data/mockDevices';
import { useResolveFault } from '@/hooks/useFacilityData';
import Sparkline from './Sparkline';

interface DeviceDetailPanelProps {
  device: Device | null;
  onClose: () => void;
}

const statusStyles: Record<string, string> = {
  healthy: 'text-status-healthy',
  warning: 'text-status-warning',
  fault: 'text-status-fault',
  offline: 'text-status-offline',
};

const severityBadge: Record<string, string> = {
  critical: 'bg-status-fault/15 text-status-fault border-status-fault/30',
  high: 'bg-status-warning/15 text-status-warning border-status-warning/30',
  medium: 'bg-status-warning/15 text-status-warning border-status-warning/30',
  low: 'bg-muted text-muted-foreground border-border',
};

export default function DeviceDetailPanel({ device, onClose }: DeviceDetailPanelProps) {
  const { mutate: resolve, pendingFaultId } = useResolveFault();
  return (
    <AnimatePresence>
      {device && (
        <motion.div
          initial={{ x: 360, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 360, opacity: 0 }}
          transition={{ duration: 0.24, ease: [0.2, 0, 0, 1] }}
          className="absolute right-0 top-0 w-[360px] h-full z-30 border-l border-border bg-card overflow-y-auto shadow-xl"
        >
          {/* Header */}
          <div className="px-5 py-4 border-b border-border flex items-start justify-between">
            <div>
              <div className="font-display text-sm tracking-tight">{device.name}</div>
              <div className="text-[11px] text-muted-foreground mt-0.5">{device.id} · {device.model}</div>
            </div>
            <button onClick={onClose} className="p-1 text-muted-foreground hover:text-foreground transition-colors">
              <X size={16} />
            </button>
          </div>

          {/* Status */}
          <div className="px-5 py-3 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${device.status === 'healthy' ? 'bg-status-healthy' : device.status === 'warning' ? 'bg-status-warning' : 'bg-status-fault'}`} />
              <span className={`text-[13px] font-medium capitalize ${statusStyles[device.status]}`}>{device.status}</span>
            </div>
            <div className="text-right">
              <div className="label-caps">Anomaly Score</div>
              <div className={`font-display text-lg ${device.anomalyScore > 0.7 ? 'text-status-fault' : device.anomalyScore > 0.4 ? 'text-status-warning' : 'text-status-healthy'}`}>
                {device.anomalyScore.toFixed(2)}
              </div>
            </div>
          </div>

          {/* Device Meta */}
          <div className="px-5 py-3 border-b border-border grid grid-cols-2 gap-3">
            {[
              { label: 'Serial', value: device.serial },
              { label: 'Type', value: device.type },
              { label: 'Zone', value: device.zone },
              { label: 'Installed', value: device.installedDate },
            ].map(m => (
              <div key={m.label}>
                <div className="label-caps">{m.label}</div>
                <div className="text-[13px] text-secondary-foreground mt-0.5 capitalize">{m.value}</div>
              </div>
            ))}
          </div>

          {/* Telemetry */}
          <div className="px-5 py-4 border-b border-border">
            <div className="label-caps mb-3">Live Telemetry (24h)</div>
            <div className="space-y-4">
              {[
                { label: 'Torque (Nm)', data: device.torque, color: 'hsl(var(--brand))' },
                { label: 'Position (%)', data: device.position, color: 'hsl(var(--foreground))' },
                { label: 'Temperature (°C)', data: device.temperature, color: 'hsl(var(--status-warning))' },
              ].map(t => (
                <div key={t.label} className="flex items-center justify-between">
                  <div>
                    <div className="text-[11px] text-muted-foreground">{t.label}</div>
                    <div className="font-display text-sm mt-0.5">{t.data[t.data.length - 1]?.value.toFixed(1)}</div>
                  </div>
                  <Sparkline data={t.data} color={t.color} />
                </div>
              ))}
            </div>
          </div>

          {/* Faults */}
          {device.faults.length > 0 && (
            <div className="px-5 py-4">
              <div className="label-caps mb-3 flex items-center gap-1.5">
                <AlertTriangle size={10} />
                Active Faults ({device.faults.length})
              </div>
              <div className="space-y-3">
                {device.faults.map(fault => {
                  const isPending = pendingFaultId === fault.id;
                  return (
                    <div key={fault.id} className={`border border-border bg-card p-3 ${isPending ? 'opacity-50' : ''}`}>
                      <div className="text-[13px] font-medium">{fault.type}</div>
                      <span className={`inline-block mt-1.5 px-2 py-0.5 text-[10px] uppercase tracking-wider font-medium border ${severityBadge[fault.severity]}`}>
                        {fault.severity}
                      </span>

                      <div className="text-[12px] leading-relaxed text-muted-foreground mt-2.5">{fault.diagnosis}</div>

                      <div className="border-t border-border pt-2 mt-2.5">
                        <div className="flex items-start gap-1.5 mb-2">
                          <Wrench size={11} className="mt-0.5 shrink-0 text-muted-foreground" />
                          <span className="text-[11px] leading-relaxed text-muted-foreground">{fault.recommendation}</span>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                          <div className="flex items-center gap-3">
                            <span className="flex items-center gap-1"><Zap size={10} />{fault.energyWaste}</span>
                            <span className="flex items-center gap-1"><Clock size={10} />{new Date(fault.detectedAt).toLocaleDateString()}</span>
                          </div>
                          <button
                            disabled={isPending}
                            onClick={() => resolve(fault.id)}
                            className="flex items-center gap-1 px-2 py-1 border border-border text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors text-[11px] disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {isPending ? <Loader2 size={10} className="animate-spin" /> : <Check size={10} />}
                            {isPending ? 'Resolving...' : 'Resolve'}
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {device.faults.length === 0 && (
            <div className="px-5 py-8 text-center">
              <div className="text-status-healthy font-display text-sm">No Active Faults</div>
              <div className="text-[12px] text-muted-foreground mt-1">Device operating within normal parameters</div>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
