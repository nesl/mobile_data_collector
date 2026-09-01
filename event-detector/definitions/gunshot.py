"""A gunshot is heard by the building device."""

from definitions.common import gunshot_like
from fsm import ComplexEventFSM, Step


def build(_outside_device: str, building_device: str) -> ComplexEventFSM:
    return ComplexEventFSM("gunshot", [
        Step("Gunshot heard", gunshot_like, building_device, "audio"),
    ])
