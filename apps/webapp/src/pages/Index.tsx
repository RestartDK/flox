import { useState } from 'react';
import AppSidebar from '@/components/AppSidebar';
import FacilityMap from '@/components/FacilityMap';
import DeviceDetailPanel from '@/components/DeviceDetailPanel';
import AlertDashboard from '@/components/AlertDashboard';
import { useFacilityData } from '@/hooks/useFacilityData';

export default function Index() {
  const [activeView, setActiveView] = useState<'map' | 'alerts'>('map');
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const { buildingStats, devices } = useFacilityData();
  const selectedDevice = devices.find(device => device.id === selectedDeviceId) ?? null;

  const handleDeviceSelect = (deviceId: string) => {
    setSelectedDeviceId(deviceId);
    setActiveView('map');
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <AppSidebar activeView={activeView} onViewChange={setActiveView} buildingStats={buildingStats} />
      
      <div className="flex flex-1 overflow-hidden">
        {activeView === 'map' ? (
          <FacilityMap
            devices={devices}
            onDeviceSelect={(device) => setSelectedDeviceId(device.id)}
            selectedDeviceId={selectedDeviceId}
          />
        ) : (
          <AlertDashboard devices={devices} onNavigateToDevice={(device) => handleDeviceSelect(device.id)} />
        )}

        <DeviceDetailPanel device={selectedDevice} onClose={() => setSelectedDeviceId(null)} />
      </div>

      {/* Top loading bar placeholder */}
      <div className="fixed top-0 left-0 right-0 h-0.5 z-50" />
    </div>
  );
}
