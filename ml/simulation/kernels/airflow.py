from __future__ import annotations

import math

import numpy as np

from ml.simulation.kernels.base import Kernel
from ml.simulation.state import DuctSegmentState, SimulationState
from ml.simulation.topology import DatacenterTopology


class AirflowPropagationKernel(Kernel):
    """
    Lumped-parameter airflow model.

    Flow rates are computed from a manifold pressure balance using orifice equations.
    Zone pressures are integrated with implicit Euler so the scheme is unconditionally
    stable regardless of dt.  Duct temperatures use a residence-time mixing model —
    no inner loops.
    """

    name = "airflow_propagation"

    def __init__(
        self,
        topology: DatacenterTopology,
        *,
        cooled_supply_temp_c: float = 18.0,
        supply_fan_head_pa: float = 280.0,
        exhaust_suction_pa: float = 240.0,
        branch_gain_m3s_sqrt_pa: float = 0.042,
        pressure_gain_pa_per_m3s: float = 80.0,
        pressure_damping_per_s: float = 0.8,
        velocity_relaxation_per_s: float = 3.0,
    ) -> None:
        self.topology = topology
        self.cooled_supply_temp_c = cooled_supply_temp_c
        self.supply_fan_head_pa = supply_fan_head_pa
        self.exhaust_suction_pa = exhaust_suction_pa
        self.branch_gain_m3s_sqrt_pa = branch_gain_m3s_sqrt_pa
        self.pressure_gain_pa_per_m3s = pressure_gain_pa_per_m3s
        self.pressure_damping_per_s = pressure_damping_per_s
        self.velocity_relaxation_per_s = velocity_relaxation_per_s

    def apply(self, state: SimulationState) -> SimulationState:
        dt_s = state.dt_s
        intake = state.components[self.topology.intake_component_id]
        outlet = state.components[self.topology.outlet_component_id]

        prev_supply = sum(z.supply_flow_m3s for z in state.zones.values())
        prev_exhaust = sum(z.exhaust_flow_m3s for z in state.zones.values())

        # Manifold pressures — linear flow-resistance terms keep these bounded
        supply_manifold_pa = (
            self.supply_fan_head_pa * intake.effective_position - 32.0 * prev_supply
        )
        exhaust_manifold_pa = (
            -self.exhaust_suction_pa * outlet.effective_position + 32.0 * prev_exhaust
        )

        supply_flows: dict[str, float] = {}
        exhaust_flows: dict[str, float] = {}

        for zone_id in self.topology.zone_ids:
            zone = state.zones[zone_id]
            sc = state.components[self.topology.zone_supply_component[zone_id]]
            ec = state.components[self.topology.zone_exhaust_component[zone_id]]

            supply_dp = max(supply_manifold_pa - zone.pressure_pa, 0.0)
            exhaust_dp = max(zone.pressure_pa - exhaust_manifold_pa, 0.0)

            sf = (
                self.branch_gain_m3s_sqrt_pa
                * sc.effective_position
                * math.sqrt(supply_dp)
            )
            ef = (
                self.branch_gain_m3s_sqrt_pa
                * ec.effective_position
                * math.sqrt(exhaust_dp)
            )

            zone.supply_flow_m3s = max(0.0, sf)
            zone.exhaust_flow_m3s = max(0.0, ef)

            # Implicit Euler for zone pressure — unconditionally stable
            numerator = zone.pressure_pa + dt_s * self.pressure_gain_pa_per_m3s * (
                sf - ef
            )
            zone.pressure_pa = numerator / (1.0 + dt_s * self.pressure_damping_per_s)

            supply_flows[zone_id] = zone.supply_flow_m3s
            exhaust_flows[zone_id] = zone.exhaust_flow_m3s
            sc.airflow_m3s = zone.supply_flow_m3s
            ec.airflow_m3s = zone.exhaust_flow_m3s

        intake_flow = sum(supply_flows.values())
        outlet_flow = sum(exhaust_flows.values())
        intake.airflow_m3s = intake_flow
        outlet.airflow_m3s = outlet_flow

        ambient_c = float(np.mean([z.ambient_c for z in state.zones.values()]))
        supply_source_temp_c = min(self.cooled_supply_temp_c, ambient_c - 2.0)
        exhaust_manifold_temp_c = sum(
            state.zones[z].average_temp_c() * f for z, f in exhaust_flows.items()
        ) / max(outlet_flow, 1e-6)

        # Update duct visualization fields (fast: only numpy vectorized ops)
        self._update_duct(
            state.ducts[self.topology.intake_duct_id],
            flow_m3s=intake_flow,
            source_temp_c=ambient_c,
            sink_temp_c=supply_source_temp_c,
            source_pa=0.0,
            sink_pa=supply_manifold_pa,
            dt_s=dt_s,
        )

        for zone_id in self.topology.zone_ids:
            zone = state.zones[zone_id]
            self._update_duct(
                state.ducts[self.topology.zone_supply_duct[zone_id]],
                flow_m3s=supply_flows[zone_id],
                source_temp_c=supply_source_temp_c,
                sink_temp_c=supply_source_temp_c
                + 0.08 * max(zone.average_temp_c() - supply_source_temp_c, 0.0),
                source_pa=supply_manifold_pa,
                sink_pa=zone.pressure_pa,
                dt_s=dt_s,
            )
            zone.supply_temp_c = float(
                state.ducts[self.topology.zone_supply_duct[zone_id]].temperature_c[-1]
            )
            self._update_duct(
                state.ducts[self.topology.zone_exhaust_duct[zone_id]],
                flow_m3s=exhaust_flows[zone_id],
                source_temp_c=zone.average_temp_c(),
                sink_temp_c=exhaust_manifold_temp_c,
                source_pa=zone.pressure_pa,
                sink_pa=exhaust_manifold_pa,
                dt_s=dt_s,
            )

        self._update_duct(
            state.ducts[self.topology.outlet_duct_id],
            flow_m3s=outlet_flow,
            source_temp_c=exhaust_manifold_temp_c,
            sink_temp_c=ambient_c + 4.0,
            source_pa=exhaust_manifold_pa,
            sink_pa=0.0,
            dt_s=dt_s,
        )
        return state

    def _update_duct(
        self,
        duct: DuctSegmentState,
        *,
        flow_m3s: float,
        source_temp_c: float,
        sink_temp_c: float,
        source_pa: float,
        sink_pa: float,
        dt_s: float,
    ) -> None:
        area = max(duct.area_m2, 1e-8)
        target_v = flow_m3s / area
        relax = min(1.0, self.velocity_relaxation_per_s * dt_s)
        duct.velocity_mps += relax * (target_v - duct.velocity_mps)
        np.clip(duct.velocity_mps, -18.0, 18.0, out=duct.velocity_mps)

        mean_v = max(abs(float(np.mean(duct.velocity_mps))), 0.05)
        tau = duct.length_m / mean_v
        mix = min(1.0, dt_s / max(tau, dt_s * 0.1))
        target_temp = np.linspace(source_temp_c, sink_temp_c, duct.n_cells)
        duct.temperature_c = (1.0 - mix) * duct.temperature_c + mix * target_temp
        duct.pressure_pa[:] = np.linspace(source_pa, sink_pa, duct.n_cells)
        duct.flow_m3s = flow_m3s
