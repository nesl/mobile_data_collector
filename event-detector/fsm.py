"""Small event-time state machine used by the mobile detector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class Observation:
    device: str
    timestamp: float
    modality: str
    labels: tuple[str, ...]
    scores: tuple[float, ...] = ()
    colors: tuple[str, ...] = ()


Predicate = Callable[[Observation], bool]


@dataclass(frozen=True)
class Step:
    name: str
    predicate: Predicate
    device: str | None = None
    modality: str | None = None
    hold_seconds: float = 0

    def matches(self, observation: Observation) -> bool:
        return (
            (self.device is None or observation.device == self.device)
            and (self.modality is None or observation.modality == self.modality)
            and self.predicate(observation)
        )


class ComplexEventFSM:
    """Advance through an immutable sequence of atomic-event steps."""

    def __init__(self, name: str, steps: Iterable[Step]):
        self.name = name
        self.steps = tuple(steps)
        if not self.steps:
            raise ValueError("a complex event requires at least one step")
        self.reset()

    @property
    def current_step(self) -> Step:
        return self.steps[self.step_index]

    def reset(self) -> None:
        self.step_index = 0
        self.hold_started_at: float | None = None
        self.completed = False

    def status(self) -> dict:
        return {
            "event": self.name,
            "current_step": self.step_index,
            "completed": self.completed,
            "steps": [
                {
                    "name": step.name,
                    "device": step.device,
                    "modality": step.modality,
                    "hold_seconds": step.hold_seconds,
                }
                for step in self.steps
            ],
        }

    def observe(self, observation: Observation) -> bool:
        if self.completed:
            return False
        step = self.current_step
        if step.device is not None and observation.device != step.device:
            return False
        if step.modality is not None and observation.modality != step.modality:
            return False

        if not step.matches(observation):
            if step.hold_seconds:
                self.hold_started_at = None
            return False

        if step.hold_seconds:
            if self.hold_started_at is None:
                self.hold_started_at = observation.timestamp
                return False
            if observation.timestamp - self.hold_started_at < step.hold_seconds:
                return False

        self.step_index += 1
        self.hold_started_at = None
        if self.step_index == len(self.steps):
            self.completed = True
            return True
        return False
