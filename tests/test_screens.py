"""Check screen detection against the saved screenshots in screens/.

Run:  .venv\\Scripts\\python -m unittest discover tests -v
"""
import sys
import unittest
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maacro.vision.ocr import OcrReader          # noqa: E402
from maacro.vision.screens import detect_screen, fuzzy_in  # noqa: E402

SCREENS = ROOT / "screens"

# file -> (screen, extra checks)
EXPECTED = {
    "01_lobby.png": ("lobby", {}),
    "03_join_matchmaking.png": ("join_matchmaking", {}),
    "04_captcha_crop.png": ("captcha", {}),
    "04_captcha_full.png": ("captcha", {}),
    "05_match_found.png": ("match_found", {}),
    "06_vote_start.png": ("vote_start", {}),
    "07_card_pick.png": ("card_pick", {}),
    "08_card_pick_green.png": ("card_pick", {}),
    "09_unit_manager.png": ("unit_manager", {}),
    "11_victory.png": ("end", {"result": "win", "wave": 50}),
    "12_defeat.png": ("end", {"result": "loss", "wave": 50}),
    "13_after_next.png": ("after_end", {}),
    "14_place_red.png": ("in_match", {"placing": True, "wave": 1}),
    "15_place_blue.png": ("in_match", {"placing": True}),
    "16_not_enough_money.png": ("in_match", {"no_money": True, "wave": 5}),
    # Live frames. The "Wave Completed!" banner once got mistaken for the end screen.
    "18_wave_completed_banner.png": ("in_match", {"placing": True, "wave": 7}),
    "19_card_pick_live.png": ("card_pick", {}),
}


class ScreenDetectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = OcrReader()

    def test_screens(self):
        for name, (screen, extra) in EXPECTED.items():
            with self.subTest(name):
                frame = cv2.imread(str(SCREENS / name))
                det = detect_screen(frame, self.reader.read(frame))
                self.assertEqual(det.screen, screen, f"{name}: {[l.text for l in det.lines]}")
                for key, value in extra.items():
                    self.assertEqual(getattr(det, key), value, f"{name}: {key}")


class FuzzyTest(unittest.TestCase):
    def test_loose_matching(self):
        self.assertTrue(fuzzy_in("victory", "VICTORYi!l", 0.7))
        self.assertTrue(fuzzy_in("matchmaking started", "Matchmakihg.started!"))
        self.assertFalse(fuzzy_in("find match", "Match found!"))
        self.assertFalse(fuzzy_in("total time", "Level 112 [137/877]"))


if __name__ == "__main__":
    unittest.main()
