from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ml.simulation.state import (
    ComponentState,
    DuctSegmentState,
    HeatSource,
    RackState,
    SimulationState,
    ZoneThermalGrid,
)


@dataclass(slots=True)
class DuctSpec:
    id: str
    kind: str
    start_node: str
    end_node: str
    control_component_id: str
    length_m: float
    diameter_m: float
    n_cells: int


@dataclass(slots=True)
class DatacenterTopology:
    zone_ids: tuple[str, ...]
    zone_labels: dict[str, str]
    zone_supply_component: dict[str, str]
    zone_exhaust_component: dict[str, str]
    zone_supply_duct: dict[str, str]
    zone_exhaust_duct: dict[str, str]
    intake_component_id: str
    intake_duct_id: str
    outlet_component_id: str
    outlet_duct_id: str
    component_defaults: dict[str, tuple[str, float]]
    duct_specs: tuple[DuctSpec, ...]


def build_datacenter_topology() -> DatacenterTopology:
    zone_ids = ("zone_ab", "zone_cd", "zone_ef")
    zone_labels = {
        "zone_ab": "Rows A/B",
        "zone_cd": "Rows C/D",
        "zone_ef": "Rows E/F",
    }
    component_defaults = {
        "act_intake": ("actuator", 0.78),
        "vlv_ab": ("valve", 0.72),
        "vlv_cd": ("valve", 0.72),
        "act_ef_supply": ("actuator", 0.72),
        "dmp_ab": ("damper", 0.72),
        "act_cd_exhaust": ("actuator", 0.72),
        "dmp_ef": ("damper", 0.72),
        "dmp_outlet": ("damper", 0.80),
    }
    zone_supply_component = {
        "zone_ab": "vlv_ab",
        "zone_cd": "vlv_cd",
        "zone_ef": "act_ef_supply",
    }
    zone_exhaust_component = {
        "zone_ab": "dmp_ab",
        "zone_cd": "act_cd_exhaust",
        "zone_ef": "dmp_ef",
    }
    zone_supply_duct = {
        "zone_ab": "supply_ab",
        "zone_cd": "supply_cd",
        "zone_ef": "supply_ef",
    }
    zone_exhaust_duct = {
        "zone_ab": "exhaust_ab",
        "zone_cd": "exhaust_cd",
        "zone_ef": "exhaust_ef",
    }
    duct_specs = (
        DuctSpec(
            id="intake_main",
            kind="intake",
            start_node="outside_intake",
            end_node="supply_manifold",
            control_component_id="act_intake",
            length_m=12.0,
            diameter_m=0.60,
            n_cells=24,
        ),
        DuctSpec(
            id="supply_ab",
            kind="supply",
            start_node="supply_manifold",
            end_node="zone_ab",
            control_component_id="vlv_ab",
            length_m=4.0,
            diameter_m=0.30,
            n_cells=20,
        ),
        DuctSpec(
            id="supply_cd",
            kind="supply",
            start_node="supply_manifold",
            end_node="zone_cd",
            control_component_id="vlv_cd",
            length_m=4.0,
            diameter_m=0.30,
            n_cells=20,
        ),
        DuctSpec(
            id="supply_ef",
            kind="supply",
            start_node="supply_manifold",
            end_node="zone_ef",
            control_component_id="act_ef_supply",
            length_m=4.0,
            diameter_m=0.30,
            n_cells=20,
        ),
        DuctSpec(
            id="exhaust_ab",
            kind="exhaust",
            start_node="zone_ab",
            end_node="exhaust_manifold",
            control_component_id="dmp_ab",
            length_m=3.2,
            diameter_m=0.28,
            n_cells=18,
        ),
        DuctSpec(
            id="exhaust_cd",
            kind="exhaust",
            start_node="zone_cd",
            end_node="exhaust_manifold",
            control_component_id="act_cd_exhaust",
            length_m=3.2,
            diameter_m=0.28,
            n_cells=18,
        ),
        DuctSpec(
            id="exhaust_ef",
            kind="exhaust",
            start_node="zone_ef",
            end_node="exhaust_manifold",
            control_component_id="dmp_ef",
            length_m=3.2,
            diameter_m=0.28,
            n_cells=18,
        ),
        DuctSpec(
            id="exhaust_outlet",
            kind="outlet",
            start_node="exhaust_manifold",
            end_node="outside_exhaust",
            control_component_id="dmp_outlet",
            length_m=8.0,
            diameter_m=0.65,
            n_cells=22,
        ),
    )
    return DatacenterTopology(
        zone_ids=zone_ids,
        zone_labels=zone_labels,
        zone_supply_component=zone_supply_component,
        zone_exhaust_component=zone_exhaust_component,
        zone_supply_duct=zone_supply_duct,
        zone_exhaust_duct=zone_exhaust_duct,
        intake_component_id="act_intake",
        intake_duct_id="intake_main",
        outlet_component_id="dmp_outlet",
        outlet_duct_id="exhaust_outlet",
        component_defaults=component_defaults,
        duct_specs=duct_specs,
    )


def build_initial_state(
    topology: DatacenterTopology | None = None,
    *,
    dt_s: float = 1.0,
    ambient_temp_c: float = 24.0,
    supply_temp_c: float = 18.0,
    zone_grid_shape: tuple[int, int] = (30, 20),
) -> SimulationState:
    topology = topology or build_datacenter_topology()
    components: dict[str, ComponentState] = {}
    for component_id, (kind, position) in topology.component_defaults.items():
        components[component_id] = ComponentState(
            id=component_id,
            kind=kind,
            command_position=position,
            effective_position=position,
            min_position=0.05,
            max_position=1.0,
            temperature_c=ambient_temp_c,
        )

    zones: dict[str, ZoneThermalGrid] = {}
    for zone_id in topology.zone_ids:
        zones[zone_id] = _build_zone(
            zone_id=zone_id,
            label=topology.zone_labels[zone_id],
            nx=zone_grid_shape[0],
            ny=zone_grid_shape[1],
            ambient_temp_c=ambient_temp_c,
            supply_temp_c=supply_temp_c,
            rack_count=8,
            rack_power_w=1700.0,
        )

    ducts: dict[str, DuctSegmentState] = {}
    for spec in topology.duct_specs:
        initial_temp = (
            supply_temp_c if spec.kind in {"intake", "supply"} else ambient_temp_c + 8.0
        )
        ducts[spec.id] = DuctSegmentState.create(
            id=spec.id,
            kind=spec.kind,
            start_node=spec.start_node,
            end_node=spec.end_node,
            control_component_id=spec.control_component_id,
            length_m=spec.length_m,
            diameter_m=spec.diameter_m,
            n_cells=spec.n_cells,
            initial_temp_c=initial_temp,
        )

    metadata = {
        "zone_supply_component": topology.zone_supply_component,
        "zone_exhaust_component": topology.zone_exhaust_component,
        "zone_supply_duct": topology.zone_supply_duct,
        "zone_exhaust_duct": topology.zone_exhaust_duct,
        "intake_component_id": topology.intake_component_id,
        "intake_duct_id": topology.intake_duct_id,
        "outlet_component_id": topology.outlet_component_id,
        "outlet_duct_id": topology.outlet_duct_id,
    }
    return SimulationState(
        time_s=0.0,
        dt_s=dt_s,
        components=components,
        ducts=ducts,
        zones=zones,
        metadata=metadata,
    )


def _build_zone(
    *,
    zone_id: str,
    label: str,
    nx: int,
    ny: int,
    ambient_temp_c: float,
    supply_temp_c: float,
    rack_count: int,
    rack_power_w: float,
) -> ZoneThermalGrid:
    temperature = np.full((nx, ny), ambient_temp_c, dtype=float)
    y_positions = np.linspace(2, ny - 3, rack_count).astype(int)
    racks: dict[str, RackState] = {}
    heat_sources: list[HeatSource] = []
    x_source = max(2, int(round(nx * 0.45)))
    for index, y_idx in enumerate(y_positions, start=1):
        rack_id = f"{zone_id}_rack_{index:02d}"
        racks[rack_id] = RackState(
            id=rack_id,
            zone_id=zone_id,
            y_idx=int(y_idx),
            power_w=rack_power_w,
            inlet_temp_c=ambient_temp_c,
            cpu_temp_c=48.0,
        )
        heat_sources.append(
            HeatSource(
                id=f"{rack_id}_heat",
                x_idx=x_source,
                y_idx=int(y_idx),
                power_w=rack_power_w,
            )
        )

    return ZoneThermalGrid(
        id=zone_id,
        name=label,
        width_m=3.0,
        height_m=2.0,
        depth_m=1.0,
        nx=nx,
        ny=ny,
        temperature_c=temperature,
        setpoint_c=24.0,
        ambient_c=ambient_temp_c,
        supply_temp_c=supply_temp_c,
        cold_aisle_temp_c=ambient_temp_c - 1.0,
        hot_aisle_temp_c=ambient_temp_c + 4.0,
        recirculation_fraction=0.0,
        heat_sources=heat_sources,
        racks=racks,
    )
