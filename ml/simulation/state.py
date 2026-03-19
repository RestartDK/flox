from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
import copy
import math

import numpy as np


AIR_DENSITY_KG_M3 = 1.2
AIR_HEAT_CAPACITY_J_KG_K = 1005.0
AIR_THERMAL_DIFFUSIVITY_M2_S = 2.2e-5


ComponentKind = Literal["actuator", "valve", "damper", "junction", "system"]
DuctKind = Literal["intake", "supply", "exhaust", "outlet"]


@dataclass(slots=True)
class FailureEvent:
    component_id: str
    mode: str
    severity: float = 1.0
    start_s: float = 0.0
    end_s: float | None = None

    def is_active(self, time_s: float) -> bool:
        if time_s < self.start_s:
            return False
        if self.end_s is None:
            return True
        return time_s <= self.end_s


@dataclass(slots=True)
class HeatSource:
    id: str
    x_idx: int
    y_idx: int
    power_w: float


@dataclass(slots=True)
class RackState:
    id: str
    zone_id: str
    y_idx: int
    power_w: float
    inlet_temp_c: float = 24.0
    cpu_temp_c: float = 48.0
    throttled: bool = False
    shutdown: bool = False


@dataclass(slots=True)
class ComponentState:
    id: str
    kind: ComponentKind
    command_position: float = 0.7
    effective_position: float = 0.7
    min_position: float = 0.05
    max_position: float = 1.0
    status: Literal["healthy", "warning", "fault"] = "healthy"
    airflow_m3s: float = 0.0
    pressure_pa: float = 0.0
    temperature_c: float = 24.0
    active_failure: str | None = None
    failure_probabilities: dict[str, float] = field(default_factory=dict)
    locked_position: float | None = None

    def clamp_command(self) -> None:
        self.command_position = max(
            self.min_position, min(self.max_position, self.command_position)
        )


@dataclass(slots=True)
class DuctSegmentState:
    id: str
    kind: DuctKind
    start_node: str
    end_node: str
    control_component_id: str
    length_m: float
    diameter_m: float
    n_cells: int
    velocity_mps: np.ndarray
    temperature_c: np.ndarray
    pressure_pa: np.ndarray
    flow_m3s: float = 0.0

    @property
    def area_m2(self) -> float:
        return math.pi * (self.diameter_m * 0.5) ** 2

    @property
    def dx_m(self) -> float:
        if self.n_cells <= 1:
            return self.length_m
        return self.length_m / float(self.n_cells - 1)

    @classmethod
    def create(
        cls,
        *,
        id: str,
        kind: DuctKind,
        start_node: str,
        end_node: str,
        control_component_id: str,
        length_m: float,
        diameter_m: float,
        n_cells: int,
        initial_temp_c: float,
    ) -> "DuctSegmentState":
        safe_cells = max(3, int(n_cells))
        return cls(
            id=id,
            kind=kind,
            start_node=start_node,
            end_node=end_node,
            control_component_id=control_component_id,
            length_m=length_m,
            diameter_m=diameter_m,
            n_cells=safe_cells,
            velocity_mps=np.zeros(safe_cells, dtype=float),
            temperature_c=np.full(safe_cells, float(initial_temp_c), dtype=float),
            pressure_pa=np.zeros(safe_cells, dtype=float),
        )


@dataclass(slots=True)
class ZoneThermalGrid:
    id: str
    name: str
    width_m: float
    height_m: float
    depth_m: float
    nx: int
    ny: int
    temperature_c: np.ndarray
    setpoint_c: float = 24.0
    ambient_c: float = 24.0
    supply_temp_c: float = 18.0
    pressure_pa: float = 0.0
    supply_flow_m3s: float = 0.0
    exhaust_flow_m3s: float = 0.0
    heat_sources: list[HeatSource] = field(default_factory=list)
    racks: dict[str, RackState] = field(default_factory=dict)

    @property
    def dx_m(self) -> float:
        if self.nx <= 1:
            return self.width_m
        return self.width_m / float(self.nx - 1)

    @property
    def dy_m(self) -> float:
        if self.ny <= 1:
            return self.height_m
        return self.height_m / float(self.ny - 1)

    @property
    def cell_volume_m3(self) -> float:
        return (self.width_m * self.height_m * self.depth_m) / float(self.nx * self.ny)

    def average_temp_c(self) -> float:
        return float(np.mean(self.temperature_c))


@dataclass(slots=True)
class StepMetrics:
    time_s: float
    zone_avg_temp_c: dict[str, float]
    zone_supply_flow_m3s: dict[str, float]
    zone_exhaust_flow_m3s: dict[str, float]
    max_cpu_temp_c: float
    throttled_cpu_count: int
    shutdown_cpu_count: int


@dataclass(slots=True)
class SimulationState:
    time_s: float
    dt_s: float
    components: dict[str, ComponentState]
    ducts: dict[str, DuctSegmentState]
    zones: dict[str, ZoneThermalGrid]
    active_failures: list[FailureEvent] = field(default_factory=list)
    history: list[StepMetrics] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def record_event(self, message: str) -> None:
        self.events.append(f"t={self.time_s:.1f}s: {message}")


def clone_state(state: SimulationState) -> SimulationState:
    return copy.deepcopy(state)
