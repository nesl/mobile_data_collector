"""Load and strictly validate YAML mobile complex-event definitions."""

from __future__ import annotations

from pathlib import Path
import re

import yaml

from .models import (
    Comparison,
    ComplexEventDefinition,
    HoldsConstraintDefinition,
    AtomicEventDefinition,
    TriggerDefinition,
    WithinConstraintDefinition,
)


_LOWER_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_DEVICE_ROLE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_DEVICE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
_COMPARISON = re.compile(r"^(==|!=|>=|>|<=|<)\s*(.+?)\s*$")
_NUMBER = re.compile(r"^-?(?:\d+(?:\.\d*)?|\.\d+)$")
_DURATION = re.compile(r"^(\d+(?:\.\d*)?|\.\d+)(ms|s|m|h)$")


def load_event(path: str | Path) -> ComplexEventDefinition:
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        return parse_event(yaml.safe_load(handle), source=str(source))


def parse_event(raw: object, *, source: str = "<memory>") -> ComplexEventDefinition:
    data = _mapping(raw, source)
    _unknown(data, {"version", "complex_event_name", "description", "devices", "atomic_events", "ce_sequence", "constraints"}, source)
    version = data.get("version", 1)
    if version != 1:
        raise ValueError(f"{source}.version: only version 1 is supported")
    name = _name(data.get("complex_event_name"), f"{source}.complex_event_name")
    description = data.get("description", "")
    if not isinstance(description, str):
        raise ValueError(f"{source}.description: expected string")
    devices = _parse_devices(data.get("devices", {}), source)
    atomic_events = _parse_atomic_events(data.get("atomic_events"), devices, source)
    ce_sequence = _parse_ce_sequence(data.get("ce_sequence"), atomic_events, source)
    constraints = _parse_constraints(data.get("constraints", []), atomic_events, ce_sequence, source)
    return ComplexEventDefinition(name, devices, atomic_events, ce_sequence, constraints, description, version)


def parse_comparison(value: object, *, kind: str, path: str) -> Comparison:
    if not isinstance(value, str):
        raise ValueError(f"{path}: expected comparison string such as '>= 1'")
    match = _COMPARISON.fullmatch(value.strip())
    if not match:
        raise ValueError(f"{path}: invalid comparison {value!r}")
    operator, operand_text = match.groups()
    if kind in {"count", "confidence"}:
        if not _NUMBER.fullmatch(operand_text):
            raise ValueError(f"{path}: {kind} comparison requires a number")
        number = float(operand_text)
        operand: int | float = int(number) if number.is_integer() else number
        if kind == "count" and (not isinstance(operand, int) or operand < 0):
            raise ValueError(f"{path}: count requires a non-negative integer")
        if kind == "confidence" and not 0 <= number <= 1:
            raise ValueError(f"{path}: confidence must be between 0 and 1")
        return Comparison(operator, operand)
    if operator not in {"==", "!="}:
        raise ValueError(f"{path}: color supports only == and !=")
    if not _LOWER_NAME.fullmatch(operand_text):
        raise ValueError(f"{path}: color must be a lowercase identifier")
    return Comparison(operator, operand_text)


def parse_duration(value: object, *, path: str) -> float:
    if not isinstance(value, str):
        raise ValueError(f"{path}: duration requires units, for example '4s' or '2m'")
    match = _DURATION.fullmatch(value.strip())
    if not match:
        raise ValueError(f"{path}: invalid duration {value!r}; use ms, s, m, or h")
    amount = float(match.group(1))
    seconds = amount * {"ms": .001, "s": 1, "m": 60, "h": 3600}[match.group(2)]
    if seconds <= 0:
        raise ValueError(f"{path}: duration must be greater than zero")
    return seconds


def _parse_devices(raw, source):
    data = _mapping(raw, f"{source}.devices")
    devices = {}
    for role, binding in data.items():
        if not isinstance(role, str) or not _DEVICE_ROLE.fullmatch(role) or role == "ANY":
            raise ValueError(f"{source}.devices: device roles must be uppercase identifiers other than ANY")
        if not isinstance(binding, str) or not _DEVICE_NAME.fullmatch(binding):
            raise ValueError(f"{source}.devices.{role}: expected a deployable phone name")
        devices[role] = binding
    return devices


def _parse_atomic_events(raw, devices, source):
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{source}.atomic_events: expected a non-empty list")
    atomic_events = {}
    for index, item in enumerate(raw):
        path = f"{source}.atomic_events[{index}]"
        data = _mapping(item, path)
        _unknown(data, {"atomic_event_name", "device", "logic", "window", "triggers"}, path)
        identifier = _name(data.get("atomic_event_name"), f"{path}.atomic_event_name")
        if identifier in atomic_events:
            raise ValueError(f"{path}.atomic_event_name: duplicate atomic event {identifier!r}")
        device = _device(data.get("device"), devices, f"{path}.device")
        logic = data.get("logic", "AND")
        if logic not in {"AND", "OR"}:
            raise ValueError(f"{path}.logic: expected AND or OR")
        window = parse_duration(data.get("window", "2m"), path=f"{path}.window")
        raw_triggers = data.get("triggers")
        if not isinstance(raw_triggers, list) or not raw_triggers:
            raise ValueError(f"{path}.triggers: expected a non-empty list")
        triggers = tuple(_parse_trigger(value, devices, f"{path}.triggers[{i}]") for i, value in enumerate(raw_triggers))
        atomic_events[identifier] = AtomicEventDefinition(identifier, triggers, device, logic, window)
    return atomic_events


def _parse_trigger(raw, devices, path):
    data = _mapping(raw, path)
    _unknown(data, {"device", "label", "count", "confidence", "color"}, path)
    label = _name(data.get("label"), f"{path}.label")
    return TriggerDefinition(
        label=label,
        device=_device(data.get("device"), devices, f"{path}.device"),
        count=parse_comparison(data["count"], kind="count", path=f"{path}.count") if "count" in data else None,
        confidence=parse_comparison(data["confidence"], kind="confidence", path=f"{path}.confidence") if "confidence" in data else None,
        color=parse_comparison(data["color"], kind="color", path=f"{path}.color") if "color" in data else None,
    )


def _parse_ce_sequence(raw, atomic_events, source):
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{source}.ce_sequence: expected a non-empty list")
    ce_sequence = tuple(_name(value, f"{source}.ce_sequence[{i}]") for i, value in enumerate(raw))
    if len(set(ce_sequence)) != len(ce_sequence):
        raise ValueError(f"{source}.ce_sequence: atomic events may appear only once")
    unknown = set(ce_sequence) - set(atomic_events)
    unused = set(atomic_events) - set(ce_sequence)
    if unknown:
        raise ValueError(f"{source}.ce_sequence: unknown atomic events {sorted(unknown)}")
    if unused:
        raise ValueError(f"{source}.ce_sequence: unused atomic events {sorted(unused)}")
    return ce_sequence


def _parse_constraints(raw, atomic_events, ce_sequence, source):
    if not isinstance(raw, list):
        raise ValueError(f"{source}.constraints: expected a list")
    positions = {name: index for index, name in enumerate(ce_sequence)}
    result = []
    for index, item in enumerate(raw):
        path = f"{source}.constraints[{index}]"
        data = _mapping(item, path)
        if len(data) != 1 or next(iter(data), None) not in {"holds", "within"}:
            raise ValueError(f"{path}: expected exactly one holds or within constraint")
        kind, payload = next(iter(data.items()))
        spec = _mapping(payload, f"{path}.{kind}")
        if kind == "holds":
            _unknown(spec, {"atomic_event", "duration"}, f"{path}.holds")
            atomic_event = _reference(spec.get("atomic_event"), atomic_events, f"{path}.holds.atomic_event")
            result.append(HoldsConstraintDefinition(atomic_event, parse_duration(spec.get("duration"), path=f"{path}.holds.duration")))
        else:
            _unknown(spec, {"from_atomic_event", "to_atomic_event", "duration"}, f"{path}.within")
            start = _reference(spec.get("from_atomic_event"), atomic_events, f"{path}.within.from_atomic_event")
            end = _reference(spec.get("to_atomic_event"), atomic_events, f"{path}.within.to_atomic_event")
            if positions[start] >= positions[end]:
                raise ValueError(f"{path}.within: from_atomic_event must precede to_atomic_event in ce_sequence")
            result.append(WithinConstraintDefinition(start, end, parse_duration(spec.get("duration"), path=f"{path}.within.duration")))
    return tuple(result)


def _mapping(value, path):
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a mapping")
    return value


def _unknown(data, allowed, path):
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"{path}: unknown fields {sorted(unknown)}")


def _name(value, path):
    if not isinstance(value, str) or not _LOWER_NAME.fullmatch(value):
        raise ValueError(f"{path}: expected a lowercase identifier")
    return value


def _device(value, devices, path):
    if value is None or value == "ANY":
        return value
    if not isinstance(value, str) or value not in devices:
        raise ValueError(f"{path}: expected ANY or a declared device role")
    return value


def _reference(value, atomic_events, path):
    name = _name(value, path)
    if name not in atomic_events:
        raise ValueError(f"{path}: unknown atomic event {name!r}")
    return name
