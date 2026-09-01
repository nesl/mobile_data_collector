"""Event-time FSM primitives for compiled mobile complex events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Literal


@dataclass(frozen=True)
class Observation:
    device: str
    timestamp: float
    modality: str
    labels: tuple[str, ...]
    scores: tuple[float, ...] = ()
    colors: tuple[str, ...] = ()


Predicate = Callable[[Observation], bool]
TriggerLogic = Literal["AND", "OR"]


@dataclass(frozen=True)
class Trigger:
    """One sensor predicate; ``device=None`` represents the original ``ANY``."""

    predicate: Predicate
    device: str | None = None
    modality: str | None = None

    def matches(self, observation: Observation) -> bool:
        return (
            (self.device is None or observation.device == self.device)
            and (self.modality is None or observation.modality == self.modality)
            and self.predicate(observation)
        )


@dataclass(frozen=True)
class AtomicEvent:
    atomic_event_name: str
    triggers: tuple[Trigger, ...]
    trigger_logic: TriggerLogic = "AND"
    and_within_seconds: float = 120
    hold_seconds: float = 0

    def __post_init__(self) -> None:
        if self.trigger_logic not in ("AND", "OR"):
            raise ValueError("trigger_logic must be 'AND' or 'OR'")
        if self.hold_seconds < 0:
            raise ValueError("hold_seconds cannot be negative")
        if self.and_within_seconds <= 0:
            raise ValueError("and_within_seconds must be positive")
        if not self.triggers:
            raise ValueError("an atomic event requires at least one trigger")


@dataclass(frozen=True)
class WithinConstraint:
    from_atomic_event: int
    to_atomic_event: int
    seconds: float


class ComplexEventFSM:
    """Evaluate atomic events, transitions, actions, HOLDS, and WITHIN."""

    def __init__(self, complex_event_name: str, atomic_events: Iterable[AtomicEvent]):
        self.complex_event_name = complex_event_name
        self.atomic_events = tuple(atomic_events)
        if not self.atomic_events:
            raise ValueError("a complex event requires at least one atomic event")
        self._within: list[WithinConstraint] = []
        self.reset()

    @property
    def current_atomic_event(self) -> AtomicEvent:
        return self.atomic_events[self.atomic_event_index]

    def _atomic_event_index(self, atomic_event: int | str | AtomicEvent) -> int:
        if isinstance(atomic_event, int):
            if not 0 <= atomic_event < len(self.atomic_events):
                raise IndexError(atomic_event)
            return atomic_event
        matches = [
            index for index, item in enumerate(self.atomic_events)
            if (item.atomic_event_name == atomic_event if isinstance(atomic_event, str) else item is atomic_event)
        ]
        # A HOLDS update replaces the frozen AtomicEvent value; resolve a stale
        # object reference by its unique name.
        if not matches and isinstance(atomic_event, AtomicEvent):
            matches = [
                index for index, item in enumerate(self.atomic_events)
                if item.atomic_event_name == atomic_event.atomic_event_name
            ]
        if len(matches) != 1:
            raise ValueError(f"atomic event must identify exactly one state: {atomic_event!r}")
        return matches[0]

    def add_holds_constraint(self, atomic_event, seconds: float) -> None:
        """Require a state to remain true for at least ``seconds`` (HOLDS)."""
        if seconds < 0:
            raise ValueError("HOLDS duration cannot be negative")
        index = self._atomic_event_index(atomic_event)
        values = {**self.atomic_events[index].__dict__, "hold_seconds": seconds}
        mutable = list(self.atomic_events)
        mutable[index] = AtomicEvent(**values)
        self.atomic_events = tuple(mutable)

    def add_within_constraint(self, from_atomic_event, to_atomic_event, seconds: float) -> None:
        """Require the end state no later than seconds after the start state."""
        if seconds < 0:
            raise ValueError("WITHIN duration cannot be negative")
        self._within.append(WithinConstraint(
            self._atomic_event_index(from_atomic_event), self._atomic_event_index(to_atomic_event), seconds
        ))

    def reset(self) -> None:
        self.atomic_event_index = 0
        self.hold_started_at: float | None = None
        self.completed = False
        self.failed = False
        self._satisfied_triggers: set[int] = set()
        self._and_started_at: float | None = None
        self._satisfied_at: dict[int, float] = {}

    def status(self) -> dict:
        return {
            "complex_event_name": self.complex_event_name,
            "current_atomic_event_index": self.atomic_event_index,
            "completed": self.completed,
            "failed": self.failed,
            "atomic_events": [
                {
                    "atomic_event_name": step.atomic_event_name,
                    "hold_seconds": step.hold_seconds,
                    "trigger_logic": step.trigger_logic,
                    "and_within_seconds": step.and_within_seconds,
                    "triggers": [
                        {"device": trigger.device, "modality": trigger.modality}
                        for trigger in step.triggers
                    ],
                }
                for step in self.atomic_events
            ],
            "within": [constraint.__dict__ for constraint in self._within],
        }

    def _within_satisfied(self, timestamp: float) -> bool:
        for constraint in self._within:
            if constraint.to_atomic_event != self.atomic_event_index:
                continue
            started_at = self._satisfied_at.get(constraint.from_atomic_event)
            if started_at is None:
                return False
            if timestamp - started_at > constraint.seconds:
                self.failed = True
                return False
        return True

    def _state_matches(self, observation: Observation, *, continuous: bool = False) -> bool:
        step = self.current_atomic_event
        triggers = step.triggers
        relevant = {
            index for index, trigger in enumerate(triggers)
            if (trigger.device is None or trigger.device == observation.device)
            and (trigger.modality is None or trigger.modality == observation.modality)
        }
        matched = {index for index in relevant if triggers[index].matches(observation)}
        if continuous:
            self._satisfied_triggers.difference_update(relevant - matched)
        if step.trigger_logic == "OR" and not continuous:
            return bool(matched)
        if self._satisfied_triggers and self._and_started_at is not None:
            if observation.timestamp - self._and_started_at > step.and_within_seconds:
                self.failed = True
                return False
        if matched and not self._satisfied_triggers:
            self._and_started_at = observation.timestamp
        self._satisfied_triggers.update(matched)
        if not self._satisfied_triggers:
            self._and_started_at = None
        return (
            bool(self._satisfied_triggers)
            if step.trigger_logic == "OR"
            else len(self._satisfied_triggers) == len(triggers)
        )

    def observe(self, observation: Observation) -> bool:
        if self.completed or self.failed:
            return False
        step = self.current_atomic_event
        if not self._state_matches(observation, continuous=bool(step.hold_seconds)):
            if step.hold_seconds:
                relevant = any(
                    (trigger.device is None or trigger.device == observation.device)
                    and (trigger.modality is None or trigger.modality == observation.modality)
                    for trigger in step.triggers
                )
                if relevant:
                    self.hold_started_at = None
            return False

        if not self._within_satisfied(observation.timestamp):
            return False

        if step.hold_seconds:
            if self.hold_started_at is None:
                self.hold_started_at = observation.timestamp
                return False
            if observation.timestamp - self.hold_started_at < step.hold_seconds:
                return False

        source = self.atomic_event_index
        self._satisfied_at[source] = observation.timestamp
        self.hold_started_at = None
        self._satisfied_triggers.clear()
        self._and_started_at = None
        if source == len(self.atomic_events) - 1:
            self.completed = True
            self.atomic_event_index = len(self.atomic_events)
            return True
        self.atomic_event_index += 1
        return False
