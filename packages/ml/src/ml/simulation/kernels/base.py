from __future__ import annotations

from abc import ABC, abstractmethod

from ml.simulation.state import SimulationState


class Kernel(ABC):
    name = "kernel"

    @abstractmethod
    def apply(self, state: SimulationState) -> SimulationState:
        raise NotImplementedError


class LinearKernelPipeline:
    def __init__(self, kernels: list[Kernel]) -> None:
        self.kernels = kernels

    def step(self, state: SimulationState) -> SimulationState:
        for kernel in self.kernels:
            state = kernel.apply(state)
        return state
