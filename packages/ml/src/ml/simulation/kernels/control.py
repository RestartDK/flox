from __future__ import annotations

from ml.simulation.kernels.base import Kernel
from ml.simulation.state import ComponentState, SimulationState
from ml.simulation.topology import DatacenterTopology


class HVACControlKernel(Kernel):
    name = "hvac_control"

    def __init__(
        self,
        topology: DatacenterTopology,
        *,
        kp: float = 0.045,
        ki: float = 0.007,
        command_slew_per_s: float = 0.22,
    ) -> None:
        self.topology = topology
        self.kp = kp
        self.ki = ki
        self.command_slew_per_s = command_slew_per_s
        self.integral_error: dict[str, float] = {
            zone_id: 0.0 for zone_id in topology.zone_ids
        }

    def apply(self, state: SimulationState) -> SimulationState:
        dt_s = state.dt_s
        hottest_error = 0.0
        for zone_id in self.topology.zone_ids:
            zone = state.zones[zone_id]
            error = zone.average_temp_c() - zone.setpoint_c
            self.integral_error[zone_id] = max(
                -40.0,
                min(40.0, self.integral_error[zone_id] + error * dt_s),
            )
            command_delta = self.kp * error + self.ki * self.integral_error[zone_id]
            command_delta = max(
                -self.command_slew_per_s, min(self.command_slew_per_s, command_delta)
            )
            hottest_error = max(hottest_error, error)

            supply_component = state.components[
                self.topology.zone_supply_component[zone_id]
            ]
            exhaust_component = state.components[
                self.topology.zone_exhaust_component[zone_id]
            ]
            if not _is_hard_failure(supply_component.active_failure):
                supply_component.command_position += command_delta * dt_s
                supply_component.clamp_command()
            if not _is_hard_failure(exhaust_component.active_failure):
                exhaust_component.command_position += 0.9 * command_delta * dt_s
                exhaust_component.clamp_command()

        intake_component = state.components[self.topology.intake_component_id]
        outlet_component = state.components[self.topology.outlet_component_id]
        global_delta = max(-0.12, min(0.12, 0.03 * hottest_error))
        if not _is_hard_failure(intake_component.active_failure):
            intake_component.command_position += global_delta * dt_s
            intake_component.clamp_command()
        if not _is_hard_failure(outlet_component.active_failure):
            outlet_component.command_position += 0.8 * global_delta * dt_s
            outlet_component.clamp_command()

        return state


def _is_hard_failure(mode: str | None) -> bool:
    if mode is None:
        return False
    mode_key = mode.strip().lower().replace(" ", "_")
    return mode_key in {
        "gear_stuck",
        "stuck",
        "signal_loss",
        "offline",
        "transmission_lock",
    }
