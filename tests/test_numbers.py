import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maacro.vision import numbers  # noqa: E402
from maacro.vision.numbers import (  # noqa: E402
    BuiltinNumberReader, DigitShapeReader, GuardedNumberReader, extract_number,
    make_number_reader,
)

SCREENS = ROOT / "screens"


class FakeReader:
    name = "fake"

    def __init__(self, result="42", error=None):
        self.result, self.error, self.calls = result, error, 0

    def read(self, frame, box):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class Log:
    def __init__(self):
        self.entries = []

    def __call__(self, message, level):
        self.entries.append((level, message))


FRAME = np.zeros((100, 100, 3), np.uint8)


class GuardTest(unittest.TestCase):
    def test_reads_normally(self):
        guard = GuardedNumberReader(FakeReader("7"), lambda: "card_pick")
        self.assertEqual(guard.read(FRAME, (0, 0, 10, 10)), "7")

    def test_refuses_on_verification_screen(self):
        inner, log = FakeReader("123"), Log()
        guard = GuardedNumberReader(inner, lambda: "captcha", log)
        self.assertIsNone(guard.read(FRAME, (0, 0, 10, 10)))
        self.assertEqual(inner.calls, 0, "the provider must not even be called")
        self.assertEqual(len(log.entries), 1)

    def test_failure_returns_none_and_logs_once(self):
        log = Log()
        guard = GuardedNumberReader(FakeReader(error=RuntimeError("boom")), lambda: "in_match", log)
        self.assertIsNone(guard.read(FRAME, (0, 0, 10, 10)))
        self.assertIsNone(guard.read(FRAME, (0, 0, 10, 10)))
        self.assertEqual([lvl for lvl, _ in log.entries], ["Warn"])


class ProviderTest(unittest.TestCase):
    def setUp(self):
        self.saved = dict(numbers.PROVIDERS)

    def tearDown(self):
        numbers.PROVIDERS.clear()
        numbers.PROVIDERS.update(self.saved)

    def test_unknown_provider_falls_back_to_builtin(self):
        log = Log()
        reader = make_number_reader(lambda: "in_match", provider="screen-number-typer", log=log)
        self.assertEqual(reader.name, "built-in")
        self.assertTrue(any("isn't available" in m for _, m in log.entries))

    def test_provider_that_fails_to_start_falls_back(self):
        def broken():
            raise ImportError("No module named 'screen_numbers'")
        numbers.PROVIDERS["broken"] = broken
        log = Log()
        reader = make_number_reader(lambda: "in_match", provider="broken", log=log)
        self.assertEqual(reader.name, "built-in")
        self.assertTrue(any("couldn't start" in m for _, m in log.entries))

    def test_extra_provider_can_be_registered(self):
        numbers.PROVIDERS["fake"] = lambda: FakeReader("9")
        reader = make_number_reader(lambda: "in_match", provider="fake")
        self.assertEqual(reader.read(FRAME, (0, 0, 10, 10)), "9")

    def test_extract_number(self):
        self.assertEqual(extract_number("Upg: 5000¥"), "5000")
        self.assertEqual(extract_number("007"), "007")
        self.assertIsNone(extract_number("Cancel"))
        self.assertEqual(extract_number("ooo", lookalikes=True), "000")


class VoteDigitsTest(unittest.TestCase):
    """Real card vote boxes from the screenshots."""
    CASES = [
        ("07_card_pick.png", (239, 439, 297, 501), "0"),
        ("07_card_pick.png", (479, 439, 537, 501), "3"),
        ("08_card_pick_green.png", (211, 443, 269, 505), "5"),
        ("08_card_pick_green.png", (691, 443, 749, 505), "1"),
    ]

    def test_shape_reader(self):
        reader = DigitShapeReader()
        for name, (l, t, r, b), want in self.CASES:
            with self.subTest(name=name, want=want):
                frame = cv2.imread(str(SCREENS / name))
                self.assertEqual(reader.read_image(frame[t:b, l:r]), want)

    def test_builtin_reader(self):
        reader = BuiltinNumberReader()
        for name, box, want in self.CASES:
            with self.subTest(name=name, want=want):
                self.assertEqual(reader.read(cv2.imread(str(SCREENS / name)), box), want)

    def test_empty_box(self):
        self.assertIsNone(BuiltinNumberReader().read(FRAME, (50, 50, 50, 50)))


if __name__ == "__main__":
    unittest.main()
