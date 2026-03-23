from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.simulation.scenarios import (
    build_default_engine,
    default_scenarios,
    discovery_report,
)
from ml.simulation.topology import build_datacenter_topology, build_initial_state
from ml.simulation.visualize import plot_comparison, plot_final_heatmaps


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run datacenter HVAC simulation scenarios"
    )
    parser.add_argument(
        "--scenario",
        default="dmp_ef_stuck",
        help="Scenario key from default scenarios",
    )
    parser.add_argument(
        "--duration", type=float, default=900.0, help="Simulation duration in seconds"
    )
    parser.add_argument(
        "--dt", type=float, default=1.0, help="Simulation timestep in seconds"
    )
    parser.add_argument(
        "--output-dir",
        default="ml/simulation/artifacts",
        help="Output directory for plots and discovery report",
    )
    parser.add_argument("--show", action="store_true", help="Show plots interactively")
    args = parser.parse_args()

    scenarios = default_scenarios(duration_s=args.duration)
    if args.scenario not in scenarios:
        available = ", ".join(sorted(scenarios))
        raise ValueError(f"Unknown scenario '{args.scenario}'. Available: {available}")

    topology = build_datacenter_topology()
    baseline_state = build_initial_state(topology, dt_s=args.dt)
    candidate_state = build_initial_state(topology, dt_s=args.dt)

    baseline_engine = build_default_engine(topology)
    candidate_engine = build_default_engine(topology)
    baseline_result = baseline_engine.run_scenario(
        baseline_state,
        scenario_name="baseline",
        duration_s=args.duration,
        failures=scenarios["baseline"].failures,
    )
    candidate_def = scenarios[args.scenario]
    candidate_result = candidate_engine.run_scenario(
        candidate_state,
        scenario_name=candidate_def.name,
        duration_s=args.duration,
        failures=candidate_def.failures,
    )

    report = discovery_report(baseline_result, candidate_result)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"discovery_{candidate_def.name}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    comparison_path = output_dir / f"comparison_{candidate_def.name}.png"
    heatmap_path = output_dir / f"heatmap_{candidate_def.name}.png"
    plot_comparison(
        baseline_result,
        candidate_result,
        focus_zone_id="zone_ef",
        output_path=comparison_path,
        show=args.show,
    )
    plot_final_heatmaps(candidate_result, output_path=heatmap_path, show=args.show)

    print(f"Saved discovery report to {report_path}")
    print(f"Saved comparison plot to {comparison_path}")
    print(f"Saved final heatmap plot to {heatmap_path}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
