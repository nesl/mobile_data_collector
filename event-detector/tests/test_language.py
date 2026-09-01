from pathlib import Path
import unittest

from language import EventCompilationError, compile_event, event_names, load_catalog, load_event, parse_event
from runtime.fsm import Observation


ROOT = Path(__file__).resolve().parents[2]


def minimal_event(**changes):
    raw = {
        "version": 1,
        "complex_event_name": "example",
        "devices": {"OUTSIDE": "outside_phone", "BUILDING": "building_phone"},
        "atomic_events": [{
            "atomic_event_name": "activity",
            "triggers": [{"device": "OUTSIDE", "label": "person"}],
        }],
        "ce_sequence": ["activity"],
    }
    raw.update(changes)
    return raw


class LanguageParserTests(unittest.TestCase):
    def test_multiple_triggers_default_to_and_and_two_minutes(self):
        raw = minimal_event(atomic_events=[{
            "atomic_event_name": "activity",
            "triggers": [
                {"device": "OUTSIDE", "label": "person"},
                {"device": "BUILDING", "label": "person"},
            ],
        }])
        atomic_event = parse_event(raw).atomic_events["activity"]
        self.assertEqual(atomic_event.logic, "AND")
        self.assertEqual(atomic_event.window_seconds, 120)

    def test_comparisons_are_typed(self):
        raw = minimal_event(atomic_events=[{
            "atomic_event_name": "activity",
            "triggers": [{
                "label": "vehicle",
                "count": ">= 2",
                "confidence": "> 0.5",
                "color": "!= red",
            }],
        }])
        trigger = parse_event(raw).atomic_events["activity"].triggers[0]
        self.assertEqual((trigger.count.operator, trigger.count.value), (">=", 2))
        self.assertEqual(trigger.confidence.value, 0.5)
        self.assertEqual(trigger.color.value, "red")

    def test_invalid_comparison_and_unknown_field_are_rejected(self):
        raw = minimal_event(atomic_events=[{
            "atomic_event_name": "activity",
            "triggers": [{"label": "person", "count": ">= many"}],
        }])
        with self.assertRaisesRegex(ValueError, "requires a number"):
            parse_event(raw)
        raw["atomic_events"][0]["triggers"][0] = {"label": "person", "modality": "vision"}
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            parse_event(raw)

    def test_within_references_ordered_observations(self):
        raw = minimal_event(
            atomic_events=[
                {"atomic_event_name": "first", "triggers": [{"label": "person"}]},
                {"atomic_event_name": "second", "triggers": [{"label": "gunshot"}]},
            ],
            ce_sequence=["first", "second"],
            constraints=[{"within": {"from_atomic_event": "second", "to_atomic_event": "first", "duration": "2m"}}],
        )
        with self.assertRaisesRegex(ValueError, "from_atomic_event must precede"):
            parse_event(raw)


class LanguageCompilerTests(unittest.TestCase):
    def test_all_shipped_yaml_events_compile(self):
        catalog = load_catalog()
        self.assertEqual(set(event_names()), {
            "car_gunshot_person", "gunshot", "iobt_ce1", "iobt_ce2", "iobt_ce3",
        })
        for path in catalog.values():
            compile_event(load_event(path))

    def test_cross_device_default_and_and_explicit_or(self):
        raw = minimal_event(
            atomic_events=[
                {
                    "atomic_event_name": "both",
                    "triggers": [
                        {"device": "OUTSIDE", "label": "person"},
                        {"device": "BUILDING", "label": "gunshot"},
                    ],
                },
                {
                    "atomic_event_name": "either",
                    "logic": "OR",
                    "triggers": [
                        {"device": "OUTSIDE", "label": "car"},
                        {"device": "BUILDING", "label": "truck"},
                    ],
                },
            ],
            ce_sequence=["both", "either"],
        )
        detector = compile_event(parse_event(raw))
        self.assertFalse(detector.observe(Observation("outside_phone", 1, "vision", ("person",))))
        self.assertFalse(detector.observe(Observation("building_phone", 2, "audio", ("gunshot",))))
        self.assertTrue(detector.observe(Observation("building_phone", 3, "vision", ("truck",))))

    def test_example_loads_compiles_and_executes(self):
        event = load_event(ROOT / "ce_definitions" / "iobt_ce3.yaml")
        detector = compile_event(event)
        sequence = [
            Observation("outside_phone", 1, "vision", ("car",), (0.8,)),
            Observation("outside_phone", 2, "vision", ("person",)),
            Observation("building_phone", 3, "vision", ("person",)),
            Observation("building_phone", 4, "audio", ("Gunshot, gunfire",), (0.09,)),
            Observation("outside_phone", 5, "vision", ("person",)),
            Observation("outside_phone", 6, "vision", ()),
            Observation("outside_phone", 10, "vision", ()),
        ]
        self.assertEqual([detector.observe(item) for item in sequence], [False] * 6 + [True])

    def test_compiler_rejects_unknown_label_and_unavailable_color(self):
        unknown = parse_event(minimal_event(atomic_events=[{
            "atomic_event_name": "activity", "triggers": [{"label": "dragon"}],
        }]))
        with self.assertRaisesRegex(EventCompilationError, "unsupported semantic label"):
            compile_event(unknown)

        colored = parse_event(minimal_event(atomic_events=[{
            "atomic_event_name": "activity", "triggers": [{"label": "vehicle", "color": "== white"}],
        }]))
        with self.assertRaisesRegex(EventCompilationError, "does not provide this field"):
            compile_event(colored)

if __name__ == "__main__":
    unittest.main()
