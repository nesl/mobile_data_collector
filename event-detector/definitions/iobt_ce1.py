"""Four cars arrive, then a truck, then all vehicles leave."""

from definitions.common import label_count, no_vehicles
from fsm import ComplexEventFSM, Step


def build(outside_device: str, _building_device: str) -> ComplexEventFSM:
    return ComplexEventFSM("iobt_ce1", [
        Step("Four cars detected", label_count("car", 4), outside_device, "vision"),
        Step("Truck detected", label_count("truck"), outside_device, "vision"),
        Step("Vehicles gone", no_vehicles, outside_device, "vision", hold_seconds=4),
    ])
