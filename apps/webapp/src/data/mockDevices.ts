export type DeviceStatus = 'healthy' | 'warning' | 'fault' | 'offline';
export type DeviceType = 'actuator' | 'damper' | 'valve';

export interface TelemetryPoint {
  time: string;
  value: number;
}

export interface Fault {
  id: string;
  type: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  diagnosis: string;
  recommendation: string;
  detectedAt: string;
  estimatedImpact: string;
  energyWaste: string;
}

export interface Device {
  id: string;
  name: string;
  model: string;
  serial: string;
  type: DeviceType;
  zone: string;
  zoneId: string;
  status: DeviceStatus;
  x: number;
  y: number;
  installedDate: string;
  anomalyScore: number;
  torque: TelemetryPoint[];
  position: TelemetryPoint[];
  temperature: TelemetryPoint[];
  faults: Fault[];
}

export interface Zone {
  id: string;
  name: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  healthScore: number;
}

const generateTelemetry = (base: number, variance: number, anomaly = false): TelemetryPoint[] => {
  return Array.from({ length: 24 }, (_, i) => ({
    time: `${String(i).padStart(2, '0')}:00`,
    value: base + (Math.random() - 0.5) * variance + (anomaly && i > 18 ? variance * 2 : 0),
  }));
};

// Zones mapped to the floor plan rooms
export const zones: Zone[] = [
  { id: 'zone-kitchen', name: 'Kitchen', label: 'K', x: 25, y: 25, width: 280, height: 255, healthScore: 94 },
  { id: 'zone-living', name: 'Living Room', label: 'L', x: 308, y: 25, width: 487, height: 295, healthScore: 67 },
  { id: 'zone-bath', name: 'Bathroom', label: 'B', x: 25, y: 288, width: 153, height: 182, healthScore: 88 },
  { id: 'zone-bed1', name: 'Bedroom 1', label: '1', x: 588, y: 328, width: 207, height: 267, healthScore: 98 },
  { id: 'zone-bed2', name: 'Bedroom 2', label: '2', x: 186, y: 408, width: 244, height: 187, healthScore: 91 },
];

// AHU positions on the floor plan
export const ahuUnits = [
  { id: 'ahu-01', label: 'AHU-01', x: 310, y: 240, description: 'Kitchen & Living' },
  { id: 'ahu-02', label: 'AHU-02', x: 460, y: 370, description: 'Bedrooms & Bath' },
];

// Devices placed at specific locations on the floor plan
export const devices: Device[] = [
  {
    id: 'BEL-ACT-001', name: 'Kitchen Supply Actuator', model: 'LMV-D3', serial: 'SN-88421',
    type: 'actuator', zone: 'Kitchen', zoneId: 'zone-kitchen',
    status: 'healthy', x: 160, y: 210, installedDate: '2024-06-15', anomalyScore: 0.12,
    torque: generateTelemetry(4.2, 0.8), position: generateTelemetry(72, 15), temperature: generateTelemetry(23, 2),
    faults: [],
  },
  {
    id: 'BEL-DMP-002', name: 'Kitchen Exhaust Damper', model: 'NMV-D2M', serial: 'SN-88422',
    type: 'damper', zone: 'Kitchen', zoneId: 'zone-kitchen',
    status: 'healthy', x: 80, y: 100, installedDate: '2024-06-15', anomalyScore: 0.08,
    torque: generateTelemetry(3.8, 0.5), position: generateTelemetry(65, 10), temperature: generateTelemetry(22, 1.5),
    faults: [],
  },
  {
    id: 'BEL-VLV-003', name: 'Living Room Chiller Valve', model: 'R2025-S2', serial: 'SN-71004',
    type: 'valve', zone: 'Living Room', zoneId: 'zone-living',
    status: 'fault', x: 550, y: 100, installedDate: '2023-11-20', anomalyScore: 0.91,
    torque: generateTelemetry(6.8, 2.5, true), position: generateTelemetry(45, 30, true), temperature: generateTelemetry(28, 5, true),
    faults: [{
      id: 'F-001', type: 'Stuck Actuator', severity: 'critical',
      diagnosis: 'Torque signature shows mechanical binding at 45° position. Position tracking deviates >30% from setpoint. Likely cause: debris accumulation or gear wear in actuator assembly.',
      recommendation: 'Inspect actuator assembly for debris. If gear teeth show wear, replace actuator. Estimated 2hr service call.',
      detectedAt: '2026-03-17T14:30:00Z', estimatedImpact: '$1,200/day cooling inefficiency',
      energyWaste: '340 kWh/day',
    }],
  },
  {
    id: 'BEL-ACT-004', name: 'Living Room Damper Actuator', model: 'LMV-D3', serial: 'SN-71005',
    type: 'actuator', zone: 'Living Room', zoneId: 'zone-living',
    status: 'warning', x: 700, y: 200, installedDate: '2024-01-10', anomalyScore: 0.64,
    torque: generateTelemetry(5.1, 1.8, true), position: generateTelemetry(80, 20), temperature: generateTelemetry(26, 3),
    faults: [{
      id: 'F-002', type: 'Control Signal Drift', severity: 'high',
      diagnosis: 'Position feedback shows increasing deviation from control signal over 72hr window. Drift rate: 0.8%/hr. Pattern consistent with calibration loss in position sensor.',
      recommendation: 'Recalibrate position sensor. If drift persists after calibration, replace feedback potentiometer.',
      detectedAt: '2026-03-18T08:15:00Z', estimatedImpact: '$400/day energy waste',
      energyWaste: '120 kWh/day',
    }],
  },
  {
    id: 'BEL-VLV-005', name: 'Bathroom Water Valve', model: 'AF24-MFT', serial: 'SN-55301',
    type: 'valve', zone: 'Bathroom', zoneId: 'zone-bath',
    status: 'warning', x: 100, y: 380, installedDate: '2024-03-22', anomalyScore: 0.52,
    torque: generateTelemetry(3.2, 1.2), position: generateTelemetry(55, 18), temperature: generateTelemetry(21, 2),
    faults: [{
      id: 'F-003', type: 'Oversized Valve', severity: 'medium',
      diagnosis: 'Valve operates consistently below 30% open position. Flow coefficient analysis suggests valve is oversized for current load profile.',
      recommendation: 'Evaluate replacing with smaller valve size. Current oversizing wastes ~80 kWh/day through hunting behavior.',
      detectedAt: '2026-03-16T10:00:00Z', estimatedImpact: '$180/day energy waste',
      energyWaste: '80 kWh/day',
    }],
  },
  {
    id: 'BEL-DMP-006', name: 'Bedroom 1 Supply Damper', model: 'R2015-S1', serial: 'SN-55302',
    type: 'damper', zone: 'Bedroom 1', zoneId: 'zone-bed1',
    status: 'healthy', x: 700, y: 450, installedDate: '2025-01-08', anomalyScore: 0.05,
    torque: generateTelemetry(2.8, 0.4), position: generateTelemetry(60, 8), temperature: generateTelemetry(42, 3),
    faults: [],
  },
  {
    id: 'BEL-ACT-007', name: 'Bedroom 1 Return Actuator', model: 'LMV-D3', serial: 'SN-99100',
    type: 'actuator', zone: 'Bedroom 1', zoneId: 'zone-bed1',
    status: 'healthy', x: 750, y: 550, installedDate: '2025-02-14', anomalyScore: 0.03,
    torque: generateTelemetry(3.5, 0.3), position: generateTelemetry(70, 5), temperature: generateTelemetry(22, 1),
    faults: [],
  },
  {
    id: 'BEL-DMP-008', name: 'Bedroom 2 Fresh Air Damper', model: 'NMV-D2M', serial: 'SN-99101',
    type: 'damper', zone: 'Bedroom 2', zoneId: 'zone-bed2',
    status: 'healthy', x: 350, y: 520, installedDate: '2025-02-14', anomalyScore: 0.07,
    torque: generateTelemetry(2.9, 0.5), position: generateTelemetry(50, 10), temperature: generateTelemetry(20, 1.5),
    faults: [],
  },
];

export const buildingStats = {
  totalDevices: devices.length,
  healthyDevices: devices.filter(d => d.status === 'healthy').length,
  warningDevices: devices.filter(d => d.status === 'warning').length,
  faultDevices: devices.filter(d => d.status === 'fault').length,
  overallHealth: 86.4,
  energyWaste: '540 kWh/day',
  estimatedCost: '$1,780/day',
  activeFaults: devices.reduce((sum, d) => sum + d.faults.length, 0),
};
