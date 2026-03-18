import { useRef, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { useGesture } from '@use-gesture/react';
import { ZoomIn, ZoomOut, Maximize } from 'lucide-react';
import { devices, ahuUnits, type Device } from '@/data/mockDevices';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

interface FacilityMapProps {
  onDeviceSelect: (device: Device) => void;
  selectedDeviceId: string | null;
}

const statusColor: Record<string, string> = {
  healthy: 'var(--status-healthy)',
  warning: 'var(--status-warning)',
  fault: 'var(--status-fault)',
  offline: 'var(--status-offline)',
};

const deviceIcon: Record<string, string> = {
  actuator: 'A',
  damper: 'D',
  valve: 'V',
};

const DeviceNode = ({ device, selected, onClick }: { device: Device; selected: boolean; onClick: () => void }) => {
  const color = `hsl(${statusColor[device.status]})`;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <motion.g
          onClick={onClick}
          className="cursor-pointer"
          whileHover={{ scale: 1.15 }}
          transition={{ duration: 0.12, ease: [0.2, 0, 0, 1] }}
        >
          {device.status === 'fault' && (
            <circle cx={device.x} cy={device.y} r={18} fill="none" stroke={color} strokeWidth={1} opacity={0.4} className="animate-pulse-glow" />
          )}
          {selected && (
            <circle cx={device.x} cy={device.y} r={16} fill="none" stroke="hsl(var(--foreground))" strokeWidth={1.5} />
          )}
          <circle cx={device.x} cy={device.y} r={12} fill={`hsl(${statusColor[device.status]} / 0.15)`} stroke={color} strokeWidth={1.5} />
          <text x={device.x} y={device.y + 1} textAnchor="middle" dominantBaseline="middle" fill={color} fontSize={9} fontWeight={600} fontFamily="var(--font-display)">
            {deviceIcon[device.type]}
          </text>
        </motion.g>
      </TooltipTrigger>
      <TooltipContent side="top" className="bg-popover border-border text-popover-foreground p-0">
        <div className="px-3 py-2">
          <div className="text-[12px] font-medium">{device.name}</div>
          <div className="text-[11px] text-muted-foreground">{device.id} · {device.zone}</div>
          <div className="flex items-center gap-1.5 mt-1">
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-[11px] capitalize">{device.status}</span>
            <span className="text-[11px] text-muted-foreground ml-1">Score: {device.anomalyScore.toFixed(2)}</span>
          </div>
        </div>
      </TooltipContent>
    </Tooltip>
  );
};

// Ductwork connections from AHUs to devices
const Ductwork = () => (
  <g stroke="hsl(var(--accent) / 0.4)" strokeWidth={1.5} fill="none" strokeDasharray="6 3">
    {/* AHU-01 (310,240) → Kitchen devices */}
    <path d="M 310 240 L 240 240 L 240 210 L 160 210" />
    <path d="M 310 240 L 200 240 L 200 100 L 80 100" />
    {/* AHU-01 → Living Room devices */}
    <path d="M 310 240 L 420 240 L 420 100 L 550 100" />
    <path d="M 310 240 L 500 240 L 500 200 L 700 200" />
    {/* AHU-01 → AHU-02 trunk */}
    <path d="M 310 260 L 310 370 L 460 370" />
    {/* AHU-02 (460,370) → Bathroom */}
    <path d="M 460 370 L 200 370 L 200 380 L 100 380" />
    {/* AHU-02 → Bedroom 1 */}
    <path d="M 460 370 L 580 370 L 580 450 L 700 450" />
    <path d="M 460 370 L 580 370 L 580 550 L 750 550" />
    {/* AHU-02 → Bedroom 2 */}
    <path d="M 460 390 L 460 520 L 350 520" />
  </g>
);

// The floor plan SVG extracted from the uploaded HTML, with all text removed
const FloorPlanBase = () => (
  <g>
    {/* Wall pattern */}
    <defs>
      <pattern id="wallHatch" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
        <line x1="0" y1="0" x2="0" y2="6" stroke="hsl(var(--muted-foreground))" strokeWidth="0.5" opacity="0.15" />
      </pattern>
    </defs>

    {/* Outer walls */}
    <rect x="20" y="20" width="780" height="580" fill="none" stroke="hsl(var(--foreground) / 0.6)" strokeWidth="10" rx="2" />

    {/* Inner walls */}
    <rect x="300" y="20" width="8" height="200" fill="hsl(var(--foreground) / 0.5)" />
    <rect x="20" y="280" width="220" height="8" fill="hsl(var(--foreground) / 0.5)" />
    <rect x="170" y="280" width="8" height="190" fill="hsl(var(--foreground) / 0.5)" />
    <rect x="430" y="320" width="370" height="8" fill="hsl(var(--foreground) / 0.5)" />
    <rect x="580" y="320" width="8" height="280" fill="hsl(var(--foreground) / 0.5)" />
    <rect x="178" y="400" width="252" height="8" fill="hsl(var(--foreground) / 0.5)" />
    <rect x="178" y="400" width="8" height="70" fill="hsl(var(--foreground) / 0.5)" />

    {/* Doors */}
    <g>
      <line x1="20" y1="500" x2="20" y2="560" stroke="hsl(var(--accent))" strokeWidth="3" />
      <path d="M 20 500 Q 55 500, 55 530" fill="none" stroke="hsl(var(--accent))" strokeWidth="1.5" strokeDasharray="3,2" />
    </g>
    <g>
      <line x1="100" y1="280" x2="150" y2="280" stroke="hsl(var(--card))" strokeWidth="10" />
      <line x1="100" y1="280" x2="150" y2="280" stroke="hsl(var(--muted-foreground) / 0.5)" strokeWidth="1.5" />
      <path d="M 100 280 Q 100 318, 130 318" fill="none" stroke="hsl(var(--muted-foreground) / 0.5)" strokeWidth="1" strokeDasharray="3,2" />
    </g>
    <g>
      <line x1="470" y1="320" x2="530" y2="320" stroke="hsl(var(--card))" strokeWidth="10" />
      <line x1="470" y1="320" x2="530" y2="320" stroke="hsl(var(--muted-foreground) / 0.5)" strokeWidth="1.5" />
      <path d="M 470 320 Q 470 358, 500 358" fill="none" stroke="hsl(var(--muted-foreground) / 0.5)" strokeWidth="1" strokeDasharray="3,2" />
    </g>
    <g>
      <line x1="620" y1="320" x2="680" y2="320" stroke="hsl(var(--card))" strokeWidth="10" />
      <line x1="620" y1="320" x2="680" y2="320" stroke="hsl(var(--muted-foreground) / 0.5)" strokeWidth="1.5" />
      <path d="M 680 320 Q 680 358, 650 358" fill="none" stroke="hsl(var(--muted-foreground) / 0.5)" strokeWidth="1" strokeDasharray="3,2" />
    </g>
    <g>
      <line x1="300" y1="120" x2="300" y2="190" stroke="hsl(var(--card))" strokeWidth="10" />
      <line x1="300" y1="120" x2="300" y2="190" stroke="hsl(var(--muted-foreground) / 0.5)" strokeWidth="1.5" />
    </g>

    {/* Windows */}
    <g>
      <line x1="420" y1="20" x2="560" y2="20" stroke="hsl(var(--accent) / 0.6)" strokeWidth="5" />
      <line x1="420" y1="17" x2="560" y2="17" stroke="hsl(var(--accent) / 0.3)" strokeWidth="1" />
      <line x1="420" y1="23" x2="560" y2="23" stroke="hsl(var(--accent) / 0.3)" strokeWidth="1" />
    </g>
    <g>
      <line x1="640" y1="20" x2="760" y2="20" stroke="hsl(var(--accent) / 0.6)" strokeWidth="5" />
      <line x1="640" y1="17" x2="760" y2="17" stroke="hsl(var(--accent) / 0.3)" strokeWidth="1" />
      <line x1="640" y1="23" x2="760" y2="23" stroke="hsl(var(--accent) / 0.3)" strokeWidth="1" />
    </g>
    <g>
      <line x1="800" y1="400" x2="800" y2="520" stroke="hsl(var(--accent) / 0.6)" strokeWidth="5" />
      <line x1="797" y1="400" x2="797" y2="520" stroke="hsl(var(--accent) / 0.3)" strokeWidth="1" />
    </g>
    <g>
      <line x1="620" y1="600" x2="760" y2="600" stroke="hsl(var(--accent) / 0.6)" strokeWidth="5" />
      <line x1="620" y1="597" x2="760" y2="597" stroke="hsl(var(--accent) / 0.3)" strokeWidth="1" />
    </g>
    <g>
      <line x1="20" y1="320" x2="20" y2="390" stroke="hsl(var(--accent) / 0.6)" strokeWidth="5" />
      <line x1="17" y1="320" x2="17" y2="390" stroke="hsl(var(--accent) / 0.3)" strokeWidth="1" />
    </g>

    {/* Kitchen furniture */}
    <g opacity="0.3">
      {/* Stove */}
      <rect x="35" y="35" width="70" height="60" rx="3" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="1" />
      <circle cx="55" cy="52" r="8" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <circle cx="85" cy="52" r="8" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <circle cx="55" cy="78" r="8" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <circle cx="85" cy="78" r="8" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      {/* Sink */}
      <rect x="35" y="110" width="70" height="50" rx="3" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="1" />
      <rect x="42" y="117" width="24" height="36" rx="8" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <rect x="72" y="117" width="24" height="36" rx="8" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      {/* Counter */}
      <rect x="35" y="170" width="70" height="15" rx="2" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <rect x="35" y="185" width="15" height="70" rx="2" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      {/* Fridge */}
      <rect x="120" y="35" width="50" height="65" rx="3" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="1" />
      <line x1="145" y1="38" x2="145" y2="97" stroke="hsl(var(--muted-foreground))" strokeWidth="0.6" />
      {/* Dining table */}
      <rect x="180" y="120" width="100" height="65" rx="4" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="1" />
      <rect x="192" y="108" width="22" height="10" rx="3" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <rect x="246" y="108" width="22" height="10" rx="3" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <rect x="192" y="187" width="22" height="10" rx="3" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <rect x="246" y="187" width="22" height="10" rx="3" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <rect x="168" y="135" width="10" height="22" rx="3" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <rect x="282" y="135" width="10" height="22" rx="3" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
    </g>

    {/* Living room furniture */}
    <g opacity="0.3">
      <rect x="380" y="230" width="180" height="60" rx="6" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="1" />
      <rect x="580" y="230" width="55" height="55" rx="6" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="1" />
      <rect x="430" y="170" width="100" height="45" rx="3" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <rect x="420" y="36" width="160" height="18" rx="2" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <circle cx="660" cy="260" r="16" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <circle cx="770" cy="50" r="13" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <rect x="660" y="30" width="80" height="20" rx="2" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
    </g>

    {/* Bathroom furniture */}
    <g opacity="0.3">
      <rect x="30" y="295" width="55" height="105" rx="20" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="1" />
      <rect x="105" y="295" width="40" height="22" rx="3" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <ellipse cx="125" cy="338" rx="18" ry="22" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <rect x="105" y="405" width="48" height="35" rx="3" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <ellipse cx="129" cy="422" rx="16" ry="11" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.6" />
    </g>

    {/* Bedroom 1 furniture */}
    <g opacity="0.3">
      <rect x="640" y="370" width="130" height="160" rx="4" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="1" />
      <rect x="650" y="378" width="48" height="30" rx="8" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.6" />
      <rect x="712" y="378" width="48" height="30" rx="8" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.6" />
      <rect x="640" y="540" width="35" height="30" rx="2" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <rect x="736" y="540" width="35" height="30" rx="2" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <rect x="600" y="370" width="25" height="100" rx="2" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
    </g>

    {/* Bedroom 2 furniture */}
    <g opacity="0.3">
      <rect x="210" y="440" width="80" height="140" rx="4" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="1" />
      <rect x="222" y="448" width="56" height="26" rx="8" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.6" />
      <rect x="320" y="440" width="80" height="40" rx="2" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <circle cx="360" cy="505" r="16" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <rect x="320" y="558" width="80" height="18" rx="2" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
      <rect x="435" y="420" width="24" height="80" rx="2" fill="none" stroke="hsl(var(--muted-foreground))" strokeWidth="0.8" />
    </g>
  </g>
);

// AHU boxes rendered on the map
const AHUNodes = () => (
  <g>
    {ahuUnits.map(ahu => (
      <g key={ahu.id}>
        <rect
          x={ahu.x - 22} y={ahu.y - 22} width={44} height={44} rx={2}
          fill="hsl(var(--secondary))" stroke="hsl(var(--border))" strokeWidth={1}
        />
        <text x={ahu.x} y={ahu.y - 4} textAnchor="middle" fill="hsl(var(--muted-foreground))" fontSize={8} fontFamily="var(--font-display)" fontWeight={600}>
          AHU
        </text>
        <text x={ahu.x} y={ahu.y + 8} textAnchor="middle" fill="hsl(var(--muted-foreground))" fontSize={8} fontFamily="var(--font-display)">
          {ahu.label.split('-')[1]}
        </text>
      </g>
    ))}
  </g>
);

export default function FacilityMap({ onDeviceSelect, selectedDeviceId }: FacilityMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });

  const clampTransform = useCallback((x: number, y: number, scale: number) => {
    const s = Math.min(Math.max(scale, 0.5), 4);
    // Allow panning proportional to zoom level
    const maxPan = 300 * s;
    return {
      x: Math.min(Math.max(x, -maxPan), maxPan),
      y: Math.min(Math.max(y, -maxPan), maxPan),
      scale: s,
    };
  }, []);

  useGesture(
    {
      onDrag: ({ delta: [dx, dy], event }) => {
        event.preventDefault();
        setTransform(t => clampTransform(t.x + dx, t.y + dy, t.scale));
      },
      onPinch: ({ offset: [s], event }) => {
        event.preventDefault();
        setTransform(t => clampTransform(t.x, t.y, s));
      },
      onWheel: ({ delta: [, dy], event }) => {
        event.preventDefault();
        const factor = dy > 0 ? 0.95 : 1.05;
        setTransform(t => clampTransform(t.x, t.y, t.scale * factor));
      },
    },
    {
      target: containerRef,
      drag: { filterTaps: true },
      pinch: { scaleBounds: { min: 0.5, max: 4 } },
      wheel: { eventOptions: { passive: false } },
      eventOptions: { passive: false },
    }
  );

  const zoomIn = () => setTransform(t => clampTransform(t.x, t.y, t.scale * 1.3));
  const zoomOut = () => setTransform(t => clampTransform(t.x, t.y, t.scale / 1.3));
  const resetView = () => setTransform({ x: 0, y: 0, scale: 1 });

  return (
    <div className="flex-1 p-6 flex flex-col overflow-hidden">
      <div className="mb-4 flex items-center justify-between shrink-0">
        <div>
          <h1 className="font-display text-lg tracking-tight">Facility Overview</h1>
          <p className="text-[13px] text-muted-foreground mt-0.5">2-Bedroom Apartment · 78 m² · 8 devices connected</p>
        </div>
        <div className="flex items-center gap-4 text-[11px] text-muted-foreground">
          {['healthy', 'warning', 'fault'].map(s => (
            <span key={s} className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: `hsl(${statusColor[s]})` }} />
              <span className="capitalize">{s}</span>
            </span>
          ))}
          <span className="border-l border-border pl-4 flex items-center gap-1.5">
            <span className="font-display">A</span> Actuator
            <span className="font-display ml-2">D</span> Damper
            <span className="font-display ml-2">V</span> Valve
          </span>
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.15, ease: [0.2, 0, 0, 1] }}
        className="border border-border bg-card overflow-hidden flex-1 relative touch-none"
        ref={containerRef}
        style={{ cursor: 'grab' }}
      >
        {/* Zoom controls */}
        <div className="absolute top-3 right-3 z-10 flex flex-col gap-1">
          <button onClick={zoomIn} className="w-8 h-8 flex items-center justify-center bg-secondary border border-border text-muted-foreground hover:text-foreground transition-colors">
            <ZoomIn size={14} />
          </button>
          <button onClick={zoomOut} className="w-8 h-8 flex items-center justify-center bg-secondary border border-border text-muted-foreground hover:text-foreground transition-colors">
            <ZoomOut size={14} />
          </button>
          <button onClick={resetView} className="w-8 h-8 flex items-center justify-center bg-secondary border border-border text-muted-foreground hover:text-foreground transition-colors">
            <Maximize size={14} />
          </button>
        </div>

        {/* Zoom level indicator */}
        <div className="absolute bottom-3 left-3 z-10 text-[10px] text-muted-foreground font-display bg-secondary/80 px-2 py-1 border border-border">
          {Math.round(transform.scale * 100)}%
        </div>

        <svg
          viewBox="0 0 820 620"
          className="w-full h-full"
          style={{
            transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`,
            transformOrigin: 'center center',
            transition: 'none',
          }}
        >
          {/* Background grid */}
          <defs>
            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="hsl(var(--border))" strokeWidth={0.5} opacity={0.3} />
            </pattern>
          </defs>
          <rect width="820" height="620" fill="url(#grid)" />

          {/* Floor plan structure */}
          <FloorPlanBase />

          {/* Ductwork connections */}
          <Ductwork />

          {/* AHU units */}
          <AHUNodes />

          {/* Devices */}
          {devices.map(device => (
            <DeviceNode
              key={device.id}
              device={device}
              selected={device.id === selectedDeviceId}
              onClick={() => onDeviceSelect(device)}
            />
          ))}
        </svg>
      </motion.div>
    </div>
  );
}
