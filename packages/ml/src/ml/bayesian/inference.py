from __future__ import annotations

from dataclasses import dataclass
import math

from ml.bayesian.network import (
    BayesianEdge,
    BayesianGraph,
    BayesianNode,
    build_datacenter_bayesian_graph,
)


@dataclass(slots=True)
class BayesianInferenceResult:
    node_probabilities: dict[str, float]
    top_risks: list[tuple[str, float]]
    summary: dict[str, float | str]
    graph: BayesianGraph


def run_datacenter_inference(
    component_failure_priors: dict[str, float],
    simulation_context: dict[str, float],
) -> BayesianInferenceResult:
    graph = build_datacenter_bayesian_graph()
    probs: dict[str, float] = {}

    for node in graph.nodes:
        if node.kind == "component_failure":
            probs[node.id] = _clamp(component_failure_priors.get(node.id, 0.02))

    incoming_by_target: dict[str, list[BayesianEdge]] = {}
    for edge in graph.edges:
        incoming_by_target.setdefault(edge.target, []).append(edge)

    ordered_layers = ["flow", "zone", "equipment", "system"]
    for layer in ordered_layers:
        for node in graph.nodes:
            if node.layer != layer:
                continue
            contributions = []
            for edge in incoming_by_target.get(node.id, []):
                parent_p = probs.get(edge.source, 0.0)
                contributions.append(parent_p * edge.weight)
            base = 0.02 if layer in {"flow", "zone"} else 0.01
            probs[node.id] = _noisy_or(contributions, base_prob=base)

    probs = _blend_with_simulation_signal(probs, simulation_context)

    top_risks = sorted(probs.items(), key=lambda item: item[1], reverse=True)[:6]
    most_at_risk_zone = max(
        ["r_zone_ab", "r_zone_cd", "r_zone_ef"],
        key=lambda zone_id: probs.get(zone_id, 0.0),
    )
    summary = {
        "cpu_throttling_probability": round(probs.get("r_cpu", 0.0), 4),
        "service_degradation_probability": round(probs.get("r_service", 0.0), 4),
        "most_at_risk_zone": most_at_risk_zone.removeprefix("r_").upper(),
    }
    return BayesianInferenceResult(
        node_probabilities={key: round(value, 4) for key, value in probs.items()},
        top_risks=[
            (node_id, round(probability, 4)) for node_id, probability in top_risks
        ],
        summary=summary,
        graph=graph,
    )


def serialize_bayesian_result(result: BayesianInferenceResult) -> dict[str, object]:
    node_lookup: dict[str, BayesianNode] = {
        node.id: node for node in result.graph.nodes
    }
    nodes_payload = []
    for node in result.graph.nodes:
        nodes_payload.append(
            {
                "id": node.id,
                "label": node.label,
                "layer": node.layer,
                "kind": node.kind,
                "probability": result.node_probabilities.get(node.id, 0.0),
            }
        )

    top_risks_payload = []
    for node_id, probability in result.top_risks:
        node = node_lookup.get(node_id)
        top_risks_payload.append(
            {
                "id": node_id,
                "label": node.label if node is not None else node_id,
                "probability": probability,
            }
        )

    return {
        "nodes": nodes_payload,
        "edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "weight": round(edge.weight, 4),
            }
            for edge in result.graph.edges
        ],
        "topRisks": top_risks_payload,
        "summary": result.summary,
    }


def _blend_with_simulation_signal(
    probs: dict[str, float],
    simulation_context: dict[str, float],
) -> dict[str, float]:
    candidate_cpu_peak = simulation_context.get("candidate_cpu_peak_c", 0.0)
    baseline_cpu_peak = simulation_context.get("baseline_cpu_peak_c", 0.0)
    cpu_delta = max(0.0, candidate_cpu_peak - baseline_cpu_peak)
    max_zone_delta = max(0.0, simulation_context.get("max_zone_peak_delta_c", 0.0))
    thermal_pressure = _sigmoid((candidate_cpu_peak - 80.0) * 0.22)
    delta_pressure = _sigmoid((cpu_delta + max_zone_delta) * 3.8)

    probs["r_cpu"] = _blend_prob(probs.get("r_cpu", 0.0), thermal_pressure, weight=0.48)
    probs["r_service"] = _blend_prob(
        probs.get("r_service", 0.0), delta_pressure, weight=0.34
    )

    zone_map = {
        "zone_ab": "r_zone_ab",
        "zone_cd": "r_zone_cd",
        "zone_ef": "r_zone_ef",
    }
    for zone_key, node_id in zone_map.items():
        delta = simulation_context.get(f"zone_peak_delta_{zone_key}_c", 0.0)
        if delta <= 0:
            continue
        evidence = _sigmoid((delta - 0.2) * 2.8)
        probs[node_id] = _blend_prob(probs.get(node_id, 0.0), evidence, weight=0.42)

    return {node_id: _clamp(prob) for node_id, prob in probs.items()}


def _noisy_or(contributions: list[float], *, base_prob: float) -> float:
    survival = 1.0 - _clamp(base_prob)
    for contribution in contributions:
        survival *= 1.0 - _clamp(contribution)
    return _clamp(1.0 - survival)


def _blend_prob(base: float, evidence: float, *, weight: float) -> float:
    safe_weight = _clamp(weight)
    return _clamp(base * (1.0 - safe_weight) + evidence * safe_weight)


def _sigmoid(value: float) -> float:
    if value >= 0:
        exp_term = math.exp(-value)
        return 1.0 / (1.0 + exp_term)
    exp_term = math.exp(value)
    return exp_term / (1.0 + exp_term)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
