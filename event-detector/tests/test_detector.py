import json
import unittest

from definitions import build_event
from detector import SequenceDetector, labels_from_payload, observations_from_payload
from fsm import Observation


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
        detector = build_event("iobt_ce3", "outside", "building")
        sequence = [
            observation("outside", 1, "vision", "car"),
            observation("outside", 2, "vision", "person"),
            observation("building", 3, "vision", "person"),
            observation("building", 4, "audio", "Gunshot, gunfire"),
            observation("outside", 5, "vision", "person"),
            observation("outside", 6, "vision"),
            observation("outside", 10, "vision"),
        ]
        self.assertEqual([detector.observe(item) for item in sequence], [False] * 6 + [True])

    def test_gunshot_uses_yamnet_substring(self):
        detector = build_event("gunshot", "outside", "building")
        self.assertTrue(detector.observe(
            observation("building", 1, "audio", "Gunshot, gunfire")
        ))

    def test_related_gunshot_label(self):
        detector = build_event("gunshot", "outside", "building")
        self.assertTrue(detector.observe(
            observation("building", 1, "audio", "Machine gun")
        ))
        second_detector = build_event("gunshot", "outside", "building")
        self.assertFalse(second_detector.observe(
            Observation("building", 2, "audio", ("Cap gun",), (0.8,))
        ))

    def test_low_scoring_gunshot_is_rejected(self):
        detector = build_event("gunshot", "outside", "building")
        item = Observation("building", 1, "audio", ("Gunshot, gunfire",), (0.049,))
        self.assertFalse(detector.observe(item))

    def test_confirmed_live_gunshot_score_is_accepted(self):
        detector = build_event("gunshot", "outside", "building")
        item = Observation("building", 1, "audio", ("Gunshot, gunfire",), (0.05859375,))
        self.assertTrue(detector.observe(item))

    def test_car_gunshot_person(self):
        detector = build_event("car_gunshot_person", "outside", "building")
        sequence = [
            observation("outside", 1, "vision", "vehicle"),
            Observation("building", 2, "audio", ("Gunshot, gunfire",), (0.1,)),
            Observation("building", 2.5, "audio", ("Gunshot, gunfire",), (0.1,)),
            observation("outside", 3, "vision", "person"),
        ]
        self.assertEqual([detector.observe(item) for item in sequence], [False, False, False, True])
        self.assertTrue(detector.status()["completed"])
        self.assertEqual(detector.status()["current_step"], 3)
        self.assertFalse(detector.observe(observation("outside", 4, "vision", "car")))
        self.assertEqual(detector.status()["current_step"], 3)

    def test_car_event_rejects_single_or_duplicate_gunshot_window(self):
        detector = build_event("car_gunshot_person", "outside", "building")
        detector.observe(observation("outside", 1, "vision", "vehicle"))
        first = Observation("building", 2, "audio", ("Gunshot, gunfire",), (0.2,))
        self.assertFalse(detector.observe(first))
        self.assertFalse(detector.observe(first))
        self.assertEqual(detector.status()["current_step"], 1)

    def test_iobt_ce2_repeated_arrivals(self):
        detector = build_event("iobt_ce2", "outside", "building")
        result = False
        timestamp = 0
        for _ in range(3):
            result = detector.observe(observation("outside", timestamp, "vision", "car"))
            result = detector.observe(observation("outside", timestamp + 3, "vision", "car"))
            result = detector.observe(observation("outside", timestamp + 4, "vision"))
            result = detector.observe(observation("outside", timestamp + 8, "vision"))
            timestamp += 9
        self.assertTrue(result)

    def test_hold_resets_if_object_reappears(self):
        detector = build_event("iobt_ce1", "outside", "building")
        sequence = [
            observation("outside", 1, "vision", "car", "car", "car", "car"),
            observation("outside", 2, "vision", "truck"),
            observation("outside", 3, "vision"),
            observation("outside", 6, "vision", "car"),
            observation("outside", 7, "vision"),
            observation("outside", 11, "vision"),
        ]
        self.assertEqual([detector.observe(item) for item in sequence], [False] * 5 + [True])

    def test_sequence_detector_remains_compatible(self):
        detector = SequenceDetector("person", "gunshot", 5)
        self.assertFalse(detector.observe(["person"], now=10))
        self.assertFalse(detector.observe(["gunshot"], now=16))

    def test_unknown_message_is_ignored(self):
        self.assertEqual(observations_from_payload(b"handshake::{}"), [])


if __name__ == "__main__":
    unittest.main()
