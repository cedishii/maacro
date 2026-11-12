"""Map zones, smarter card picks, leaderboard closing and run records."""
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maacro.maps import extract_zones, find_map, load_maps  # noqa: E402
from maacro.runs import read_run  # noqa: E402
from maacro.vision.cards import (Card, choose_card, find_cards, needs_votes,  # noqa: E402
                                 predicted_vote_button, read_card_texts)
from maacro.vision.ocr import OcrReader  # noqa: E402
from maacro.vision.screens import detect_screen  # noqa: E402

SCREENS = ROOT / "screens"
MAPS = ROOT / "maps"


class MapZonesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrReader()
        cls.maps = load_maps()

    def test_haunted_mansion_is_saved(self):
        self.assertIn("Haunted Mansion", [m.name for m in self.maps])

    def test_two_zones_from_the_white_circles(self):
        image = cv2.imread(str(MAPS / "haunted_mansion_source.png"))
        self.assertEqual(len(extract_zones(image)), 2)

    def test_map_recognised_on_the_loading_screen(self):
        frame = cv2.imread(str(SCREENS / "27_loading_haunted_mansion.png"))
        found = find_map(self.maps, self.ocr.read(frame))
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "Haunted Mansion")

    def test_other_maps_not_mistaken_for_it(self):
        frame = cv2.imread(str(SCREENS / "19_card_pick_live.png"))      # Magic Town
        self.assertIsNone(find_map(self.maps, self.ocr.read(frame)))

    def test_spots_fall_inside_the_zones(self):
        zones_map = next(m for m in self.maps if m.name == "Haunted Mansion")
        image = cv2.imread(str(MAPS / "haunted_mansion_source.png"))
        spots = zones_map.spots(self.ocr.read(image), image.shape[1], image.shape[0])
        self.assertGreater(len(spots), 50)
        polygons = [np.array(z, np.float32) for z in zones_map.zones]
        for x, y in spots:
            self.assertTrue(any(cv2.pointPolygonTest(p, (x, y), False) >= 0 for p in polygons))

    def test_scaled_screen_lines_up(self):
        # The same screenshot at 1.25× must give the same spots, scaled.
        zones_map = next(m for m in self.maps if m.name == "Haunted Mansion")
        image = cv2.imread(str(MAPS / "haunted_mansion_source.png"))
        big = cv2.resize(image, None, fx=1.25, fy=1.25, interpolation=cv2.INTER_CUBIC)
        fit = zones_map.transform(self.ocr.read(big), big.shape[1], big.shape[0])
        self.assertIsNotNone(fit)
        self.assertAlmostEqual(fit[0], 1.25, delta=0.08)


class CardPriorityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrReader()

    def pick(self, name):
        frame = cv2.imread(str(SCREENS / name))
        lines = self.ocr.read(frame)
        cards = find_cards(frame, lines)
        read_card_texts(cards, lines)
        return choose_card(cards)[0].index, cards, lines

    def test_all_red_takes_enemy_health(self):
        self.assertEqual(self.pick("07_card_pick.png")[0], 1)       # Spellproof / Health / Resistant
        self.assertEqual(self.pick("19_card_pick_live.png")[0], 2)  # Spellproof / Regen / Health

    def test_green_still_wins(self):
        self.assertEqual(self.pick("08_card_pick_green.png")[0], 2)

    def test_lower_pearls_bonus_beats_health(self):
        cards = [Card(0, (0, 0), "red", (0, 0, 1, 1), text="Enemy Health +150% SummerPearls", pearls=150),
                 Card(1, (0, 0), "red", (0, 0, 1, 1), text="Spellproof +30% SummerPearls Magic", pearls=30)]
        self.assertEqual(choose_card(cards)[0].index, 1)

    def test_physical_only_beats_both_resists(self):
        cards = [Card(0, (0, 0), "red", (0, 0, 1, 1), text="Resistant +30% Physical Resist Magic Resist", pearls=30),
                 Card(1, (0, 0), "red", (0, 0, 1, 1), text="Plated +30% +75 Enemy Physical Resist", pearls=30)]
        self.assertEqual(choose_card(cards)[0].index, 1)

    def test_blue_beats_red(self):
        cards = [Card(0, (0, 0), "red", (0, 0, 1, 1), text="Enemy Health +30%", pearls=30),
                 Card(1, (0, 0), "other", (0, 0, 1, 1), text="+ Range")]
        self.assertEqual(choose_card(cards)[0].index, 1)

    def test_votes_only_read_on_a_tie(self):
        _, cards, _ = self.pick("19_card_pick_live.png")
        self.assertFalse(needs_votes(cards))        # Health wins outright

    def test_vote_button_predicted_near_the_real_one(self):
        lines = self.ocr.read(cv2.imread(str(SCREENS / "19_card_pick_live.png")))
        x, y = predicted_vote_button(lines)
        self.assertLess(abs(x - 857) + abs(y - 815), 25)


class LeaderboardTest(unittest.TestCase):
    def test_close_button_found_only_when_open(self):
        ocr = OcrReader()
        frame = cv2.imread(str(SCREENS / "28_leaderboard_open.png"))
        x, y = detect_screen(frame, ocr.read(frame)).leaderboard_close
        self.assertLess(abs(x - 292) + abs(y - 55), 15)
        for name in ("21_user_placed_units.png", "24_slot2_0of4_banner.png", "25_slot3_2of3.png"):
            frame = cv2.imread(str(SCREENS / name))
            self.assertIsNone(detect_screen(frame, ocr.read(frame)).leaderboard_close, name)


class RunRecordTest(unittest.TestCase):
    def test_end_screens(self):
        ocr = OcrReader()
        cases = [("11_victory.png", "win", 11354, "26:27"),
                 ("12_defeat.png", "loss", 6111, "30:53"),
                 ("26_defeat_gold_upgrade.png", "loss", 4391, "30:33")]
        for name, result, pearls, duration in cases:
            with self.subTest(name):
                frame = cv2.imread(str(SCREENS / name))
                record = read_run(frame, ocr.read(frame), ocr, result)
                self.assertEqual((record.pearls, record.waves, record.duration), (pearls, 50, duration))


if __name__ == "__main__":
    unittest.main()
