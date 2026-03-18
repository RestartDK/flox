import { buildingStats } from '@/data/mockDevices';
import { Activity, AlertTriangle, Map, type LucideIcon } from 'lucide-react';

interface AppSidebarProps {
  activeView: 'map' | 'alerts';
  onViewChange: (view: 'map' | 'alerts') => void;
}

const StatBlock = ({ label, value, accent }: { label: string; value: string | number; accent?: boolean }) => (
  <div className="px-4 py-3">
    <div className="label-caps mb-1">{label}</div>
    <div className={`font-display text-xl tracking-tight ${accent ? 'text-accent' : 'text-foreground'}`}>
      {value}
    </div>
  </div>
);

const NavItem = ({ icon: Icon, label, active, onClick }: { icon: LucideIcon; label: string; active: boolean; onClick: () => void }) => (
  <button
    onClick={onClick}
    className={`w-full flex items-center gap-3 px-4 py-2.5 text-[13px] font-medium transition-colors ${
      active ? 'bg-sidebar-accent text-sidebar-accent-foreground' : 'text-sidebar-foreground hover:text-sidebar-accent-foreground'
    }`}
  >
    <Icon size={16} strokeWidth={1.5} />
    {label}
  </button>
);

export default function AppSidebar({ activeView, onViewChange }: AppSidebarProps) {
  return (
    <aside className="w-[260px] h-screen bg-sidebar border-r border-sidebar-border flex flex-col shrink-0">
      {/* Header */}
      <div className="px-4 py-5 border-b border-sidebar-border">
        <div className="font-display text-sm tracking-tight text-foreground flex items-center gap-2">
          <Activity size={16} className="text-accent" />
          VAULT / HVAC
        </div>
        <div className="text-[11px] text-muted-foreground mt-1">Belimo Observability Platform</div>
      </div>

      {/* Navigation */}
      <div className="py-2 border-b border-sidebar-border">
        <NavItem icon={Map} label="Facility Map" active={activeView === 'map'} onClick={() => onViewChange('map')} />
        <NavItem icon={AlertTriangle} label="Alert Dashboard" active={activeView === 'alerts'} onClick={() => onViewChange('alerts')} />
      </div>

      {/* Building Health */}
      <div className="py-2 border-b border-sidebar-border">
        <div className="label-caps px-4 py-2">Building Health</div>
        <StatBlock label="Overall Score" value={`${buildingStats.overallHealth}%`} accent />
        <StatBlock label="Active Faults" value={buildingStats.activeFaults} />
        <StatBlock label="Energy Waste" value={buildingStats.energyWaste} />
        <StatBlock label="Est. Daily Cost" value={buildingStats.estimatedCost} />
      </div>

      {/* Device Summary */}
      <div className="py-2 flex-1">
        <div className="label-caps px-4 py-2">Device Status</div>
        <div className="px-4 space-y-2 mt-1">
          {[
            { label: 'Healthy', count: buildingStats.healthyDevices, color: 'bg-status-healthy' },
            { label: 'Warning', count: buildingStats.warningDevices, color: 'bg-status-warning' },
            { label: 'Fault', count: buildingStats.faultDevices, color: 'bg-status-fault' },
          ].map(s => (
            <div key={s.label} className="flex items-center gap-2 text-[13px] text-secondary-foreground">
              <span className={`w-2 h-2 rounded-full ${s.color}`} />
              <span className="flex-1">{s.label}</span>
              <span className="font-display">{s.count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-sidebar-border text-[11px] text-muted-foreground">
        v1.0 — March 2026
      </div>
    </aside>
  );
}
