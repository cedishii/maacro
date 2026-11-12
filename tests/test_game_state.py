import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maacro.game_state import GameTracker  # noqa: E402
from maacro.vision.screens import Detection  # noqa: E402


def feed(tracker, *dets):
    events = []
    for det in dets:
        events += tracker.feed(det)
    return events


def results(events):
    return [v for k, v in events if k == "result"]


class GameTrackerTest(unittest.TestCase):
    def test_win_counted_once_per_match(self):
        t = GameTracker()
        end = Detection(screen="end", result="win", wave=50)
        events = feed(t, *[end] * 10, Detection(screen="after_end"), Detection(screen="after_end"))
        self.assertEqual(results(events), ["win"])

    def test_next_match_counts_again(self):
        t = GameTracker()
        win = Detection(screen="end", result="win")
        loss = Detection(screen="end", result="loss")
        lobby = Detection(screen="lobby")
        events = feed(t, win, win, win, lobby, lobby, loss, loss)
        self.assertEqual(results(events), ["win", "loss"])

    def test_one_bad_read_does_not_change_screen_or_result(self):
        t = GameTracker()
        events = feed(t, Detection(screen="in_match", wave=3), Detection(screen="in_match", wave=3),
                      Detection(screen="lobby"), Detection(screen="in_match", wave=4))
        screens = [v for k, v in events if k == "screen"]
        self.assertEqual(screens, ["in_match"])
        # Mixed reads: needs two agreeing reads before counting.
        t = GameTracker()
        events = feed(t, Detection(screen="end", result="win"), Detection(screen="end", result="loss"),
                      Detection(screen="end", result="loss"))
        self.assertEqual(results(events), ["loss"])

    def test_stray_end_read_does_not_count(self):
        t = GameTracker()
        play = Detection(screen="in_match", wave=7)
        stray = Detection(screen="end", result="loss")
        events = feed(t, play, play, stray, play, stray, play)
        self.assertEqual(results(events), [])

    def test_map_name_settles(self):
        t = GameTracker()
        reads = ["Magic Town", "Magiowo", "Magic Town", "Magic Town", "Magiowo"]
        events = feed(t, *[Detection(screen="in_match", map_name=n) for n in reads])
        self.assertEqual([v for k, v in events if k == "map"], ["Magic Town"])

    def test_wave_tracking(self):
        t = GameTracker()
        events = feed(t, Detection(screen="in_match", wave=1), Detection(screen="in_match", wave=2))
        self.assertEqual([v for k, v in events if k == "wave"], [1, 2])


if __name__ == "__main__":
    unittest.main()
