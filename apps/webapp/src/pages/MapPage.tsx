import { useState, useRef, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import DatacenterMap from '@/components/DatacenterMap';
import DeviceDetailPanel from '@/components/DeviceDetailPanel';
import { type FacilityContext } from '@/types/facility';

const HOVER_CLOSE_DELAY_MS = 220;

export default function MapPage() {
  const { ahuUnits, devices, nodePositions } = useOutletContext<FacilityContext>();
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const [hoveredDeviceId, setHoveredDeviceId] = useState<string | null>(null);
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleDeviceSelect = useCallback((device: { id: string }) => {
    setSelectedDeviceId(prev => prev === device.id ? null : device.id);
  }, []);

  const handleDeviceHover = useCallback((device: { id: string }) => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    setHoveredDeviceId(device.id);
  }, []);

  const handleDeviceHoverEnd = useCallback(() => {
    hoverTimerRef.current = setTimeout(() => setHoveredDeviceId(null), HOVER_CLOSE_DELAY_MS);
  }, []);

  const pinnedDevice = devices.find(d => d.id === selectedDeviceId) ?? null;
  const hoveredDevice = !selectedDeviceId && hoveredDeviceId
    ? (devices.find(d => d.id === hoveredDeviceId) ?? null)
    : null;

  const activeDevice = pinnedDevice ?? hoveredDevice;
  const mode = pinnedDevice ? 'pinned' : 'peek';

  return (
    <>
      <DatacenterMap
        ahuUnits={ahuUnits}
        devices={devices}
        nodePositions={nodePositions}
        onDeviceSelect={handleDeviceSelect}
        onDeviceHover={handleDeviceHover}
        onDeviceHoverEnd={handleDeviceHoverEnd}
        selectedDeviceId={selectedDeviceId}
      />
      <div
        className="shrink-0 transition-[width] duration-300"
        style={{ width: pinnedDevice ? 360 : 0, transitionTimingFunction: 'cubic-bezier(0.2,0,0,1)' }}
      />
      <DeviceDetailPanel
        device={activeDevice}
        mode={mode}
        onClose={() => setSelectedDeviceId(null)}
      />
    </>
  );
}
