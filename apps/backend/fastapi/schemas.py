from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

NodeStatus = Literal["healthy", "warning", "critical"]
FaultState = Literal["open", "resolved"]


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


class FaultView(BaseModel):
    id: str
    state: FaultState
    kind: str
    probability: float
    summary: str
    recommendedAction: str


class NodeView(BaseModel):
    id: str
    label: str
    type: str
    status: NodeStatus
    parentIds: list[str]
    fault: FaultView | None = None


class StatusResponse(BaseModel):
    generatedAt: str
    nodes: list[NodeView]


class ResolveFaultRequest(BaseModel):
    resolvedBy: str = Field(min_length=1)
    note: str | None = None


class ResolveFaultResponse(BaseModel):
    ok: bool
    faultId: str
    state: FaultState
