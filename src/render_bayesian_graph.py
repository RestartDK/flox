from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shacklib.simulation_service import run_simulation_bundle


LAYER_ORDER = ["components", "flow", "zone", "equipment", "system"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render Bayesian network graph to a PNG file."
    )
    parser.add_argument(
        "--output",
        default="bayesian_network.png",
        help="Output PNG path.",
    )
    parser.add_argument(
        "--input-json",
        help="Optional JSON file containing either a simulation response or BayesianView.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=300.0,
        help="Simulation duration in seconds when generating graph data.",
    )
    parser.add_argument(
        "--dt-seconds",
        type=float,
        default=1.0,
        help="Simulation time step in seconds when generating graph data.",
    )
    parser.add_argument(
        "--failure-component-id",
        default="dmp_ef",
        help="Failure component id used for generated simulation data.",
    )
    parser.add_argument(
        "--failure-mode",
        default="stuck",
        help="Failure mode used for generated simulation data.",
    )
    parser.add_argument(
        "--failure-severity",
        type=float,
        default=0.92,
        help="Failure severity used for generated simulation data.",
    )
    parser.add_argument(
        "--include-discovery-analysis",
        action="store_true",
        help="Include advanced discovery analysis when generating data.",
    )
    return parser.parse_args()


def _load_json(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must be an object")
    if isinstance(payload.get("bayesian"), dict):
        return payload["bayesian"]
    return payload


def _generate_bayesian_view(args: argparse.Namespace) -> dict[str, Any]:
    failures = [
        {
            "componentId": args.failure_component_id,
            "mode": args.failure_mode,
            "severity": float(args.failure_severity),
            "startSeconds": 0.0,
        }
    ]
    result = run_simulation_bundle(
        duration_seconds=args.duration_seconds,
        dt_seconds=args.dt_seconds,
        failures_payload=failures,
        status_payload=None,
        generated_at=datetime.now(timezone.utc).isoformat(),
        include_discovery_analysis=bool(args.include_discovery_analysis),
    )
    return result["bayesian"]


def _node_layout(bayesian: dict[str, Any]) -> dict[str, tuple[float, float]]:
    nodes = bayesian.get("nodes") or []
    by_layer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        if isinstance(node, dict):
            by_layer[str(node.get("layer") or "unknown")].append(node)

    active_layers = [layer for layer in LAYER_ORDER if by_layer.get(layer)]
    if not active_layers:
        active_layers = list(by_layer.keys()) or ["unknown"]

    positions: dict[str, tuple[float, float]] = {}
    layer_count = len(active_layers)
    for layer_index, layer in enumerate(active_layers):
        layer_nodes = sorted(
            by_layer[layer],
            key=lambda item: float(item.get("probability") or 0.0),
            reverse=True,
        )
        count = max(1, len(layer_nodes))
        x = 0.5 if layer_count == 1 else layer_index / (layer_count - 1)
        for node_index, node in enumerate(layer_nodes):
            y = 0.5 if count == 1 else 1.0 - (node_index / (count - 1))
            node_id = str(node.get("id") or "")
            if node_id:
                positions[node_id] = (x, y)
    return positions


def render_bayesian_graph(bayesian: dict[str, Any], output_path: str) -> None:
    nodes = [node for node in (bayesian.get("nodes") or []) if isinstance(node, dict)]
    edges = [edge for edge in (bayesian.get("edges") or []) if isinstance(edge, dict)]
    positions = _node_layout(bayesian)

    fig, ax = plt.subplots(figsize=(14, 7), constrained_layout=True)
    ax.set_facecolor("#f8fafc")
    fig.patch.set_facecolor("#ffffff")

    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in positions or target not in positions:
            continue
        sx, sy = positions[source]
        tx, ty = positions[target]
        weight = float(edge.get("weight") or 0.0)
        alpha = 0.15 + max(0.0, min(weight, 1.0)) * 0.45
        width = 0.8 + max(0.0, min(weight, 1.0)) * 2.2
        ax.annotate(
            "",
            xy=(tx, ty),
            xytext=(sx, sy),
            arrowprops={
                "arrowstyle": "-|>",
                "lw": width,
                "color": "#64748b",
                "alpha": alpha,
                "shrinkA": 14,
                "shrinkB": 14,
            },
        )

    norm = Normalize(vmin=0.0, vmax=1.0)
    cmap = plt.cm.RdYlGn_r

    for node in nodes:
        node_id = str(node.get("id") or "")
        if node_id not in positions:
            continue
        x, y = positions[node_id]
        label = str(node.get("label") or node_id)
        probability = float(node.get("probability") or 0.0)
        radius = 220 + max(0.0, min(probability, 1.0)) * 1400
        color = cmap(norm(probability))
        ax.scatter(
            [x],
            [y],
            s=radius,
            color=[color],
            alpha=0.9,
            edgecolors="#ffffff",
            linewidths=1.2,
            zorder=3,
        )
        ax.text(
            x + 0.016,
            y + 0.012,
            label,
            fontsize=9,
            color="#0f172a",
            ha="left",
            va="bottom",
            zorder=4,
        )
        ax.text(
            x + 0.016,
            y - 0.014,
            f"{probability * 100:.0f}%",
            fontsize=8,
            color="#475569",
            ha="left",
            va="top",
            zorder=4,
        )

    layer_positions = sorted({x for x, _ in positions.values()})
    layer_names = []
    nodes_by_layer = defaultdict(list)
    for node in nodes:
        nodes_by_layer[str(node.get("layer") or "unknown")].append(node)
    for layer in LAYER_ORDER:
        if nodes_by_layer.get(layer):
            layer_names.append(layer)
    if not layer_names:
        layer_names = ["unknown"]

    for idx, layer_x in enumerate(layer_positions):
        layer_label = layer_names[min(idx, len(layer_names) - 1)].upper()
        ax.text(
            layer_x,
            1.06,
            layer_label,
            fontsize=10,
            color="#334155",
            ha="center",
            va="bottom",
        )

    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.08, 1.1)
    ax.axis("off")
    ax.set_title(
        "Bayesian Failure Propagation Network", fontsize=14, color="#0f172a", pad=18
    )

    sm = ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    colorbar = fig.colorbar(sm, ax=ax, fraction=0.02, pad=0.02)
    colorbar.set_label("Failure probability", color="#334155")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    bayesian = (
        _load_json(args.input_json)
        if args.input_json
        else _generate_bayesian_view(args)
    )
    render_bayesian_graph(bayesian=bayesian, output_path=args.output)
    print(f"Saved Bayesian network graph to {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
