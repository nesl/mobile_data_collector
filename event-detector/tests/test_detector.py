import json
import unittest

from language import build_event
from runtime.detector import labels_from_payload, observations_from_payload
from runtime.fsm import AtomicEvent, ComplexEventFSM, Observation, Trigger


def observation(device, timestamp, modality, *labels):
    return Observation(device, timestamp, modality, labels)


class DetectorTests(unittest.TestCase):
    def test_mobile_payload_preserves_frames_and_timestamps(self):
        body = {
            "dev_id": "phone-1",
            "detectionResults": [
                {"timestamp": 10000, "dev_id": "phone-1", "bboxes": [{"clsName": "person", "cnf": 0.9}]},
                {"timestamp": 11000, "dev_id": "phone-1", "bboxes": []},
            ],
            "audioResults": [
                {"timestamp": 10500, "events": [{"first": "Gunshot, gunfire", "second": 0.8}]}
            ],
        }
        payload = ("detection::" + json.dumps(body)).encode()
        items = observations_from_payload(payload, min_confidence=0.5)
        self.assertEqual([(x.timestamp, x.modality) for x in items], [(10, "vision"), (10.5, "audio"), (11, "vision")])
        self.assertEqual(items[-1].labels, ())
        self.assertEqual(items[1].scores, (0.8,))
        self.assertEqual(labels_from_payload(payload), ("phone-1", ["person", "Gunshot, gunfire"]))

    def test_iobt_ce3_across_two_devices(self):
        detector = build_event("iobt_ce3")
        sequence = [
            observation("outside_phone", 1, "vision", "car"),
            observation("outside_phone", 2, "vision", "person"),
            observation("building_phone", 3, "vision", "person"),
            observation("building_phone", 4, "audio", "Gunshot, gunfire"),
            observation("outside_phone", 5, "vision", "person"),
            observation("outside_phone", 6, "vision"),
            observation("outside_phone", 10, "vision"),
        ]
        self.assertEqual([detector.observe(item) for item in sequence], [False] * 6 + [True])

    def test_gunshot_uses_yamnet_substring(self):
        detector = build_event("gunshot")
        self.assertTrue(detector.observe(
            observation("building_phone", 1, "audio", "Gunshot, gunfire")
        ))

    def test_related_gunshot_label(self):
        detector = build_event("gunshot")
        self.assertTrue(detector.observe(
            observation("building_phone", 1, "audio", "Machine gun")
        ))
        second_detector = build_event("gunshot")
        self.assertFalse(second_detector.observe(
            Observation("building_phone", 2, "audio", ("Cap gun",), (0.8,))
        ))

    def test_low_scoring_gunshot_is_rejected(self):
        detector = build_event("gunshot")
        item = Observation("building_phone", 1, "audio", ("Gunshot, gunfire",), (0.049,))
        self.assertFalse(detector.observe(item))

    def test_confirmed_live_gunshot_score_is_accepted(self):
        detector = build_event("gunshot")
        item = Observation("building_phone", 1, "audio", ("Gunshot, gunfire",), (0.05859375,))
        self.assertTrue(detector.observe(item))

    def test_car_gunshot_person(self):
        detector = build_event("car_gunshot_person")
        sequence = [
            observation("outside_phone", 1, "vision", "car"),
            Observation("building_phone", 2, "audio", ("Gunshot, gunfire",), (0.1,)),
            observation("outside_phone", 3, "vision", "person"),
        ]
        self.assertEqual([detector.observe(item) for item in sequence], [False, False, True])
        self.assertTrue(detector.status()["completed"])
        self.assertEqual(detector.status()["current_atomic_event_index"], 3)
        self.assertFalse(detector.observe(observation("outside_phone", 4, "vision", "car")))
        self.assertEqual(detector.status()["current_atomic_event_index"], 3)

    def test_car_event_rejects_low_confidence_gunshot(self):
        detector = build_event("car_gunshot_person")
        detector.observe(observation("outside_phone", 1, "vision", "car"))
        first = Observation("building_phone", 2, "audio", ("Gunshot, gunfire",), (0.079,))
        self.assertFalse(detector.observe(first))
        self.assertEqual(detector.status()["current_atomic_event_index"], 1)

    def test_iobt_ce2_repeated_arrivals(self):
        detector = build_event("iobt_ce2")
        result = False
        timestamp = 0
        for _ in range(3):
            result = detector.observe(observation("outside_phone", timestamp, "vision", "car"))
            result = detector.observe(observation("outside_phone", timestamp + 3, "vision", "car"))
            result = detector.observe(observation("outside_phone", timestamp + 4, "vision"))
            result = detector.observe(observation("outside_phone", timestamp + 8, "vision"))
            timestamp += 9
        self.assertTrue(result)

    def test_hold_resets_if_object_reappears(self):
        detector = build_event("iobt_ce1")
        sequence = [
            observation("outside_phone", 1, "vision", "car", "car", "car", "car"),
            observation("outside_phone", 2, "vision", "truck"),
            observation("outside_phone", 3, "vision"),
            observation("outside_phone", 6, "vision", "car"),
            observation("outside_phone", 7, "vision"),
            observation("outside_phone", 11, "vision"),
        ]
        self.assertEqual([detector.observe(item) for item in sequence], [False] * 5 + [True])

    def test_within_accepts_deadline_and_rejects_late_event(self):
        def build():
            result = ComplexEventFSM("within", [
                AtomicEvent("person", (Trigger(lambda item: "person" in item.labels),)),
                AtomicEvent("gunshot", (Trigger(lambda item: "gunshot" in item.labels),)),
            ])
            result.add_within_constraint("person", "gunshot", 5)
            return result

        on_time = build()
        self.assertFalse(on_time.observe(observation("any", 10, "vision", "person")))
        self.assertTrue(on_time.observe(observation("any", 15, "audio", "gunshot")))

        late = build()
        late.observe(observation("any", 10, "vision", "person"))
        self.assertFalse(late.observe(observation("any", 15.1, "audio", "gunshot")))
        self.assertTrue(late.status()["failed"])

    def test_explicit_and_or_and_any_device(self):
        both = AtomicEvent("multisensor", triggers=(
            Trigger(lambda item: "person" in item.labels, "camera", "vision"),
            Trigger(lambda item: "gunshot" in item.labels, "mic", "audio"),
        ), trigger_logic="AND")
        either = AtomicEvent("either", triggers=(
            Trigger(lambda item: "car" in item.labels),
            Trigger(lambda item: "truck" in item.labels),
        ), trigger_logic="OR")
        detector = ComplexEventFSM("composition", [both, either])
        self.assertFalse(detector.observe(observation("camera", 1, "vision", "person")))
        self.assertFalse(detector.observe(observation("mic", 2, "audio", "gunshot")))
        self.assertTrue(detector.observe(observation("unregistered", 3, "vision", "truck")))

    def test_and_has_default_and_configurable_deadline(self):
        def build(deadline=120):
            return ComplexEventFSM("bounded-and", [AtomicEvent("both", triggers=(
                Trigger(lambda item: "person" in item.labels),
                Trigger(lambda item: "gunshot" in item.labels),
            ), and_within_seconds=deadline)])

        default = build()
        self.assertFalse(default.observe(observation("x", 1, "vision", "person")))
        self.assertFalse(default.observe(observation("x", 121.1, "audio", "gunshot")))
        self.assertTrue(default.status()["failed"])

        configured = build(5)
        configured.observe(observation("x", 10, "vision", "person"))
        self.assertTrue(configured.observe(observation("x", 15, "audio", "gunshot")))

    def test_holds_api(self):
        first = AtomicEvent("present", (Trigger(lambda item: "car" in item.labels),))
        held = AtomicEvent("absent", (Trigger(lambda item: not item.labels),))
        detector = ComplexEventFSM("actions", [first, held])
        detector.add_holds_constraint(held, 2)
        self.assertFalse(detector.observe(observation("x", 1, "vision", "car")))
        self.assertFalse(detector.observe(observation("x", 2, "vision")))
        self.assertTrue(detector.observe(observation("x", 4, "vision")))

    def test_unknown_message_is_ignored(self):
        self.assertEqual(observations_from_payload(b"handshake::{}"), [])


if __name__ == "__main__":
    unittest.main()
