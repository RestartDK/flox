from __future__ import annotations

from ml.simulation.scenarios import (
    build_default_engine,
    default_scenarios,
    discovery_report,
)
from ml.simulation.topology import build_datacenter_topology, build_initial_state


def _run_named_scenario(name: str, *, duration_s: float = 600.0):
    topology = build_datacenter_topology()
    scenario = default_scenarios(duration_s=duration_s)[name]
    engine = build_default_engine(topology)
    initial_state = build_initial_state(topology, dt_s=1.0)
    return engine.run_scenario(
        initial_state,
        scenario_name=scenario.name,
        duration_s=scenario.duration_s,
        failures=scenario.failures,
    )


def test_exhaust_damper_failure_propagates_to_zone_temperatures_and_cpus():
    baseline = _run_named_scenario("baseline", duration_s=600.0)
    failing = _run_named_scenario("dmp_ef_stuck", duration_s=600.0)

    deltas = {
        zone_id: failing.peak_zone_temp_c(zone_id) - baseline.peak_zone_temp_c(zone_id)
        for zone_id in baseline.zone_avg_temp_c.keys()
    }
    assert max(deltas.values()) > 0.1
    assert max(failing.max_cpu_temp_c) >= max(baseline.max_cpu_temp_c)


def test_discovery_report_exposes_temperature_delta():
    baseline = _run_named_scenario("baseline", duration_s=600.0)
    failing = _run_named_scenario("dmp_ef_stuck", duration_s=600.0)
    report = discovery_report(baseline, failing)

    assert report["max_zone_peak_delta_c"] > 0.0
    assert report["cpu_peak_delta_c"] >= 0.0
