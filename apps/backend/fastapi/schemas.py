from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

NodeStatus = Literal["healthy", "warning", "critical", "offline"]
DeviceStatus = Literal["healthy", "warning", "fault", "offline"]
FaultState = Literal["open", "resolved"]
DeviceType = Literal["actuator", "damper", "valve"]
AirflowDirection = Literal["supply", "return"] | None
FacilityNodeType = Literal["system", "ahu", "actuator", "damper", "valve", "device"]


class IngestPayload(BaseModel):
    nodeId: str = Field(min_length=1)
    timestamp: datetime
    deviceType: str = Field(min_length=1)
    parentIds: list[str] = Field(default_factory=list)
    telemetry: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    ok: bool
    nodeId: str
    acceptedAt: str


class TelemetryPoint(BaseModel):
    time: str
    value: float


class FaultImpactMeta(BaseModel):
    estimatedImpact: str
    energyWaste: str


class LiveFaultView(BaseModel):
    id: str
    state: Literal["open"]
    kind: str
    probability: float
    summary: str
    recommendedAction: str


class LiveNodeView(BaseModel):
    id: str
    label: str
    type: FacilityNodeType
    status: NodeStatus
    position: float
    parentIds: list[str]
    fault: LiveFaultView | None = None


class FrontendFaultView(BaseModel):
    id: str
    type: str
    severity: Literal["critical", "high", "medium", "low"]
    diagnosis: str
    recommendation: str
    detectedAt: str
    estimatedImpact: str
    energyWaste: str


class DeviceView(BaseModel):
    id: str
    name: str
    model: str
    serial: str
    type: DeviceType
    zone: str
    zoneId: str
    status: DeviceStatus
    x: int
    y: int
    installedDate: str
    anomalyScore: float
    airflowDirection: AirflowDirection
    torque: list[TelemetryPoint]
    position: list[TelemetryPoint]
    temperature: list[TelemetryPoint]
    faults: list[FrontendFaultView]


class DeviceTemplateView(BaseModel):
    id: str
    name: str
    model: str
    serial: str
    type: DeviceType
    zone: str
    zoneId: str
    x: int
    y: int
    installedDate: str
    baseAnomalyScore: float
    airflowDirection: AirflowDirection
    torque: list[TelemetryPoint]
    position: list[TelemetryPoint]
    temperature: list[TelemetryPoint]


class ZoneView(BaseModel):
    id: str
    name: str
    label: str
    x: int
    y: int
    width: int
    height: int
    healthScore: int


class AHUUnitView(BaseModel):
    id: str
    label: str
    x: int
    y: int
    description: str


class BuildingStatsView(BaseModel):
    totalDevices: int
    healthyDevices: int
    warningDevices: int
    faultDevices: int
    overallHealth: float
    energyWaste: str
    estimatedCost: str
    activeFaults: int


class CatalogView(BaseModel):
    deviceTemplates: list[DeviceTemplateView]
    zones: list[ZoneView]
    ahuUnits: list[AHUUnitView]
    faultMetaByDeviceId: dict[str, FaultImpactMeta]


class DerivedView(BaseModel):
    devices: list[DeviceView]
    buildingStats: BuildingStatsView
    nodePositions: dict[str, float]


class MetaView(BaseModel):
    lastIngestAt: str | None = None
    lastClassificationAt: str | None = None
    lastFaultResolutionAt: str | None = None
    seedSource: Literal["mock"] | None = None
    seededAt: str | None = None


class StatusResponse(BaseModel):
    generatedAt: str
    nodes: list[LiveNodeView]
    catalog: CatalogView
    historyByNodeId: dict[str, dict[str, list[TelemetryPoint]]]
    derived: DerivedView
    meta: MetaView


class ResolveFaultRequest(BaseModel):
    resolvedBy: str = Field(min_length=1)
    note: str | None = None


class ResolveFaultResponse(BaseModel):
    ok: bool
    faultId: str
    state: FaultState
