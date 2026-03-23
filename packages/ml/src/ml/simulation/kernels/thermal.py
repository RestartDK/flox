from __future__ import annotations

import numpy as np

from ml.simulation.kernels.base import Kernel
from ml.simulation.state import SimulationState

_RHO = 1.2
_CP = 1005.0


class ThermalPropagationKernel(Kernel):
    """
    Two-compartment thermal model (cold aisle + hot aisle) with grid sampling.

    This avoids hard-coded row offsets and produces granular temperatures from
    simulated airflow, recirculation, and rack heat.
    """

    name = "thermal_propagation"

    def __init__(
        self,
        *,
        tau_cold_s: float = 35.0,
        tau_hot_s: float = 45.0,
        tau_cpu_s: float = 55.0,
    ) -> None:
        self.tau_cold_s = tau_cold_s
        self.tau_hot_s = tau_hot_s
        self.tau_cpu_s = tau_cpu_s

    def apply(self, state: SimulationState) -> SimulationState:
        dt = state.dt_s
        for zone in state.zones.values():
            sf = max(zone.supply_flow_m3s, 1e-6)
            ef = zone.exhaust_flow_m3s

            m_dot = max(_RHO * sf, 1e-4)
            p_total = sum(r.power_w for r in zone.racks.values())

            # Ideal exhaust temperature if all heat is convected away.
            t_exhaust_ideal = zone.supply_temp_c + p_total / (m_dot * _CP)

            # Exhaust restriction drives hot-air recirculation into cold aisle.
            recirc = float(np.clip(1.0 - ef / sf, 0.0, 0.92))
            zone.recirculation_fraction = recirc

            t_cold_inlet_target = (
                1.0 - recirc
            ) * zone.supply_temp_c + recirc * zone.hot_aisle_temp_c
            heat_delta = p_total / (m_dot * _CP)
            t_cold_target = t_cold_inlet_target + 0.22 * heat_delta
            t_hot_target = t_cold_target + 0.78 * heat_delta + 1.8 * recirc

            alpha_cold = dt / (self.tau_cold_s + dt)
            alpha_hot = dt / (self.tau_hot_s + dt)
            zone.cold_aisle_temp_c = (
                zone.cold_aisle_temp_c * (1.0 - alpha_cold) + t_cold_target * alpha_cold
            )
            zone.hot_aisle_temp_c = (
                zone.hot_aisle_temp_c * (1.0 - alpha_hot) + t_hot_target * alpha_hot
            )

            # Update 2D field: cold->hot gradient + local rack hotspots.
            x_gradient = np.linspace(
                zone.cold_aisle_temp_c,
                zone.hot_aisle_temp_c,
                zone.nx,
                dtype=float,
            )[:, None]
            zone.temperature_c = 0.82 * zone.temperature_c + 0.18 * x_gradient
            x_hot = min(zone.nx - 2, max(1, int(round(zone.nx * 0.58))))
            for rack in zone.racks.values():
                y = rack.y_idx
                y0 = max(0, y - 1)
                y1 = min(zone.ny, y + 2)
                zone.temperature_c[x_hot : x_hot + 2, y0:y1] += 0.015 * (
                    rack.power_w / 1000.0
                )
            zone.temperature_c = np.clip(
                zone.temperature_c, zone.ambient_c - 8.0, 120.0
            )

            # Per-rack inlet and CPU temperatures sampled from the grid.
            n_racks = max(len(zone.racks), 1)
            m_dot_per_rack = m_dot / n_racks
            alpha_cpu = dt / (self.tau_cpu_s + dt)
            x_inlet = min(zone.nx - 2, max(1, int(round(zone.nx * 0.18))))
            for rack in zone.racks.values():
                y = rack.y_idx
                y0 = max(0, y - 1)
                y1 = min(zone.ny, y + 2)
                rack.inlet_temp_c = float(
                    np.mean(zone.temperature_c[x_inlet : x_inlet + 2, y0:y1])
                )
                t_cpu_target = rack.inlet_temp_c + rack.power_w / max(
                    m_dot_per_rack * _CP,
                    1e-3,
                )
                rack.cpu_temp_c = (
                    rack.cpu_temp_c * (1.0 - alpha_cpu) + t_cpu_target * alpha_cpu
                )

        return state
