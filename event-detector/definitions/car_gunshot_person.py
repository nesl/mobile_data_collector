"""A car appears, a gunshot is heard, then a person appears."""

from definitions.common import gunshot_burst, label_any, label_count
from fsm import ComplexEventFSM, Step


def build(outside_device: str, building_device: str) -> ComplexEventFSM:
    return ComplexEventFSM("car_gunshot_person", [
        Step("Car detected", label_any("car", "vehicle"), outside_device, "vision"),
        Step("Gunshot heard", gunshot_burst(), building_device, "audio"),
        Step("Person detected", label_count("person"), outside_device, "vision"),
    ])
