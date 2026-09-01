"""Registry of available complex-event definitions."""

from definitions.car_gunshot_person import build as car_gunshot_person
from definitions.gunshot import build as gunshot
from definitions.iobt_ce1 import build as iobt_ce1
from definitions.iobt_ce2 import build as iobt_ce2
from definitions.iobt_ce3 import build as iobt_ce3


BUILDERS = {
    "gunshot": gunshot,
    "iobt_ce1": iobt_ce1,
    "iobt_ce2": iobt_ce2,
    "iobt_ce3": iobt_ce3,
    "car_gunshot_person": car_gunshot_person,
}
EVENT_NAMES = tuple(BUILDERS)


def build_event(name: str, outside_device: str, building_device: str):
    try:
        builder = BUILDERS[name]
    except KeyError as error:
        raise ValueError(f"unknown event {name!r}") from error
    return builder(outside_device, building_device)
