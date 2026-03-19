from __future__ import annotations

import math

import numpy as np

from ml.simulation.kernels.base import Kernel
from ml.simulation.state import (
    AIR_DENSITY_KG_M3,
    AIR_HEAT_CAPACITY_J_KG_K,
    AIR_THERMAL_DIFFUSIVITY_M2_S,
    SimulationState,
)


class ThermalPropagationKernel(Kernel):
    name = "thermal_propagation"

    def __init__(
        self,
        *,
        thermal_diffusivity_m2_s: float = AIR_THERMAL_DIFFUSIVITY_M2_S,
        convection_per_flow: float = 0.46,
        cpu_thermal_resistance_k_per_w: float = 0.011,
        cpu_tau_s: float = 55.0,
    ) -> None:
        self.thermal_diffusivity_m2_s = thermal_diffusivity_m2_s
        self.convection_per_flow = convection_per_flow
        self.cpu_thermal_resistance_k_per_w = cpu_thermal_resistance_k_per_w
        self.cpu_tau_s = cpu_tau_s

    def apply(self, state: SimulationState) -> SimulationState:
        for zone in state.zones.values():
            self._sync_heat_sources_with_racks(zone)
            self._step_zone_temperature(zone=zone, dt_s=state.dt_s)
            self._update_rack_temperatures(zone=zone, dt_s=state.dt_s)
        return state

    def _step_zone_temperature(self, *, zone, dt_s: float) -> None:
        temperature = zone.temperature_c
        nx, ny = zone.nx, zone.ny
        dx = max(zone.dx_m, 1e-6)
        dy = max(zone.dy_m, 1e-6)
        heat_term = np.zeros((nx, ny), dtype=float)
        for source in zone.heat_sources:
            heat_term[source.x_idx, source.y_idx] += source.power_w

        stable_dt = 0.24 / (
            self.thermal_diffusivity_m2_s * (1.0 / (dx * dx) + 1.0 / (dy * dy))
        )
        substeps = max(1, int(math.ceil(dt_s / max(stable_dt, 1e-4))))
        dt_sub = dt_s / float(substeps)

        flow_velocity_x = zone.supply_flow_m3s / max(zone.height_m * zone.depth_m, 1e-6)
        exhaust_efficiency = min(
            1.0,
            zone.exhaust_flow_m3s / max(zone.supply_flow_m3s, 1e-6),
        )
        convection_rate = (
            self.convection_per_flow
            * zone.supply_flow_m3s
            * exhaust_efficiency
            / max(zone.depth_m, 1e-6)
        )
        source_scaling = 1.0 / (
            AIR_DENSITY_KG_M3 * AIR_HEAT_CAPACITY_J_KG_K * zone.cell_volume_m3
        )
        recirculation_fraction = 0.0
        if zone.supply_flow_m3s > 1e-8:
            flow_imbalance = max(zone.supply_flow_m3s - zone.exhaust_flow_m3s, 0.0)
            recirculation_fraction = min(0.85, flow_imbalance / zone.supply_flow_m3s)
        hot_side_temp_c = float(np.mean(temperature[-3:, :]))
        effective_supply_temp_c = (
            1.0 - recirculation_fraction
        ) * zone.supply_temp_c + recirculation_fraction * hot_side_temp_c

        for _ in range(substeps):
            current = temperature
            nxt = current.copy()
            lap_x = (
                current[2:, 1:-1] - 2.0 * current[1:-1, 1:-1] + current[:-2, 1:-1]
            ) / (dx * dx)
            lap_y = (
                current[1:-1, 2:] - 2.0 * current[1:-1, 1:-1] + current[1:-1, :-2]
            ) / (dy * dy)
            upwind_x = (current[1:-1, 1:-1] - current[:-2, 1:-1]) / dx
            source = heat_term[1:-1, 1:-1] * source_scaling
            cooling = convection_rate * (current[1:-1, 1:-1] - effective_supply_temp_c)

            nxt[1:-1, 1:-1] = current[1:-1, 1:-1] + dt_sub * (
                self.thermal_diffusivity_m2_s * (lap_x + lap_y)
                - flow_velocity_x * upwind_x
                + source
                - cooling
            )

            inlet_mix = min(
                1.0,
                0.10 + 0.8 * zone.supply_flow_m3s * exhaust_efficiency * dt_sub,
            )
            nxt[0, :] = (1.0 - inlet_mix) * current[
                0, :
            ] + inlet_mix * effective_supply_temp_c
            nxt[-1, :] = nxt[-2, :]
            nxt[:, 0] = nxt[:, 1]
            nxt[:, -1] = nxt[:, -2]
            temperature = np.clip(nxt, zone.ambient_c - 6.0, 120.0)

        zone.temperature_c = temperature

    def _update_rack_temperatures(self, *, zone, dt_s: float) -> None:
        x_inlet = max(1, int(round(zone.nx * 0.18)))
        for rack in zone.racks.values():
            y0 = max(0, rack.y_idx - 1)
            y1 = min(zone.ny, rack.y_idx + 2)
            inlet_slice = zone.temperature_c[x_inlet : x_inlet + 2, y0:y1]
            if inlet_slice.size > 0:
                rack.inlet_temp_c = float(np.mean(inlet_slice))
            target_cpu_temp_c = (
                rack.inlet_temp_c + rack.power_w * self.cpu_thermal_resistance_k_per_w
            )
            rack.cpu_temp_c += (
                dt_s * (target_cpu_temp_c - rack.cpu_temp_c) / self.cpu_tau_s
            )

    def _sync_heat_sources_with_racks(self, zone) -> None:
        for source in zone.heat_sources:
            rack_id = source.id.removesuffix("_heat")
            rack = zone.racks.get(rack_id)
            if rack is not None:
                source.power_w = rack.power_w
