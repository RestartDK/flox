from __future__ import annotations

from dataclasses import dataclass

from ml.simulation.kernels.base import Kernel, LinearKernelPipeline
from ml.simulation.state import FailureEvent, SimulationState, StepMetrics, clone_state


@dataclass(slots=True)
class SimulationResult:
    scenario_name: str
    duration_s: float
    dt_s: float
    times_s: list[float]
    zone_avg_temp_c: dict[str, list[float]]
    zone_cold_aisle_temp_c: dict[str, list[float]]
    zone_hot_aisle_temp_c: dict[str, list[float]]
    zone_recirculation_fraction: dict[str, list[float]]
    zone_supply_flow_m3s: dict[str, list[float]]
    zone_exhaust_flow_m3s: dict[str, list[float]]
    rack_cpu_temp_c: dict[str, list[float]]
    rack_inlet_temp_c: dict[str, list[float]]
    max_cpu_temp_c: list[float]
    throttled_cpu_count: list[int]
    shutdown_cpu_count: list[int]
    events: list[str]
    final_state: SimulationState

    def peak_zone_temp_c(self, zone_id: str) -> float:
        values = self.zone_avg_temp_c.get(zone_id, [])
        return max(values) if values else 0.0


class SimulationEngine:
    def __init__(self, kernels: list[Kernel]) -> None:
        self.pipeline = LinearKernelPipeline(kernels)

    def step(self, state: SimulationState) -> SimulationState:
        state = self.pipeline.step(state)
        state.time_s += state.dt_s
        state.history.append(self._collect_metrics(state))
        return state

    def run(
        self,
        state: SimulationState,
        *,
        duration_s: float,
        scenario_name: str = "scenario",
    ) -> SimulationResult:
        state.history.clear()
        state.history.append(self._collect_metrics(state))
        step_count = max(1, int(round(duration_s / state.dt_s)))
        for _ in range(step_count):
            self.step(state)
        return self._build_result(
            state=state, scenario_name=scenario_name, duration_s=duration_s
        )

    def run_scenario(
        self,
        initial_state: SimulationState,
        *,
        scenario_name: str,
        duration_s: float,
        failures: list[FailureEvent] | None = None,
    ) -> SimulationResult:
        state = clone_state(initial_state)
        state.active_failures = list(failures or [])
        return self.run(state, duration_s=duration_s, scenario_name=scenario_name)

    def _collect_metrics(self, state: SimulationState) -> StepMetrics:
        zone_avg_temp_c = {
            zone_id: zone.average_temp_c() for zone_id, zone in state.zones.items()
        }
        zone_cold_aisle_temp_c = {
            zone_id: zone.cold_aisle_temp_c for zone_id, zone in state.zones.items()
        }
        zone_hot_aisle_temp_c = {
            zone_id: zone.hot_aisle_temp_c for zone_id, zone in state.zones.items()
        }
        zone_recirculation_fraction = {
            zone_id: zone.recirculation_fraction
            for zone_id, zone in state.zones.items()
        }
        zone_supply_flow_m3s = {
            zone_id: zone.supply_flow_m3s for zone_id, zone in state.zones.items()
        }
        zone_exhaust_flow_m3s = {
            zone_id: zone.exhaust_flow_m3s for zone_id, zone in state.zones.items()
        }
        cpu_temps: list[float] = []
        rack_cpu_temp_c: dict[str, float] = {}
        rack_inlet_temp_c: dict[str, float] = {}
        throttled = 0
        shutdown = 0
        for zone in state.zones.values():
            for rack in zone.racks.values():
                cpu_temps.append(rack.cpu_temp_c)
                rack_cpu_temp_c[rack.id] = rack.cpu_temp_c
                rack_inlet_temp_c[rack.id] = rack.inlet_temp_c
                if rack.throttled:
                    throttled += 1
                if rack.shutdown:
                    shutdown += 1
        max_cpu_temp_c = max(cpu_temps) if cpu_temps else 0.0
        return StepMetrics(
            time_s=state.time_s,
            zone_avg_temp_c=zone_avg_temp_c,
            zone_cold_aisle_temp_c=zone_cold_aisle_temp_c,
            zone_hot_aisle_temp_c=zone_hot_aisle_temp_c,
            zone_recirculation_fraction=zone_recirculation_fraction,
            zone_supply_flow_m3s=zone_supply_flow_m3s,
            zone_exhaust_flow_m3s=zone_exhaust_flow_m3s,
            rack_cpu_temp_c=rack_cpu_temp_c,
            rack_inlet_temp_c=rack_inlet_temp_c,
            max_cpu_temp_c=max_cpu_temp_c,
            throttled_cpu_count=throttled,
            shutdown_cpu_count=shutdown,
        )

    def _build_result(
        self,
        *,
        state: SimulationState,
        scenario_name: str,
        duration_s: float,
    ) -> SimulationResult:
        times_s = [metric.time_s for metric in state.history]
        zone_ids = list(state.zones.keys())
        zone_avg_temp_c = {
            zone_id: [metric.zone_avg_temp_c[zone_id] for metric in state.history]
            for zone_id in zone_ids
        }
        zone_cold_aisle_temp_c = {
            zone_id: [
                metric.zone_cold_aisle_temp_c[zone_id] for metric in state.history
            ]
            for zone_id in zone_ids
        }
        zone_hot_aisle_temp_c = {
            zone_id: [metric.zone_hot_aisle_temp_c[zone_id] for metric in state.history]
            for zone_id in zone_ids
        }
        zone_recirculation_fraction = {
            zone_id: [
                metric.zone_recirculation_fraction[zone_id] for metric in state.history
            ]
            for zone_id in zone_ids
        }
        zone_supply_flow_m3s = {
            zone_id: [metric.zone_supply_flow_m3s[zone_id] for metric in state.history]
            for zone_id in zone_ids
        }
        zone_exhaust_flow_m3s = {
            zone_id: [metric.zone_exhaust_flow_m3s[zone_id] for metric in state.history]
            for zone_id in zone_ids
        }
        rack_ids = (
            list(state.history[0].rack_cpu_temp_c.keys()) if state.history else []
        )
        rack_cpu_temp_c = {
            rack_id: [
                metric.rack_cpu_temp_c.get(rack_id, 0.0) for metric in state.history
            ]
            for rack_id in rack_ids
        }
        rack_inlet_temp_c = {
            rack_id: [
                metric.rack_inlet_temp_c.get(rack_id, 0.0) for metric in state.history
            ]
            for rack_id in rack_ids
        }
        return SimulationResult(
            scenario_name=scenario_name,
            duration_s=duration_s,
            dt_s=state.dt_s,
            times_s=times_s,
            zone_avg_temp_c=zone_avg_temp_c,
            zone_cold_aisle_temp_c=zone_cold_aisle_temp_c,
            zone_hot_aisle_temp_c=zone_hot_aisle_temp_c,
            zone_recirculation_fraction=zone_recirculation_fraction,
            zone_supply_flow_m3s=zone_supply_flow_m3s,
            zone_exhaust_flow_m3s=zone_exhaust_flow_m3s,
            rack_cpu_temp_c=rack_cpu_temp_c,
            rack_inlet_temp_c=rack_inlet_temp_c,
            max_cpu_temp_c=[metric.max_cpu_temp_c for metric in state.history],
            throttled_cpu_count=[
                metric.throttled_cpu_count for metric in state.history
            ],
            shutdown_cpu_count=[metric.shutdown_cpu_count for metric in state.history],
            events=list(state.events),
            final_state=state,
        )
