from __future__ import annotations

import math

from ml.simulation.kernels.base import Kernel
from ml.simulation.state import ComponentState, SimulationState


class FailureInjectionKernel(Kernel):
    name = "failure_injection"

    def apply(self, state: SimulationState) -> SimulationState:
        for component in state.components.values():
            component.effective_position = component.command_position
            component.active_failure = None
            component.status = "healthy"
            component.locked_position = None

        for event in state.active_failures:
            if not event.is_active(state.time_s):
                continue
            component = state.components.get(event.component_id)
            if component is None:
                continue
            component.status = "fault"
            component.active_failure = event.mode
            self._apply_event(
                component=component,
                mode=event.mode,
                severity=event.severity,
                time_s=state.time_s,
            )

        return state

    def _apply_event(
        self,
        *,
        component: ComponentState,
        mode: str,
        severity: float,
        time_s: float,
    ) -> None:
        safe_severity = max(0.0, min(1.0, severity))
        mode_key = _normalize_mode(mode)
        position = component.effective_position

        if mode_key in {"gear_stuck", "stuck", "transmission_lock", "jam"}:
            stuck_value = max(
                component.min_position, position * (1.0 - 0.8 * safe_severity)
            )
            component.effective_position = stuck_value
            return

        if mode_key in {"signal_loss", "offline", "no_signal"}:
            component.effective_position = component.min_position
            return

        if mode_key in {"partial", "partial_failure", "degraded"}:
            component.effective_position = position * max(
                0.15, 1.0 - 0.7 * safe_severity
            )
            return

        if mode_key in {"resistance", "added_mechanical_resistance", "stiction"}:
            component.effective_position = position * max(
                0.2, 1.0 - 0.45 * safe_severity
            )
            return

        if mode_key in {
            "bottle_stuck",
            "closure_blockage",
            "closure_blockage_bottle_held_open",
        }:
            component.effective_position = max(position, 0.55 + 0.35 * safe_severity)
            return

        if mode_key in {"stabbing", "valve_destabilization", "repeated_poking"}:
            amplitude = 0.22 * safe_severity
            oscillation = amplitude * math.sin(2.0 * math.pi * 0.08 * time_s)
            component.effective_position = _clamp_position(
                component, position + oscillation
            )
            return

        component.effective_position = position * max(0.2, 1.0 - 0.6 * safe_severity)


def _normalize_mode(mode: str) -> str:
    normalized = (
        mode.strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")
    )
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized


def _clamp_position(component: ComponentState, value: float) -> float:
    return max(component.min_position, min(component.max_position, value))
