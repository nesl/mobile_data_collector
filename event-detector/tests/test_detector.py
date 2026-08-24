import json
import unittest

from detector import SequenceDetector, labels_from_payload


class DetectorTests(unittest.TestCase):
    def test_mobile_payload_and_sequence(self):
        body = {
            "dev_id": "phone-1",
            "detectionResults": [{"bboxes": [{"clsName": "person"}]}],
            "audioResults": [{"events": [{"first": "gunshot", "second": 0.9}]}],
        }
        device, labels = labels_from_payload(("detection::" + json.dumps(body)).encode())
        self.assertEqual(device, "phone-1")
        self.assertEqual(labels, ["person", "gunshot"])
        detector = SequenceDetector("person", "gunshot", 30)
        self.assertTrue(detector.observe(labels, now=10))

    def test_sequence_expires(self):
        detector = SequenceDetector("person", "gunshot", 5)
        self.assertFalse(detector.observe(["person"], now=10))
        self.assertFalse(detector.observe(["gunshot"], now=16))


if __name__ == "__main__":
    unittest.main()
