from __future__ import annotations

from pathlib import Path

from ml.simulation.engine import SimulationResult


def plot_result(
    result: SimulationResult,
    *,
    output_path: str | Path | None = None,
    show: bool = False,
) -> None:
    plt = _load_matplotlib()
    figure, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    for zone_id, series in result.zone_avg_temp_c.items():
        axes[0].plot(result.times_s, series, label=zone_id)
    axes[0].set_ylabel("Zone Avg Temp (C)")
    axes[0].set_title(f"Scenario: {result.scenario_name}")
    axes[0].grid(alpha=0.25)
    axes[0].legend(loc="best")

    axes[1].plot(
        result.times_s, result.max_cpu_temp_c, label="max_cpu_temp", color="#d04a3a"
    )
    axes[1].axhline(
        85.0, color="#c58f00", linestyle="--", linewidth=1.0, label="throttle"
    )
    axes[1].axhline(
        100.0, color="#8b0000", linestyle="--", linewidth=1.0, label="shutdown"
    )
    axes[1].set_ylabel("CPU Temp (C)")
    axes[1].set_xlabel("Time (s)")
    axes[1].grid(alpha=0.25)
    axes[1].legend(loc="best")

    figure.tight_layout()
    _save_or_show(plt=plt, output_path=output_path, show=show)


def plot_comparison(
    baseline: SimulationResult,
    candidate: SimulationResult,
    *,
    focus_zone_id: str = "zone_ef",
    output_path: str | Path | None = None,
    show: bool = False,
) -> None:
    plt = _load_matplotlib()
    figure, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    baseline_zone = baseline.zone_avg_temp_c.get(focus_zone_id, [])
    candidate_zone = candidate.zone_avg_temp_c.get(focus_zone_id, [])
    axes[0].plot(
        baseline.times_s,
        baseline_zone,
        label=f"baseline:{focus_zone_id}",
        color="#2d6cdf",
    )
    axes[0].plot(
        candidate.times_s,
        candidate_zone,
        label=f"candidate:{focus_zone_id}",
        color="#d04a3a",
    )
    axes[0].set_ylabel("Zone Avg Temp (C)")
    axes[0].set_title(f"{baseline.scenario_name} vs {candidate.scenario_name}")
    axes[0].grid(alpha=0.25)
    axes[0].legend(loc="best")

    axes[1].plot(
        baseline.times_s,
        baseline.max_cpu_temp_c,
        label=f"baseline:{baseline.scenario_name}",
        color="#2d6cdf",
    )
    axes[1].plot(
        candidate.times_s,
        candidate.max_cpu_temp_c,
        label=f"candidate:{candidate.scenario_name}",
        color="#d04a3a",
    )
    axes[1].axhline(
        85.0, color="#c58f00", linestyle="--", linewidth=1.0, label="throttle"
    )
    axes[1].axhline(
        100.0, color="#8b0000", linestyle="--", linewidth=1.0, label="shutdown"
    )
    axes[1].set_ylabel("Max CPU Temp (C)")
    axes[1].set_xlabel("Time (s)")
    axes[1].grid(alpha=0.25)
    axes[1].legend(loc="best")

    figure.tight_layout()
    _save_or_show(plt=plt, output_path=output_path, show=show)


def plot_final_heatmaps(
    result: SimulationResult,
    *,
    output_path: str | Path | None = None,
    show: bool = False,
) -> None:
    plt = _load_matplotlib()
    zone_items = list(result.final_state.zones.items())
    figure, axes = plt.subplots(1, len(zone_items), figsize=(4 * len(zone_items), 3.5))
    if len(zone_items) == 1:
        axes = [axes]
    for axis, (zone_id, zone) in zip(axes, zone_items):
        image = axis.imshow(
            zone.temperature_c.T, origin="lower", aspect="auto", cmap="inferno"
        )
        axis.set_title(zone_id)
        axis.set_xlabel("x")
        axis.set_ylabel("y")
        figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    figure.tight_layout()
    _save_or_show(plt=plt, output_path=output_path, show=show)


def _save_or_show(*, plt, output_path: str | Path | None, show: bool) -> None:
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output, dpi=160)
    if show:
        plt.show()
    plt.close("all")


def _load_matplotlib():
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required for visualization. Install project dependencies first."
        ) from exc
    return plt
