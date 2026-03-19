from __future__ import annotations

import math

import numpy as np

from ml.simulation.kernels.base import Kernel
from ml.simulation.state import DuctSegmentState, SimulationState
from ml.simulation.topology import DatacenterTopology


class AirflowPropagationKernel(Kernel):
    name = "airflow_propagation"

    def __init__(
        self,
        topology: DatacenterTopology,
        *,
        supply_fan_head_pa: float = 720.0,
        exhaust_suction_pa: float = 620.0,
        branch_gain_m3s_sqrt_pa: float = 0.055,
        pressure_gain_pa_per_m3s: float = 160.0,
        pressure_damping_per_s: float = 1.2,
        momentum_diffusivity_m2_s: float = 5.0e-3,
        velocity_relaxation_per_s: float = 2.2,
        thermal_diffusivity_m2_s: float = 2.2e-5,
    ) -> None:
        self.topology = topology
        self.supply_fan_head_pa = supply_fan_head_pa
        self.exhaust_suction_pa = exhaust_suction_pa
        self.branch_gain_m3s_sqrt_pa = branch_gain_m3s_sqrt_pa
        self.pressure_gain_pa_per_m3s = pressure_gain_pa_per_m3s
        self.pressure_damping_per_s = pressure_damping_per_s
        self.momentum_diffusivity_m2_s = momentum_diffusivity_m2_s
        self.velocity_relaxation_per_s = velocity_relaxation_per_s
        self.thermal_diffusivity_m2_s = thermal_diffusivity_m2_s

    def apply(self, state: SimulationState) -> SimulationState:
        dt_s = state.dt_s
        intake_component = state.components[self.topology.intake_component_id]
        outlet_component = state.components[self.topology.outlet_component_id]
        ambient_temp_c = self._ambient_temp(state)

        total_supply_previous = sum(
            zone.supply_flow_m3s for zone in state.zones.values()
        )
        total_exhaust_previous = sum(
            zone.exhaust_flow_m3s for zone in state.zones.values()
        )

        supply_manifold_pa = (
            self.supply_fan_head_pa * intake_component.effective_position
            - 90.0 * total_supply_previous
        )
        exhaust_manifold_pa = (
            -self.exhaust_suction_pa * outlet_component.effective_position
            + 90.0 * total_exhaust_previous
        )

        supply_flows: dict[str, float] = {}
        exhaust_flows: dict[str, float] = {}
        for zone_id in self.topology.zone_ids:
            zone = state.zones[zone_id]
            supply_component = state.components[
                self.topology.zone_supply_component[zone_id]
            ]
            exhaust_component = state.components[
                self.topology.zone_exhaust_component[zone_id]
            ]

            supply_dp = max(supply_manifold_pa - zone.pressure_pa, 0.0)
            exhaust_dp = max(zone.pressure_pa - exhaust_manifold_pa, 0.0)
            supply_flow = (
                self.branch_gain_m3s_sqrt_pa
                * supply_component.effective_position
                * math.sqrt(supply_dp)
            )
            exhaust_flow = (
                self.branch_gain_m3s_sqrt_pa
                * exhaust_component.effective_position
                * math.sqrt(exhaust_dp)
            )

            zone.supply_flow_m3s = supply_flow
            zone.exhaust_flow_m3s = exhaust_flow
            zone.pressure_pa += dt_s * (
                self.pressure_gain_pa_per_m3s * (supply_flow - exhaust_flow)
                - self.pressure_damping_per_s * zone.pressure_pa
            )

            supply_flows[zone_id] = supply_flow
            exhaust_flows[zone_id] = exhaust_flow
            supply_component.airflow_m3s = supply_flow
            exhaust_component.airflow_m3s = exhaust_flow
            supply_component.pressure_pa = supply_manifold_pa
            exhaust_component.pressure_pa = zone.pressure_pa

        intake_flow = float(sum(supply_flows.values()))
        outlet_flow = float(sum(exhaust_flows.values()))
        intake_component.airflow_m3s = intake_flow
        intake_component.pressure_pa = supply_manifold_pa
        outlet_component.airflow_m3s = outlet_flow
        outlet_component.pressure_pa = exhaust_manifold_pa

        if outlet_flow > 1e-8:
            exhaust_manifold_temp_c = (
                sum(
                    state.zones[zone_id].average_temp_c() * flow
                    for zone_id, flow in exhaust_flows.items()
                )
                / outlet_flow
            )
        else:
            exhaust_manifold_temp_c = ambient_temp_c + 6.0

        intake_duct = state.ducts[self.topology.intake_duct_id]
        self._update_duct_fd(
            duct=intake_duct,
            target_flow_m3s=intake_flow,
            source_temp_c=ambient_temp_c,
            sink_temp_c=min(zone.supply_temp_c for zone in state.zones.values()),
            source_pressure_pa=0.0,
            sink_pressure_pa=supply_manifold_pa,
            dt_s=dt_s,
        )

        for zone_id in self.topology.zone_ids:
            zone = state.zones[zone_id]
            supply_duct = state.ducts[self.topology.zone_supply_duct[zone_id]]
            self._update_duct_fd(
                duct=supply_duct,
                target_flow_m3s=supply_flows[zone_id],
                source_temp_c=zone.supply_temp_c,
                sink_temp_c=zone.average_temp_c(),
                source_pressure_pa=supply_manifold_pa,
                sink_pressure_pa=zone.pressure_pa,
                dt_s=dt_s,
            )
            zone.supply_temp_c = float(supply_duct.temperature_c[-1])

            exhaust_duct = state.ducts[self.topology.zone_exhaust_duct[zone_id]]
            self._update_duct_fd(
                duct=exhaust_duct,
                target_flow_m3s=exhaust_flows[zone_id],
                source_temp_c=zone.average_temp_c(),
                sink_temp_c=exhaust_manifold_temp_c,
                source_pressure_pa=zone.pressure_pa,
                sink_pressure_pa=exhaust_manifold_pa,
                dt_s=dt_s,
            )

        outlet_duct = state.ducts[self.topology.outlet_duct_id]
        self._update_duct_fd(
            duct=outlet_duct,
            target_flow_m3s=outlet_flow,
            source_temp_c=exhaust_manifold_temp_c,
            sink_temp_c=ambient_temp_c + 4.0,
            source_pressure_pa=exhaust_manifold_pa,
            sink_pressure_pa=0.0,
            dt_s=dt_s,
        )
        outlet_component.temperature_c = float(outlet_duct.temperature_c[0])

        return state

    def _update_duct_fd(
        self,
        *,
        duct: DuctSegmentState,
        target_flow_m3s: float,
        source_temp_c: float,
        sink_temp_c: float,
        source_pressure_pa: float,
        sink_pressure_pa: float,
        dt_s: float,
    ) -> None:
        area = max(duct.area_m2, 1e-8)
        target_velocity = target_flow_m3s / area
        u = duct.velocity_mps
        t = duct.temperature_c
        dx = max(duct.dx_m, 1e-6)

        substeps = max(1, int(math.ceil(abs(target_velocity) * dt_s / dx)))
        dt_sub = dt_s / float(substeps)

        for _ in range(substeps):
            u_next = u.copy()
            for idx in range(1, duct.n_cells - 1):
                advection = -u[idx] * (u[idx] - u[idx - 1]) / dx
                diffusion = (
                    self.momentum_diffusivity_m2_s
                    * (u[idx + 1] - 2.0 * u[idx] + u[idx - 1])
                    / (dx * dx)
                )
                relaxation = self.velocity_relaxation_per_s * (target_velocity - u[idx])
                u_next[idx] = u[idx] + dt_sub * (advection + diffusion + relaxation)
            u_next[0] = target_velocity
            u_next[-1] = target_velocity
            u = np.clip(u_next, -18.0, 18.0)

            t_next = t.copy()
            for idx in range(1, duct.n_cells - 1):
                if u[idx] >= 0.0:
                    upwind_grad = (t[idx] - t[idx - 1]) / dx
                else:
                    upwind_grad = (t[idx + 1] - t[idx]) / dx
                diffusion = (
                    self.thermal_diffusivity_m2_s
                    * (t[idx + 1] - 2.0 * t[idx] + t[idx - 1])
                    / (dx * dx)
                )
                t_next[idx] = t[idx] + dt_sub * (-u[idx] * upwind_grad + diffusion)
            blend = min(1.0, 0.25 + 0.05 * abs(target_velocity))
            t_next[0] = (1.0 - blend) * t_next[0] + blend * source_temp_c
            t_next[-1] = (1.0 - blend) * t_next[-1] + blend * sink_temp_c
            t = np.clip(
                np.nan_to_num(t_next, nan=sink_temp_c, posinf=140.0, neginf=-40.0),
                -40.0,
                140.0,
            )

        duct.velocity_mps = u
        duct.temperature_c = t
        duct.pressure_pa = np.linspace(
            source_pressure_pa, sink_pressure_pa, duct.n_cells
        )
        duct.flow_m3s = target_flow_m3s

    def _ambient_temp(self, state: SimulationState) -> float:
        if not state.zones:
            return 24.0
        return float(np.mean([zone.ambient_c for zone in state.zones.values()]))
