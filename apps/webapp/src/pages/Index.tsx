import { useState } from 'react';
import { type Device } from '@/data/mockDevices';
import AppSidebar from '@/components/AppSidebar';
import FacilityMap from '@/components/FacilityMap';
import DeviceDetailPanel from '@/components/DeviceDetailPanel';
import AlertDashboard from '@/components/AlertDashboard';

export default function Index() {
  const [activeView, setActiveView] = useState<'map' | 'alerts'>('map');
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);

  const handleDeviceSelect = (device: Device) => {
    setSelectedDevice(device);
    setActiveView('map');
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <AppSidebar activeView={activeView} onViewChange={setActiveView} />
      
      <div className="flex flex-1 overflow-hidden">
        {activeView === 'map' ? (
          <FacilityMap
            onDeviceSelect={setSelectedDevice}
            selectedDeviceId={selectedDevice?.id ?? null}
          />
        ) : (
          <AlertDashboard onNavigateToDevice={handleDeviceSelect} />
        )}

        <DeviceDetailPanel device={selectedDevice} onClose={() => setSelectedDevice(null)} />
      </div>

      {/* Top loading bar placeholder */}
      <div className="fixed top-0 left-0 right-0 h-0.5 z-50" />
    </div>
  );
}
