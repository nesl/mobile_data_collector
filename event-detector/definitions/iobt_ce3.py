"""Vehicle arrival, building entry, gunshot, exit, and departure."""

from definitions.common import gunshot_like, label_count, no_people_or_vehicles
from fsm import ComplexEventFSM, Step


def build(outside_device: str, building_device: str) -> ComplexEventFSM:
    return ComplexEventFSM("iobt_ce3", [
        Step("Car detected outside", label_count("car"), outside_device, "vision"),
        Step("Person detected outside", label_count("person"), outside_device, "vision"),
        Step("Person enters building", label_count("person"), building_device, "vision"),
        Step("Gunshot heard in building", gunshot_like, building_device, "audio"),
        Step("Person leaves building", label_count("person"), outside_device, "vision"),
        Step("Person and vehicle gone", no_people_or_vehicles, outside_device, "vision", hold_seconds=4),
    ])
