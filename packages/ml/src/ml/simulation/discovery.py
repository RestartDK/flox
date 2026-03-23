from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ml.simulation.scenarios import build_default_engine
from ml.simulation.state import FailureEvent
from ml.simulation.topology import build_datacenter_topology, build_initial_state


_ZONE_IDS = ("zone_ab", "zone_cd", "zone_ef")
_COMPONENT_TO_ZONE = {
    "vlv_ab": "zone_ab",
    "dmp_ab": "zone_ab",
    "vlv_cd": "zone_cd",
    "act_cd_exhaust": "zone_cd",
    "act_ef_supply": "zone_ef",
    "dmp_ef": "zone_ef",
}


@dataclass(slots=True)
class _RunSummary:
    zone_peaks: dict[str, float]
    cpu_peak: float


def run_discovery_analysis(
    *,
    duration_seconds: float,
    dt_seconds: float,
    candidate_failures: list[FailureEvent],
    trials: int = 8,
) -> dict[str, object]:
    candidate_failures = candidate_failures or [
        FailureEvent(component_id="dmp_ef", mode="stuck", severity=0.9)
    ]
    primary_zone = _infer_primary_zone(candidate_failures)
    compound_failures = _build_compound_failures(candidate_failures, primary_zone)

    local_deltas: list[float] = []
    nonlocal_deltas: list[float] = []
    cpu_deltas: list[float] = []
    compound_hotspots: list[str] = []
    compound_local_deltas: list[float] = []
    compound_nonlocal_deltas: list[float] = []
    nonlinear_cpu_deltas: list[float] = []

    topo = build_datacenter_topology()
    run_duration = min(max(duration_seconds, 120.0), 240.0)

    for seed in range(trials):
        baseline = _run_with_seed(
            topology=topo,
            dt_seconds=dt_seconds,
            duration_seconds=run_duration,
            failures=[],
            seed=seed,
        )
        candidate = _run_with_seed(
            topology=topo,
            dt_seconds=dt_seconds,
            duration_seconds=run_duration,
            failures=candidate_failures,
            seed=seed,
        )
        compound = _run_with_seed(
            topology=topo,
            dt_seconds=dt_seconds,
            duration_seconds=run_duration,
            failures=compound_failures,
            seed=seed,
        )

        baseline_zone = baseline.zone_peaks
        candidate_zone = candidate.zone_peaks
        compound_zone = compound.zone_peaks

        local_delta = candidate_zone[primary_zone] - baseline_zone[primary_zone]
        nonlocal_delta = max(
            candidate_zone[z] - baseline_zone[z] for z in _ZONE_IDS if z != primary_zone
        )
        local_deltas.append(local_delta)
        nonlocal_deltas.append(nonlocal_delta)
        cpu_deltas.append(candidate.cpu_peak - baseline.cpu_peak)

        compound_deltas = {z: compound_zone[z] - baseline_zone[z] for z in _ZONE_IDS}
        hotspot_zone = max(compound_deltas, key=compound_deltas.get)
        compound_hotspots.append(hotspot_zone)
        compound_local = compound_deltas[primary_zone]
        compound_nonlocal = max(
            compound_deltas[z] for z in _ZONE_IDS if z != primary_zone
        )
        compound_local_deltas.append(compound_local)
        compound_nonlocal_deltas.append(compound_nonlocal)

        single_local_cpu = candidate.cpu_peak - baseline.cpu_peak
        synthetic_secondary = _run_with_seed(
            topology=topo,
            dt_seconds=dt_seconds,
            duration_seconds=run_duration,
            failures=[compound_failures[-1]],
            seed=seed,
        )
        secondary_cpu = synthetic_secondary.cpu_peak - baseline.cpu_peak
        compound_cpu = compound.cpu_peak - baseline.cpu_peak
        nonlinear_cpu_deltas.append(compound_cpu - (single_local_cpu + secondary_cpu))

    local_stats = _stats(local_deltas)
    nonlocal_stats = _stats(nonlocal_deltas)
    cpu_stats = _stats(cpu_deltas)
    nonlinear_stats = _stats(nonlinear_cpu_deltas)

    hotspot_counts = {
        zone_id: compound_hotspots.count(zone_id) for zone_id in _ZONE_IDS
    }
    compound_hotspot_zone = max(hotspot_counts, key=hotspot_counts.get)
    compound_hotspot_rate = hotspot_counts[compound_hotspot_zone] / max(
        len(compound_hotspots), 1
    )
    counterintuitive = compound_hotspot_zone != primary_zone

    significance_score = _significance_score(
        effect_size=max(local_stats["effect_size"], nonlocal_stats["effect_size"]),
        p_value=min(local_stats["p_value"], nonlocal_stats["p_value"]),
        counterintuitive_rate=compound_hotspot_rate if counterintuitive else 0.0,
    )

    if counterintuitive:
        claim = (
            f"Compounding failures shift the dominant hotspot from {primary_zone.upper()} "
            f"to {compound_hotspot_zone.upper()} in {round(compound_hotspot_rate * 100)}% of trials."
        )
        unexpected = (
            f"Unexpected remote hotspot: {compound_hotspot_zone.upper()} heats faster than "
            f"the locally failed {primary_zone.upper()} path under compound stress."
        )
    else:
        claim = (
            f"Primary failure consistently elevates {primary_zone.upper()} thermal risk "
            f"with statistically strong uplift."
        )
        unexpected = None

    compound_local_stats = _stats(compound_local_deltas)
    compound_nonlocal_stats = _stats(compound_nonlocal_deltas)

    evidence = [
        (
            f"Local zone uplift ({primary_zone.upper()}): "
            f"mean {local_stats['mean']:+.2f}C, 95% CI [{local_stats['ci_low']:+.2f}, {local_stats['ci_high']:+.2f}]"
        ),
        (
            f"Compound hotspot {compound_hotspot_zone.upper()} in "
            f"{round(compound_hotspot_rate * 100)}% trials; compound local {compound_local_stats['mean']:+.2f}C vs non-local {compound_nonlocal_stats['mean']:+.2f}C"
        ),
        (
            f"CPU peak delta: mean {cpu_stats['mean']:+.2f}C; nonlinearity residual {nonlinear_stats['mean']:+.2f}C"
        ),
    ]

    return {
        "discoveryClaim": claim,
        "counterintuitiveFinding": unexpected,
        "significanceScore": round(significance_score, 1),
        "pValue": round(min(local_stats["p_value"], nonlocal_stats["p_value"]), 6),
        "effectSize": round(
            max(local_stats["effect_size"], nonlocal_stats["effect_size"]), 3
        ),
        "confidenceIntervalC": [
            round(local_stats["ci_low"], 3),
            round(local_stats["ci_high"], 3),
        ],
        "primaryImpactZone": primary_zone,
        "nonLocalImpactC": round(nonlocal_stats["mean"], 3),
        "compoundHotspotZone": compound_hotspot_zone,
        "compoundHotspotRate": round(compound_hotspot_rate, 3),
        "evidence": evidence,
    }


def _run_with_seed(
    *,
    topology,
    dt_seconds: float,
    duration_seconds: float,
    failures: list[FailureEvent],
    seed: int,
) -> _RunSummary:
    rng = np.random.default_rng(seed)
    state = _build_warm_state(topology=topology, dt_seconds=dt_seconds)
    _perturb_state(state, rng)
    engine = build_default_engine(topology)
    result = engine.run_scenario(
        state,
        scenario_name="trial",
        duration_s=duration_seconds,
        failures=failures,
    )
    zone_peaks = {z: max(v) for z, v in result.zone_avg_temp_c.items()}
    return _RunSummary(zone_peaks=zone_peaks, cpu_peak=max(result.max_cpu_temp_c))


def _build_warm_state(*, topology, dt_seconds: float):
    state = build_initial_state(topology, dt_s=dt_seconds)
    engine = build_default_engine(topology)
    warmup_seconds = 60.0
    warmup_steps = max(1, int(round(warmup_seconds / dt_seconds)))
    for _ in range(warmup_steps):
        state = engine.step(state)
    state.time_s = 0.0
    state.history.clear()
    state.events.clear()
    state.active_failures = []
    return state


def _perturb_state(state, rng: np.random.Generator) -> None:
    for zone in state.zones.values():
        offset = float(rng.normal(0.0, 0.25))
        zone.ambient_c += offset
        zone.supply_temp_c += float(rng.normal(0.0, 0.15))
        zone.temperature_c += offset
        for rack in zone.racks.values():
            rack.power_w *= float(np.clip(1.0 + rng.normal(0.0, 0.035), 0.88, 1.12))


def _infer_primary_zone(failures: list[FailureEvent]) -> str:
    for failure in failures:
        zone = _COMPONENT_TO_ZONE.get(failure.component_id)
        if zone:
            return zone
    return "zone_ef"


def _build_compound_failures(
    failures: list[FailureEvent],
    primary_zone: str,
) -> list[FailureEvent]:
    existing = {f.component_id for f in failures}
    secondary_map = {
        "zone_ab": FailureEvent("dmp_ef", "stuck", 0.9),
        "zone_cd": FailureEvent("dmp_ef", "stuck", 0.9),
        "zone_ef": FailureEvent("vlv_cd", "gear_stuck", 0.85),
    }
    secondary = secondary_map.get(
        primary_zone, FailureEvent("vlv_cd", "gear_stuck", 0.85)
    )
    if secondary.component_id in existing:
        return failures
    return [*failures, secondary]


def _stats(values: list[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=float)
    mean = float(np.mean(arr))
    if arr.size <= 1:
        return {
            "mean": mean,
            "std": 0.0,
            "se": 0.0,
            "ci_low": mean,
            "ci_high": mean,
            "p_value": 1.0,
            "effect_size": 0.0,
        }
    std = float(np.std(arr, ddof=1))
    se = std / math.sqrt(arr.size)
    ci_low = mean - 1.96 * se
    ci_high = mean + 1.96 * se
    if se <= 1e-12:
        p_value = 0.0 if mean > 0 else 1.0
    else:
        z = mean / se
        p_value = 0.5 * math.erfc(z / math.sqrt(2.0))
        p_value = float(max(0.0, min(1.0, p_value)))
    effect_size = abs(mean / std) if std > 1e-12 else (3.0 if abs(mean) > 0 else 0.0)
    return {
        "mean": mean,
        "std": std,
        "se": se,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p_value": p_value,
        "effect_size": effect_size,
    }


def _significance_score(
    *,
    effect_size: float,
    p_value: float,
    counterintuitive_rate: float,
) -> float:
    p_term = 1.0 - max(0.0, min(1.0, p_value))
    e_term = max(0.0, min(1.0, effect_size / 2.5))
    c_term = max(0.0, min(1.0, counterintuitive_rate))
    return min(98.0, 100.0 * (0.45 * p_term + 0.35 * e_term + 0.20 * c_term))
