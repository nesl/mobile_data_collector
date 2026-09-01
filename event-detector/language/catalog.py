"""Discover and compile the YAML complex-event catalog."""

from __future__ import annotations

import os
from pathlib import Path

from .compiler import compile_event
from .parser import load_event


DEFAULT_DEFINITION_DIR = Path(
    os.getenv("CE_DEFINITION_DIR", Path(__file__).parents[2] / "ce_definitions")
)


def load_catalog(directory: str | Path = DEFAULT_DEFINITION_DIR) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for path in sorted(Path(directory).glob("*.yaml")):
        definition = load_event(path)
        if definition.complex_event_name in paths:
            raise ValueError(
                f"duplicate complex_event_name {definition.complex_event_name!r}: "
                f"{paths[definition.complex_event_name]} and {path}"
            )
        paths[definition.complex_event_name] = path
    if not paths:
        raise ValueError(f"no YAML complex-event definitions found in {directory}")
    return paths


def event_names(directory: str | Path = DEFAULT_DEFINITION_DIR) -> tuple[str, ...]:
    return tuple(load_catalog(directory))


def build_event(name: str, directory: str | Path = DEFAULT_DEFINITION_DIR):
    catalog = load_catalog(directory)
    try:
        path = catalog[name]
    except KeyError as error:
        raise ValueError(f"unknown complex event {name!r}") from error
    return compile_event(load_event(path))
