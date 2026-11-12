"""Placing units: the hotbar counter is the proof of a placement."""
import sys
import unittest
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maacro.config import MacroConfig  # noqa: E402
from maacro.macro import MacroThread, MatchState  # noqa: E402
from maacro.placement import UI_BOTTOM, UI_LEFT, UI_RIGHT, UI_TOP, path_spots, placeable_spots  # noqa: E402
from maacro.vision.hotbar import read_unit_count  # noqa: E402
from maacro.vision.ocr import OcrReader  # noqa: E402

SCREENS = ROOT / "screens"


class CounterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrReader()

    def test_counters_on_screenshots(self):
        cases = {
            "14_place_red.png": (0, 2),
            "15_place_blue.png": (0, 2),
            "18_wave_completed_banner.png": (0, 3),
            "22_placing_2of2.png": (2, 2),      # red counter = full
        }
        for name, want in cases.items():
            with self.subTest(name):
                self.assertEqual(read_unit_count(cv2.imread(str(SCREENS / name)), self.ocr), want)

    def test_counter_above_the_pressed_card(self):
        cases = {
            ("23_bulby_1of1_red_roof.png", 6): (1, 1),     # red "1/1" on a red roof
            ("24_slot2_0of4_banner.png", 2): (0, 4),       # game's open-top 4, banner nearby
            ("25_slot3_2of3.png", 3): (2, 3),
            ("18_wave_completed_banner.png", 5): (0, 3),   # sparkles above the counter
            ("20_unit_overview_live.png", 1): None,
            ("01_lobby.png", 3): None,
        }
        for (name, slot), want in cases.items():
            with self.subTest(name):
                frame = cv2.imread(str(SCREENS / name))
                self.assertEqual(read_unit_count(frame, self.ocr, slot), want)

    def test_no_counter_when_not_placing(self):
        for name in ("20_unit_overview_live.png", "01_lobby.png", "11_victory.png"):
            with self.subTest(name):
                self.assertIsNone(read_unit_count(cv2.imread(str(SCREENS / name)), self.ocr))


class _Stub:
    hwnd = None


class ApplyCountTest(unittest.TestCase):
    def make(self, order=("6", "5", "5", "5", "1", "1")):
        macro = MacroThread(_Stub(), _Stub(), MacroConfig(placement_order=list(order)))
        macro.match = MatchState(pending=list(order))
        self.logs = []
        macro.log.connect(lambda message, level: self.logs.append(message))
        return macro

    def test_first_read_is_only_a_baseline(self):
        macro = self.make()
        macro._apply_count("5", 0, 3)
        self.assertEqual(macro.match.placed, 0)
        self.assertEqual(macro.match.pending.count("5"), 3)

    def test_counter_going_up_is_a_placement(self):
        macro = self.make()
        macro._apply_count("5", 0, 3)
        macro._apply_count("5", 1, 3, spot=(10.0, 20.0))
        self.assertEqual(macro.match.placed, 1)
        self.assertEqual(macro.match.pending.count("5"), 2)
        self.assertEqual(macro.match.spots, [(10.0, 20.0)])

    def test_same_count_is_not_a_placement(self):
        macro = self.make()
        macro._apply_count("6", 0, 1)
        macro._apply_count("6", 0, 1)
        self.assertEqual(macro.match.placed, 0)
        self.assertIn("6", macro.match.pending)

    def test_full_unit_is_dropped(self):
        macro = self.make()
        macro._apply_count("1", 2, 2)        # player already placed both
        self.assertNotIn("1", macro.match.pending)

    def test_partly_placed_by_player(self):
        macro = self.make()
        macro._apply_count("5", 1, 3)        # one C.E.O. already down
        self.assertEqual(macro.match.pending.count("5"), 2)

    def test_game_limit_below_plan(self):
        macro = self.make(order=("5", "5", "5", "5"))
        macro._apply_count("5", 0, 3)        # the game only allows 3
        self.assertEqual(macro.match.pending.count("5"), 3)


class PlaceableSpotsTest(unittest.TestCase):
    def test_spots_avoid_red_and_spread_out(self):
        frame = cv2.imread(str(SCREENS / "14_place_red.png"))
        h, w = frame.shape[:2]
        spots = placeable_spots(frame)
        for i, (x, y) in enumerate(spots):
            b, g, r = (int(v) for v in frame[int(y), int(x)])
            self.assertFalse(r > g + 50 and r > b + 50, f"spot {i} is on red")
            for x2, y2 in spots[i + 1:]:
                self.assertGreaterEqual(((x - x2) ** 2 + (y - y2) ** 2) ** 0.5, 0.05 * h - 1)


class PathSpotsTest(unittest.TestCase):
    def test_spots_stay_out_of_the_ui(self):
        frame = cv2.imread(str(SCREENS / "22_placing_2of2.png"))
        h, w = frame.shape[:2]
        spots = path_spots(frame)
        self.assertTrue(spots)
        for x, y in spots:
            self.assertTrue(UI_LEFT * w < x < UI_RIGHT * w and UI_TOP * h < y < UI_BOTTOM * h)


if __name__ == "__main__":
    unittest.main()
