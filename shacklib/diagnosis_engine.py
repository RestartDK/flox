from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

STATUS_RANK = {
    "healthy": 0,
    "warning": 1,
    "critical": 2,
}

RANK_STATUS = {
    0: "healthy",
    1: "warning",
    2: "critical",
}


def utc_now_iso() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z")


def to_utc_iso(value: datetime | str) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)

    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dedupe_ids(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _label_from_node_id(node_id: str) -> str:
    cleaned = node_id.replace("_", "-")
    parts = [part for part in cleaned.split("-") if part]

    if len(parts) >= 2 and parts[-1].isdigit():
        name = parts[-2]
        if name.lower() == "ahu":
            return f"AHU {parts[-1]}"
        return f"{name.capitalize()} {parts[-1]}"

    if parts and parts[0].lower() == "plant":
        return "Plant"

    return cleaned.replace("-", " ").title()


def _new_node(node_id: str, node_type: str, parent_ids: list[str]) -> dict[str, Any]:
    return {
        "id": node_id,
        "label": _label_from_node_id(node_id),
        "type": node_type,
        "status": "healthy",
        "parentIds": parent_ids,
        "latestTelemetry": {},
        "latestTelemetryAt": None,
        "latestFaultId": None,
        "updatedAt": utc_now_iso(),
    }


def ingest_node(state: dict[str, Any], payload: dict[str, Any]) -> None:
    nodes: dict[str, dict[str, Any]] = state.setdefault("nodes", {})

    node_id = payload["nodeId"]
    parent_ids = _dedupe_ids(payload.get("parentIds", []))
    timestamp = to_utc_iso(payload["timestamp"])

    node = nodes.get(node_id)
    if node is None:
        node = _new_node(
            node_id, str(payload.get("deviceType") or "device"), parent_ids
        )
        nodes[node_id] = node

    node["type"] = str(payload.get("deviceType") or node.get("type") or "device")
    node["parentIds"] = parent_ids
    node["latestTelemetry"] = payload.get("telemetry") or {}
    node["latestTelemetryAt"] = timestamp
    node["label"] = _label_from_node_id(node_id)
    node["updatedAt"] = utc_now_iso()
    node.setdefault("status", "healthy")
    node.setdefault("latestFaultId", None)

    for parent_id in parent_ids:
        if parent_id not in nodes:
            nodes[parent_id] = _new_node(parent_id, "system", [])

    state.setdefault("meta", {})["lastIngestAt"] = utc_now_iso()


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _clamp_probability(value: float) -> float:
    return round(max(0.5, min(0.99, value)), 2)


def _classify_node(node: dict[str, Any]) -> dict[str, Any] | None:
    telemetry = node.get("latestTelemetry") or {}
    node_type = str(node.get("type") or "").lower()

    torque = _as_float(telemetry.get("torque"))
    temperature = _as_float(telemetry.get("temperature"))
    signal = _as_float(telemetry.get("signal"))

    if node_type == "actuator" and torque is not None and torque >= 22:
        return {
            "status": "critical",
            "kind": "stiction_suspected",
            "probability": _clamp_probability(0.85 + (torque - 22) * 0.02),
            "summary": "Actuator movement is irregular and torque is elevated.",
            "recommendedAction": "Inspect for mechanical binding.",
        }

    if torque is not None and torque >= 16:
        return {
            "status": "warning",
            "kind": "high_torque_anomaly",
            "probability": _clamp_probability(0.72 + (torque - 16) * 0.03),
            "summary": "Torque is above expected range.",
            "recommendedAction": "Inspect linkage and valve stem.",
        }

    if temperature is not None and temperature >= 52:
        return {
            "status": "warning",
            "kind": "temperature_drift",
            "probability": _clamp_probability(0.7 + (temperature - 52) * 0.01),
            "summary": "Device temperature is above expected operating range.",
            "recommendedAction": "Check thermal load and actuator duty cycle.",
        }

    if signal is not None and signal <= 0.2:
        return {
            "status": "critical",
            "kind": "signal_loss",
            "probability": _clamp_probability(0.9 + (0.2 - signal) * 0.2),
            "summary": "Control signal quality is very low.",
            "recommendedAction": "Inspect wiring and communication bus integrity.",
        }

    if signal is not None and signal <= 0.45:
        return {
            "status": "warning",
            "kind": "weak_signal",
            "probability": _clamp_probability(0.66 + (0.45 - signal) * 0.5),
            "summary": "Control signal is weaker than expected.",
            "recommendedAction": "Check shielding and connector quality.",
        }

    return None


def _resolve_existing_fault(
    faults: dict[str, dict[str, Any]],
    fault_id: str | None,
    note: str,
) -> None:
    if not fault_id:
        return

    fault = faults.get(fault_id)
    if not fault or fault.get("state") != "open":
        return

    fault["state"] = "resolved"
    fault["resolvedBy"] = "classifier-worker"
    fault["note"] = note
    fault["updatedAt"] = utc_now_iso()


def _attach_fault(
    faults: dict[str, dict[str, Any]],
    node_id: str,
    node: dict[str, Any],
    diagnosis: dict[str, Any],
) -> None:
    now = utc_now_iso()
    current_fault_id = node.get("latestFaultId")
    current_fault = faults.get(current_fault_id) if current_fault_id else None

    if current_fault and current_fault.get("state") == "open":
        if current_fault.get("kind") == diagnosis["kind"]:
            current_fault["probability"] = diagnosis["probability"]
            current_fault["summary"] = diagnosis["summary"]
            current_fault["recommendedAction"] = diagnosis["recommendedAction"]
            current_fault["updatedAt"] = now
            node["status"] = diagnosis["status"]
            return

        _resolve_existing_fault(
            faults,
            current_fault_id,
            "Superseded by a newer classifier signal.",
        )

    fault_id = f"fault-{uuid4().hex[:8]}"
    faults[fault_id] = {
        "id": fault_id,
        "nodeId": node_id,
        "state": "open",
        "kind": diagnosis["kind"],
        "probability": diagnosis["probability"],
        "summary": diagnosis["summary"],
        "recommendedAction": diagnosis["recommendedAction"],
        "openedAt": now,
        "updatedAt": now,
        "resolvedBy": None,
        "note": None,
    }
    node["latestFaultId"] = fault_id
    node["status"] = diagnosis["status"]


def _clear_fault(node: dict[str, Any], faults: dict[str, dict[str, Any]]) -> None:
    current_fault_id = node.get("latestFaultId")
    _resolve_existing_fault(
        faults,
        current_fault_id,
        "Telemetry returned to expected range.",
    )
    node["latestFaultId"] = None
    node["status"] = "healthy"


def _propagate_parent_status(nodes: dict[str, dict[str, Any]]) -> None:
    children: dict[str, list[str]] = defaultdict(list)
    for node_id, node in nodes.items():
        for parent_id in node.get("parentIds", []):
            if parent_id in nodes:
                children[parent_id].append(node_id)

    effective = {
        node_id: node.get("status") if node.get("status") in STATUS_RANK else "healthy"
        for node_id, node in nodes.items()
    }

    changed = True
    while changed:
        changed = False
        for parent_id, child_ids in children.items():
            parent_rank = STATUS_RANK.get(effective.get(parent_id, "healthy"), 0)
            child_rank = max(
                (
                    STATUS_RANK.get(effective.get(child_id, "healthy"), 0)
                    for child_id in child_ids
                ),
                default=0,
            )
            worst_rank = max(parent_rank, child_rank)
            next_status = RANK_STATUS[worst_rank]
            if effective.get(parent_id) != next_status:
                effective[parent_id] = next_status
                changed = True

    for node_id, status in effective.items():
        nodes[node_id]["status"] = status


def run_diagnosis_cycle(state: dict[str, Any]) -> dict[str, int]:
    nodes: dict[str, dict[str, Any]] = state.setdefault("nodes", {})
    faults: dict[str, dict[str, Any]] = state.setdefault("faults", {})

    processed_nodes = 0
    for node_id, node in nodes.items():
        telemetry = node.get("latestTelemetry") or {}
        if not telemetry:
            node.setdefault("status", "healthy")
            continue

        processed_nodes += 1
        diagnosis = _classify_node(node)
        if diagnosis is None:
            _clear_fault(node, faults)
            continue

        _attach_fault(faults, node_id, node, diagnosis)

    _propagate_parent_status(nodes)
    state.setdefault("meta", {})["lastClassificationAt"] = utc_now_iso()

    open_faults = sum(1 for fault in faults.values() if fault.get("state") == "open")
    return {
        "processedNodes": processed_nodes,
        "openFaults": open_faults,
    }


def resolve_fault(
    state: dict[str, Any],
    fault_id: str,
    resolved_by: str,
    note: str | None,
) -> dict[str, Any] | None:
    faults: dict[str, dict[str, Any]] = state.setdefault("faults", {})
    nodes: dict[str, dict[str, Any]] = state.setdefault("nodes", {})

    fault = faults.get(fault_id)
    if not fault:
        return None

    now = utc_now_iso()
    fault["state"] = "resolved"
    fault["resolvedBy"] = resolved_by
    fault["note"] = note
    fault["updatedAt"] = now

    node_id = fault.get("nodeId")
    if node_id in nodes and nodes[node_id].get("latestFaultId") == fault_id:
        nodes[node_id]["latestFaultId"] = None
        nodes[node_id]["status"] = "healthy"

    state.setdefault("meta", {})["lastFaultResolutionAt"] = now
    return {
        "ok": True,
        "faultId": fault_id,
        "state": "resolved",
    }


def build_status_payload(state: dict[str, Any]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = state.get("nodes", {})
    faults: dict[str, dict[str, Any]] = state.get("faults", {})

    result_nodes: list[dict[str, Any]] = []
    for node_id in sorted(nodes.keys()):
        node = nodes[node_id]
        fault_payload = None

        fault_id = node.get("latestFaultId")
        if isinstance(fault_id, str):
            fault = faults.get(fault_id)
            if fault:
                fault_payload = {
                    "id": fault.get("id"),
                    "state": fault.get("state", "open"),
                    "kind": fault.get("kind"),
                    "probability": fault.get("probability", 0.0),
                    "summary": fault.get("summary"),
                    "recommendedAction": fault.get("recommendedAction"),
                }

        status = node.get("status")
        if status not in STATUS_RANK:
            status = "healthy"

        result_nodes.append(
            {
                "id": node_id,
                "label": node.get("label") or _label_from_node_id(node_id),
                "type": node.get("type") or "device",
                "status": status,
                "parentIds": node.get("parentIds") or [],
                "fault": fault_payload,
            }
        )

    return {
        "generatedAt": utc_now_iso(),
        "nodes": result_nodes,
    }
