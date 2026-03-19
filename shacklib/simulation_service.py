from __future__ import annotations

from typing import Any

from ml.bayesian import (
    build_component_failure_priors,
    run_datacenter_inference,
    serialize_bayesian_result,
)
from ml.simulation import (
    FailureEvent,
    build_datacenter_topology,
    build_default_engine,
    build_initial_state,
    discovery_report,
)


COMPONENT_TO_DEVICE_ID = {
    "act_intake": "BEL-ACT-001",
    "dmp_ab": "BEL-DMP-002",
    "vlv_ab": "BEL-VLV-003",
    "act_cd_exhaust": "BEL-ACT-004",
    "vlv_cd": "BEL-VLV-005",
    "dmp_ef": "BEL-DMP-006",
    "act_ef_supply": "BEL-ACT-007",
    "dmp_outlet": "BEL-DMP-008",
}

DEVICE_TO_COMPONENT_ID = {
    device_id: component_id
    for component_id, device_id in COMPONENT_TO_DEVICE_ID.items()
}


def run_simulation_bundle(
    *,
    duration_seconds: float,
    dt_seconds: float,
    failures_payload: list[dict[str, Any]],
    status_payload: dict[str, Any] | None,
    generated_at: str,
) -> dict[str, Any]:
    effective_failures = (
        failures_payload
        if failures_payload
        else _infer_failures_from_status(status_payload)
    )
    failure_events = [_to_failure_event(item) for item in effective_failures]

    topology = build_datacenter_topology()
    baseline_state = build_initial_state(topology, dt_s=dt_seconds)
    candidate_state = build_initial_state(topology, dt_s=dt_seconds)

    baseline_engine = build_default_engine(topology)
    candidate_engine = build_default_engine(topology)
    baseline_result = baseline_engine.run_scenario(
        baseline_state,
        scenario_name="baseline",
        duration_s=duration_seconds,
        failures=[],
    )
    candidate_result = candidate_engine.run_scenario(
        candidate_state,
        scenario_name="candidate",
        duration_s=duration_seconds,
        failures=failure_events,
    )

    discovery = discovery_report(baseline_result, candidate_result)
    simulation_context = _build_simulation_context(discovery)
    candidate_component_priors = build_component_failure_priors(
        requested_failures=effective_failures,
        status_payload=status_payload,
    )
    baseline_component_priors = build_component_failure_priors(
        requested_failures=[],
        status_payload=None,
    )
    baseline_bayesian_result = run_datacenter_inference(
        component_failure_priors=baseline_component_priors,
        simulation_context={},
    )
    candidate_bayesian_result = run_datacenter_inference(
        component_failure_priors=candidate_component_priors,
        simulation_context=simulation_context,
    )
    bayesian = serialize_bayesian_result(candidate_bayesian_result)
    bayesian["summary"] = _build_bayesian_summary_with_delta(
        baseline_serialized=serialize_bayesian_result(baseline_bayesian_result),
        candidate_serialized=bayesian,
    )

    status_node_positions = _extract_status_node_positions(status_payload)
    node_positions_timeline = _build_node_positions_timeline(
        status_node_positions,
        baseline_result.zone_supply_flow_m3s,
        baseline_result.zone_exhaust_flow_m3s,
        candidate_result.zone_supply_flow_m3s,
        candidate_result.zone_exhaust_flow_m3s,
    )

    timeline = {
        "timesSeconds": [round(value, 3) for value in candidate_result.times_s],
        "zoneTemperatures": {
            zone_id: [round(value, 4) for value in series]
            for zone_id, series in candidate_result.zone_avg_temp_c.items()
        },
        "rowTemperatures": _build_row_temperatures(candidate_result.zone_avg_temp_c),
        "zoneSupplyFlows": {
            zone_id: [round(value, 6) for value in series]
            for zone_id, series in candidate_result.zone_supply_flow_m3s.items()
        },
        "zoneExhaustFlows": {
            zone_id: [round(value, 6) for value in series]
            for zone_id, series in candidate_result.zone_exhaust_flow_m3s.items()
        },
        "nodePositionsTimeline": node_positions_timeline,
        "maxCpuTemperature": [
            round(value, 4) for value in candidate_result.max_cpu_temp_c
        ],
        "throttledCpuCount": candidate_result.throttled_cpu_count,
        "shutdownCpuCount": candidate_result.shutdown_cpu_count,
    }

    return {
        "generatedAt": generated_at,
        "durationSeconds": duration_seconds,
        "dtSeconds": dt_seconds,
        "timeline": timeline,
        "discovery": discovery,
        "bayesian": bayesian,
        "events": candidate_result.events,
    }


def _build_bayesian_summary_with_delta(
    *,
    baseline_serialized: dict[str, Any],
    candidate_serialized: dict[str, Any],
) -> dict[str, Any]:
    baseline_summary = baseline_serialized.get("summary")
    candidate_summary = candidate_serialized.get("summary")
    if not isinstance(baseline_summary, dict) or not isinstance(
        candidate_summary, dict
    ):
        return candidate_summary if isinstance(candidate_summary, dict) else {}

    baseline_cpu = float(baseline_summary.get("cpu_throttling_probability") or 0.0)
    baseline_service = float(
        baseline_summary.get("service_degradation_probability") or 0.0
    )
    candidate_cpu = float(candidate_summary.get("cpu_throttling_probability") or 0.0)
    candidate_service = float(
        candidate_summary.get("service_degradation_probability") or 0.0
    )

    top_risks = candidate_serialized.get("topRisks")
    key_drivers: list[str] = []
    if isinstance(top_risks, list):
        for risk in top_risks[:3]:
            if isinstance(risk, dict):
                label = str(risk.get("label") or "").strip()
                probability = float(risk.get("probability") or 0.0)
                if label:
                    key_drivers.append(f"{label} ({round(probability * 100)}%)")

    return {
        **candidate_summary,
        "baseline_cpu_throttling_probability": round(baseline_cpu, 4),
        "baseline_service_degradation_probability": round(baseline_service, 4),
        "cpu_probability_delta": round(candidate_cpu - baseline_cpu, 4),
        "service_probability_delta": round(candidate_service - baseline_service, 4),
        "key_drivers": key_drivers,
    }


def _to_failure_event(payload: dict[str, Any]) -> FailureEvent:
    return FailureEvent(
        component_id=str(payload.get("componentId") or "").strip(),
        mode=str(payload.get("mode") or "unknown").strip(),
        severity=float(payload.get("severity") or 0.8),
        start_s=float(payload.get("startSeconds") or 0.0),
        end_s=float(payload["endSeconds"])
        if payload.get("endSeconds") is not None
        else None,
    )


def _infer_failures_from_status(
    status_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(status_payload, dict):
        return []
    nodes = status_payload.get("nodes")
    if not isinstance(nodes, list):
        return []

    inferred: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        component_id = DEVICE_TO_COMPONENT_ID.get(node_id)
        if component_id is None:
            continue
        status = str(node.get("status") or "").lower()
        fault_probability = 0.0
        fault = node.get("fault")
        if isinstance(fault, dict):
            fault_probability = float(fault.get("probability") or 0.0)
        if (
            status not in {"warning", "critical", "offline"}
            and fault_probability <= 0.0
        ):
            continue

        if status in {"critical", "offline"}:
            severity = 0.9
        elif status == "warning":
            severity = 0.55
        else:
            severity = 0.35
        if fault_probability > 0:
            severity = max(severity, min(1.0, 0.15 + fault_probability))

        inferred.append(
            {
                "componentId": component_id,
                "mode": "degraded",
                "severity": severity,
                "startSeconds": 0.0,
            }
        )

    return inferred


def _extract_status_node_positions(
    status_payload: dict[str, Any] | None,
) -> dict[str, float]:
    if not isinstance(status_payload, dict):
        return {}
    derived = status_payload.get("derived")
    if not isinstance(derived, dict):
        return {}
    node_positions = derived.get("nodePositions")
    if not isinstance(node_positions, dict):
        return {}
    result: dict[str, float] = {}
    for node_id, value in node_positions.items():
        try:
            result[str(node_id)] = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            continue
    return result


def _build_simulation_context(discovery: dict[str, Any]) -> dict[str, float]:
    context = {
        "baseline_cpu_peak_c": float(discovery.get("baseline_cpu_peak_c") or 0.0),
        "candidate_cpu_peak_c": float(discovery.get("candidate_cpu_peak_c") or 0.0),
        "max_zone_peak_delta_c": float(discovery.get("max_zone_peak_delta_c") or 0.0),
    }
    deltas = discovery.get("zone_peak_delta_by_zone")
    if isinstance(deltas, dict):
        for zone_id, value in deltas.items():
            try:
                context[f"zone_peak_delta_{zone_id}_c"] = float(value)
            except (TypeError, ValueError):
                continue
    return context


def _build_node_positions_timeline(
    status_node_positions: dict[str, float],
    baseline_supply: dict[str, list[float]],
    baseline_exhaust: dict[str, list[float]],
    candidate_supply: dict[str, list[float]],
    candidate_exhaust: dict[str, list[float]],
) -> list[dict[str, float]]:
    steps = len(next(iter(candidate_supply.values()), []))
    if steps <= 0:
        return []

    def _series_value(
        series_by_zone: dict[str, list[float]], zone_id: str, index: int
    ) -> float:
        series = series_by_zone.get(zone_id) or []
        if not series:
            return 0.0
        return float(series[min(index, len(series) - 1)])

    timeline: list[dict[str, float]] = []
    for index in range(steps):
        factors = {
            "zone_ab_supply": _ratio(
                _series_value(candidate_supply, "zone_ab", index),
                _series_value(baseline_supply, "zone_ab", index),
            ),
            "zone_cd_supply": _ratio(
                _series_value(candidate_supply, "zone_cd", index),
                _series_value(baseline_supply, "zone_cd", index),
            ),
            "zone_ef_supply": _ratio(
                _series_value(candidate_supply, "zone_ef", index),
                _series_value(baseline_supply, "zone_ef", index),
            ),
            "zone_ab_exhaust": _ratio(
                _series_value(candidate_exhaust, "zone_ab", index),
                _series_value(baseline_exhaust, "zone_ab", index),
            ),
            "zone_cd_exhaust": _ratio(
                _series_value(candidate_exhaust, "zone_cd", index),
                _series_value(baseline_exhaust, "zone_cd", index),
            ),
            "zone_ef_exhaust": _ratio(
                _series_value(candidate_exhaust, "zone_ef", index),
                _series_value(baseline_exhaust, "zone_ef", index),
            ),
        }

        timeline.append(
            {
                "BEL-ACT-001": _scale_position(
                    status_node_positions,
                    "BEL-ACT-001",
                    (
                        factors["zone_ab_supply"]
                        + factors["zone_cd_supply"]
                        + factors["zone_ef_supply"]
                    )
                    / 3.0,
                ),
                "BEL-VLV-003": _scale_position(
                    status_node_positions, "BEL-VLV-003", factors["zone_ab_supply"]
                ),
                "BEL-VLV-005": _scale_position(
                    status_node_positions, "BEL-VLV-005", factors["zone_cd_supply"]
                ),
                "BEL-ACT-007": _scale_position(
                    status_node_positions, "BEL-ACT-007", factors["zone_ef_supply"]
                ),
                "BEL-DMP-002": _scale_position(
                    status_node_positions, "BEL-DMP-002", factors["zone_ab_exhaust"]
                ),
                "BEL-ACT-004": _scale_position(
                    status_node_positions, "BEL-ACT-004", factors["zone_cd_exhaust"]
                ),
                "BEL-DMP-006": _scale_position(
                    status_node_positions, "BEL-DMP-006", factors["zone_ef_exhaust"]
                ),
                "BEL-DMP-008": _scale_position(
                    status_node_positions,
                    "BEL-DMP-008",
                    (
                        factors["zone_ab_exhaust"]
                        + factors["zone_cd_exhaust"]
                        + factors["zone_ef_exhaust"]
                    )
                    / 3.0,
                ),
            }
        )

    return timeline


def _scale_position(
    status_node_positions: dict[str, float], node_id: str, factor: float
) -> float:
    base = status_node_positions.get(node_id, 0.7)
    return round(max(0.02, min(1.0, base * factor)), 5)


def _build_row_temperatures(
    zone_temps: dict[str, list[float]],
) -> dict[str, list[float]]:
    zone_ab = zone_temps.get("zone_ab") or []
    zone_cd = zone_temps.get("zone_cd") or []
    zone_ef = zone_temps.get("zone_ef") or []
    step_count = max(len(zone_ab), len(zone_cd), len(zone_ef))

    def _at(series: list[float], index: int, fallback: float) -> float:
        if not series:
            return fallback
        return float(series[min(index, len(series) - 1)])

    rows = {
        "row_a": [],
        "row_b": [],
        "row_c": [],
        "row_d": [],
        "row_e": [],
        "row_f": [],
    }
    for index in range(step_count):
        ab = _at(zone_ab, index, 24.0)
        cd = _at(zone_cd, index, 24.0)
        ef = _at(zone_ef, index, 24.0)
        rows["row_a"].append(round(ab - 4.6, 4))
        rows["row_b"].append(round(ab + 4.4, 4))
        rows["row_c"].append(round(cd - 4.5, 4))
        rows["row_d"].append(round(cd + 4.5, 4))
        rows["row_e"].append(round(ef - 4.1, 4))
        rows["row_f"].append(round(ef + 5.2, 4))

    return rows


def _ratio(numerator: float, denominator: float) -> float:
    safe_denominator = denominator if abs(denominator) > 1e-9 else 1.0
    return max(0.05, min(1.4, numerator / safe_denominator))
