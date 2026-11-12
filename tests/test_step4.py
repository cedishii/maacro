"""Card picking, placement spots, upgrade order and config."""
import sys
import tempfile
import unittest
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maacro.config import MacroConfig, parse_keys  # noqa: E402
from maacro.placement import candidate_spots, find_green_buttons, spots_to_try, upgrade_order  # noqa: E402
from maacro.vision.cards import Card, choose_card, find_cards, read_votes, vote_button  # noqa: E402
from maacro.vision.numbers import BuiltinNumberReader  # noqa: E402
from maacro.vision.ocr import OcrLine, OcrReader  # noqa: E402

SCREENS = ROOT / "screens"


def card(i, color, votes=None):
    return Card(i, (i * 100.0, 50.0), color, (0, 0, 1, 1), votes)


class ChooseCardTest(unittest.TestCase):
    def test_green_beats_votes(self):
        picked, _ = choose_card([card(0, "red", 5), card(1, "red", 0), card(2, "green", 1)])
        self.assertEqual(picked.index, 2)

    def test_other_colour_beats_red(self):
        picked, _ = choose_card([card(0, "red", 5), card(1, "other", 0), card(2, "red", 1)])
        self.assertEqual(picked.index, 1)

    def test_all_red_most_votes(self):
        picked, _ = choose_card([card(0, "red", 0), card(1, "red", 3), card(2, "red", 0)])
        self.assertEqual(picked.index, 1)

    def test_all_red_tie_takes_first_highest(self):
        picked, _ = choose_card([card(0, "red", 2), card(1, "red", 0), card(2, "red", 2)])
        self.assertEqual(picked.index, 0)

    def test_unreadable_votes_take_middle(self):
        picked, reason = choose_card([card(0, "red"), card(1, "red"), card(2, "red")])
        self.assertEqual(picked.index, 1)
        self.assertIn("middle", reason)

    def test_no_cards(self):
        self.assertIsNone(choose_card([]))


class CardScreenshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr = OcrReader()
        cls.numbers = BuiltinNumberReader(cls.ocr)

    def analyse(self, name):
        frame = cv2.imread(str(SCREENS / name))
        lines = self.ocr.read(frame)
        cards = find_cards(frame, lines)
        read_votes(frame, cards, self.numbers)
        return cards, lines

    def test_all_red(self):
        cards, _ = self.analyse("07_card_pick.png")
        self.assertEqual([(c.color, c.votes) for c in cards], [("red", 0), ("red", 3), ("red", 0)])
        self.assertEqual(choose_card(cards)[0].index, 1)

    def test_live_card_pick_with_hidden_footer(self):
        # "Vote ends in" is covered by a player's name here; cards are mid-animation.
        cards, _ = self.analyse("19_card_pick_live.png")
        self.assertEqual(len(cards), 3)
        self.assertEqual([c.color for c in cards], ["red", "red", "red"])
        xs = [c.center[0] for c in cards]
        self.assertTrue(560 < xs[0] < 760 and 860 < xs[1] < 1060 and 1160 < xs[2] < 1360, xs)

    def test_green_card(self):
        cards, lines = self.analyse("08_card_pick_green.png")
        self.assertEqual([c.color for c in cards], ["red", "red", "green"])
        self.assertEqual([c.votes for c in cards], [5, 0, 1])
        self.assertEqual(choose_card(cards)[0].index, 2)
        x, y = vote_button(lines)
        self.assertTrue(330 < x < 470 and 550 < y < 600, (x, y))   # the green Vote button


class PlacementTest(unittest.TestCase):
    def test_spots_avoid_ui_and_used_spots(self):
        spots = candidate_spots(1920, 1080)
        self.assertGreater(len(spots), 10)
        for x, y in spots:
            self.assertTrue(0.13 * 1920 < x < 0.84 * 1920 and 0.14 * 1080 < y < 0.78 * 1080)
        fewer = candidate_spots(1920, 1080, used=[spots[0]])
        self.assertNotIn(spots[0], fewer)

    def test_spots_next_to_placed_units_come_first(self):
        near, general = spots_to_try(1920, 1080, [(900.0, 500.0)])
        self.assertTrue(near)
        for x, y in near:
            self.assertLess(abs(x - 900) + abs(y - 500), 0.2 * 1080)
        self.assertEqual(spots_to_try(1920, 1080, [])[0], [])

    def test_upgrade_order_follows_priority(self):
        lines = [
            OcrLine("Elyssia (Abyssal)", 50, 100, 80, 12), OcrLine("Upg: 5000¥", 150, 95, 80, 16),
            OcrLine("C.E.O.", 50, 300, 40, 12), OcrLine("Upg: 900¥", 150, 295, 80, 16),
            OcrLine("Bulby", 300, 300, 40, 12), OcrLine("Upg: 1200¥", 400, 295, 80, 16),
        ]
        order = upgrade_order(lines, {"1": "Elyssia", "5": "C.E.O.", "6": "Bulby"}, ["6", "5", "1"])
        self.assertEqual([b.text for b in order], ["Upg: 1200¥", "Upg: 900¥", "Upg: 5000¥"])

    def test_green_upgrade_buttons_live(self):
        # Live unit overview: Bulby and both Elyssias upgradeable, the 3 C.E.O.s at Max.
        frame = cv2.imread(str(SCREENS / "20_unit_overview_live.png"))
        buttons = find_green_buttons(frame)
        self.assertEqual(len(buttons), 3)
        order = upgrade_order(OcrReader().read(frame), MacroConfig().unit_names, ["6", "5", "1"], buttons)
        self.assertEqual((order[0].x, order[0].y), (buttons[0].x, buttons[0].y))   # Bulby first

    def test_no_green_buttons_elsewhere(self):
        for name in ("01_lobby.png", "18_wave_completed_banner.png", "19_card_pick_live.png", "11_victory.png"):
            with self.subTest(name):
                self.assertEqual(find_green_buttons(cv2.imread(str(SCREENS / name))), [])

    def test_upgrade_buttons_on_screenshot(self):
        frame = cv2.imread(str(SCREENS / "09_unit_manager.png"))
        order = upgrade_order(OcrReader().read(frame), MacroConfig().unit_names, ["6", "5", "1"])
        self.assertEqual(len(order), 1)    # one unit not maxed, the rest say Max


class ConfigTest(unittest.TestCase):
    def test_defaults_match_flow(self):
        config = MacroConfig()
        self.assertEqual(config.placement_order, ["6", "5", "5", "5", "1", "1"])
        self.assertEqual(config.upgrade_priority, ["6", "5", "1"])

    def test_parse_keys(self):
        self.assertEqual(parse_keys("6, 5 5"), ["6", "5", "5"])
        with self.assertRaises(ValueError):
            parse_keys("6 7")

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config = MacroConfig(placement_order=["1", "2"], auto_card_pick=False)
            config.save(path)
            loaded = MacroConfig.load(path)
            self.assertEqual(loaded.placement_order, ["1", "2"])
            self.assertFalse(loaded.auto_card_pick)
            self.assertEqual(MacroConfig.load(Path(tmp) / "missing.json").placement_order,
                             MacroConfig().placement_order)


if __name__ == "__main__":
    unittest.main()
