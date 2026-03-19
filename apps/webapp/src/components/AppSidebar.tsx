import { type BuildingStats } from '@/data/mockDevices';
import { AlertTriangle, Bot, Map, type LucideIcon } from 'lucide-react';

interface AppSidebarProps {
  activeView: 'map' | 'alerts' | 'agent';
  onViewChange: (view: 'map' | 'alerts' | 'agent') => void;
  buildingStats: BuildingStats;
}

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

export default function AppSidebar({ activeView, onViewChange, buildingStats }: AppSidebarProps) {
  return (
    <aside className="w-[260px] h-screen bg-sidebar border-r border-sidebar-border flex flex-col shrink-0">
      {/* Header */}
      <div className="px-4 py-5 border-b border-sidebar-border">
        <div className="font-display text-sm tracking-tight text-foreground flex items-center gap-2">
          <img src="/favicon.svg" alt="" className="w-5 h-5 shrink-0" aria-hidden />
          Flox
        </div>
      </div>

      {/* Navigation */}
      <div className="py-2 border-b border-sidebar-border">
        <NavItem icon={Map} label="Facility Map" active={activeView === 'map'} onClick={() => onViewChange('map')} />
        <NavItem icon={AlertTriangle} label="Alert Dashboard" active={activeView === 'alerts'} onClick={() => onViewChange('alerts')} />
        <NavItem icon={Bot} label="Operations Agent" active={activeView === 'agent'} onClick={() => onViewChange('agent')} />
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

    </aside>
  );
}
