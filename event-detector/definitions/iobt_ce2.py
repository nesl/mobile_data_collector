"""A car repeatedly appears and disappears three times."""

from definitions.common import label_count, no_vehicles
from fsm import ComplexEventFSM, Step


def build(outside_device: str, _building_device: str) -> ComplexEventFSM:
    steps = []
    for occurrence in range(1, 4):
        steps.extend((
            Step(f"Car detected {occurrence}", label_count("car"), outside_device, "vision", hold_seconds=3),
            Step(f"Vehicles gone {occurrence}", no_vehicles, outside_device, "vision", hold_seconds=4),
        ))
    return ComplexEventFSM("iobt_ce2", steps)
