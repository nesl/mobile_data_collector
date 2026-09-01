"""Validate mobile capabilities and lower a parsed CE into the runtime FSM."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Mapping

import yaml

from runtime.fsm import AtomicEvent, ComplexEventFSM, Observation, Trigger

from .models import (
    Comparison,
    ComplexEventDefinition,
    HoldsConstraintDefinition,
    TriggerDefinition,
    WithinConstraintDefinition,
)


class EventCompilationError(ValueError):
    """A valid CE definition cannot be executed by this mobile pipeline."""


@lru_cache(maxsize=1)
def load_label_capabilities() -> dict:
    path = Path(__file__).with_name("label_capabilities.yaml")
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("labels"), dict):
        raise ValueError(f"{path}: invalid label capability catalog")
    return raw["labels"]


def compile_event(
    event: ComplexEventDefinition,
    *,
    label_capabilities: Mapping[str, dict] | None = None,
) -> ComplexEventFSM:
    """Compile a parsed definition into an executable event-time FSM."""
    capabilities = label_capabilities or load_label_capabilities()
    errors: list[str] = []
    resolved_devices = dict(event.devices)

    for atomic_event_name in event.ce_sequence:
        atomic_event = event.atomic_events[atomic_event_name]
        for index, trigger in enumerate(atomic_event.triggers):
            path = f"atomic_events.{atomic_event_name}.triggers[{index}]"
            capability = capabilities.get(trigger.label)
            if not isinstance(capability, dict):
                errors.append(f"{path}.label: unsupported semantic label {trigger.label!r}")
                continue
            supported_fields = set(capability.get("fields", ()))
            for field in ("count", "confidence", "color"):
                if getattr(trigger, field) is not None and field not in supported_fields:
                    errors.append(
                        f"{path}.{field}: label {trigger.label!r} does not provide this field"
                    )
            role = trigger.device if trigger.device is not None else atomic_event.device
            if role not in (None, "ANY") and role not in resolved_devices:
                errors.append(f"{path}.device: unknown device role {role!r}")

    if errors:
        raise EventCompilationError(
            f"Complex event {event.complex_event_name!r} cannot be compiled:\n  - "
            + "\n  - ".join(errors)
        )

    atomic_events: list[AtomicEvent] = []
    for atomic_event_name in event.ce_sequence:
        definition = event.atomic_events[atomic_event_name]
        triggers = tuple(
            _compile_trigger(
                trigger,
                default_device=definition.device,
                resolved_devices=resolved_devices,
                capability=capabilities[trigger.label],
            )
            for trigger in definition.triggers
        )
        atomic_events.append(AtomicEvent(
            atomic_event_name,
            triggers=triggers,
            trigger_logic=definition.logic,
            and_within_seconds=definition.window_seconds,
        ))

    fsm = ComplexEventFSM(event.complex_event_name, atomic_events)
    for constraint in event.constraints:
        if isinstance(constraint, HoldsConstraintDefinition):
            fsm.add_holds_constraint(constraint.atomic_event, constraint.duration_seconds)
        elif isinstance(constraint, WithinConstraintDefinition):
            fsm.add_within_constraint(constraint.from_atomic_event, constraint.to_atomic_event, constraint.duration_seconds)
    return fsm


def _compile_trigger(
    definition: TriggerDefinition,
    *,
    default_device: str | None,
    resolved_devices: Mapping[str, str],
    capability: Mapping,
) -> Trigger:
    role = definition.device if definition.device is not None else default_device
    device = None if role in (None, "ANY") else resolved_devices[role]
    source = capability["source"]
    native_labels = {str(value).casefold() for value in capability.get("native_labels", ())}
    contains = tuple(str(value).casefold() for value in capability.get("contains", ()))
    count_comparison = definition.count or Comparison(">=", 1)

    def predicate(observation: Observation) -> bool:
        if observation.modality != source:
            return False
        qualifying = 0
        for index, label in enumerate(observation.labels):
            normalized = label.casefold()
            if normalized not in native_labels and not any(term in normalized for term in contains):
                continue
            confidence = observation.scores[index] if index < len(observation.scores) else 1.0
            if definition.confidence is not None and not definition.confidence.matches(confidence):
                continue
            if definition.color is not None:
                color = observation.colors[index].casefold() if index < len(observation.colors) else ""
                if not definition.color.matches(color):
                    continue
            qualifying += 1
        return count_comparison.matches(qualifying)

    return Trigger(predicate, device=device, modality=source)
