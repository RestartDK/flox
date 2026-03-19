from __future__ import annotations

from ml.simulation.kernels.base import Kernel
from ml.simulation.state import SimulationState


class CascadePropagationKernel(Kernel):
    name = "cascade_propagation"

    def __init__(
        self,
        *,
        throttle_temp_c: float = 85.0,
        shutdown_temp_c: float = 100.0,
        recovery_temp_c: float = 78.0,
        throttle_power_factor: float = 0.68,
        shutdown_power_factor: float = 0.20,
    ) -> None:
        self.throttle_temp_c = throttle_temp_c
        self.shutdown_temp_c = shutdown_temp_c
        self.recovery_temp_c = recovery_temp_c
        self.throttle_power_factor = throttle_power_factor
        self.shutdown_power_factor = shutdown_power_factor

    def apply(self, state: SimulationState) -> SimulationState:
        event_last_time = state.metadata.setdefault("event_last_time", {})
        for zone_id, zone in state.zones.items():
            avg_temp = zone.average_temp_c()
            if avg_temp >= 34.0:
                self._record_once(
                    state,
                    event_last_time,
                    key=f"zone_overtemp:{zone_id}",
                    message=f"{zone_id} average temperature reached {avg_temp:.1f}C",
                    min_interval_s=30.0,
                )

            for rack in zone.racks.values():
                if rack.shutdown:
                    continue
                if rack.cpu_temp_c >= self.shutdown_temp_c:
                    rack.shutdown = True
                    rack.throttled = True
                    rack.power_w *= self.shutdown_power_factor
                    self._record_once(
                        state,
                        event_last_time,
                        key=f"shutdown:{rack.id}",
                        message=f"{rack.id} entered emergency shutdown at {rack.cpu_temp_c:.1f}C",
                        min_interval_s=1e9,
                    )
                    continue

                if rack.cpu_temp_c >= self.throttle_temp_c and not rack.throttled:
                    rack.throttled = True
                    rack.power_w *= self.throttle_power_factor
                    self._record_once(
                        state,
                        event_last_time,
                        key=f"throttle:{rack.id}",
                        message=f"{rack.id} throttled at {rack.cpu_temp_c:.1f}C",
                        min_interval_s=1e9,
                    )
                    continue

                if rack.cpu_temp_c <= self.recovery_temp_c and rack.throttled:
                    rack.throttled = False
                    rack.power_w /= max(self.throttle_power_factor, 1e-6)
                    self._record_once(
                        state,
                        event_last_time,
                        key=f"recovery:{rack.id}",
                        message=f"{rack.id} recovered from throttling at {rack.cpu_temp_c:.1f}C",
                        min_interval_s=120.0,
                    )

        return state

    def _record_once(
        self,
        state: SimulationState,
        event_last_time: dict[str, float],
        *,
        key: str,
        message: str,
        min_interval_s: float,
    ) -> None:
        last_time = event_last_time.get(key, -1e9)
        if state.time_s - last_time >= min_interval_s:
            state.record_event(message)
            event_last_time[key] = state.time_s
