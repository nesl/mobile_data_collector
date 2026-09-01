"""Immutable syntax tree for the mobile CE language."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping


ComparisonOperator = Literal["==", "!=", ">=", ">", "<=", "<"]


@dataclass(frozen=True)
class Comparison:
    operator: ComparisonOperator
    value: int | float | str

    def matches(self, actual: int | float | str) -> bool:
        operations = {
            "==": lambda left, right: left == right,
            "!=": lambda left, right: left != right,
            ">=": lambda left, right: left >= right,
            ">": lambda left, right: left > right,
            "<=": lambda left, right: left <= right,
            "<": lambda left, right: left < right,
        }
        return operations[self.operator](actual, self.value)


@dataclass(frozen=True)
class TriggerDefinition:
    label: str
    device: str | None = None
    count: Comparison | None = None
    confidence: Comparison | None = None
    color: Comparison | None = None


@dataclass(frozen=True)
class AtomicEventDefinition:
    atomic_event_name: str
    triggers: tuple[TriggerDefinition, ...]
    device: str | None = None
    logic: Literal["AND", "OR"] = "AND"
    window_seconds: float = 120


@dataclass(frozen=True)
class HoldsConstraintDefinition:
    atomic_event: str
    duration_seconds: float


@dataclass(frozen=True)
class WithinConstraintDefinition:
    from_atomic_event: str
    to_atomic_event: str
    duration_seconds: float


TemporalConstraint = HoldsConstraintDefinition | WithinConstraintDefinition


@dataclass(frozen=True)
class ComplexEventDefinition:
    complex_event_name: str
    devices: Mapping[str, str]
    atomic_events: Mapping[str, AtomicEventDefinition]
    ce_sequence: tuple[str, ...]
    constraints: tuple[TemporalConstraint, ...] = ()
    description: str = ""
    version: int = 1
