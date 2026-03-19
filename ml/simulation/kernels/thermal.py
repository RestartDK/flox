from __future__ import annotations

import numpy as np

from ml.simulation.kernels.base import Kernel
from ml.simulation.state import SimulationState

_RHO = 1.2
_CP = 1005.0


class ThermalPropagationKernel(Kernel):
    """
    Zone energy-balance thermal model.

    Hot-aisle/cold-aisle geometry is captured via:

        T_exhaust = T_inlet + P_total / (m_dot * cp)

    When exhaust is blocked, hot air recirculates back to the inlet:

        T_inlet_eff = lerp(T_supply, T_exhaust, recirculation_fraction)
        recirculation_fraction = max(0, 1 - exhaust_flow / supply_flow)

    Zone average temperature and CPU temperatures each track their targets
    with first-order RC dynamics. No spatial grid — runs in < 0.1 ms per step.
    """

    name = "thermal_propagation"

    def __init__(self, *, tau_zone_s: float = 45.0, tau_cpu_s: float = 55.0) -> None:
        self.tau_zone_s = tau_zone_s
        self.tau_cpu_s = tau_cpu_s

    def apply(self, state: SimulationState) -> SimulationState:
        dt = state.dt_s
        for zone in state.zones.values():
            sf = max(zone.supply_flow_m3s, 1e-6)
            ef = zone.exhaust_flow_m3s

            m_dot = _RHO * sf
            p_total = sum(r.power_w for r in zone.racks.values())

            # Temperature of air leaving via hot aisle (no recirculation)
            t_exhaust_ideal = zone.supply_temp_c + p_total / (m_dot * _CP)

            # Recirculation fraction: when exhaust damper is restricted, hot air
            # flows back into the cold aisle inlet
            recirc = float(np.clip(1.0 - ef / sf, 0.0, 0.92))
            t_inlet_eff = (1.0 - recirc) * zone.supply_temp_c + recirc * t_exhaust_ideal

            # Zone average temperature (between cold aisle inlet and hot aisle)
            t_zone_target = (t_inlet_eff + t_exhaust_ideal) * 0.5
            alpha_z = dt / (self.tau_zone_s + dt)
            delta = t_zone_target * alpha_z - zone.average_temp_c() * alpha_z
            zone.temperature_c += delta

            # Per-rack CPU temperature
            n_racks = max(len(zone.racks), 1)
            m_dot_per_rack = m_dot / n_racks
            alpha_c = dt / (self.tau_cpu_s + dt)
            for rack in zone.racks.values():
                rack.inlet_temp_c = t_inlet_eff
                t_cpu_target = t_inlet_eff + rack.power_w / max(
                    m_dot_per_rack * _CP, 1e-3
                )
                rack.cpu_temp_c = (
                    rack.cpu_temp_c * (1.0 - alpha_c) + t_cpu_target * alpha_c
                )
        return state
