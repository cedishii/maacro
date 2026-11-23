"""The Find Match button when its text isn't read.

On the "Join Matchmaking?" window the "Find Match" label sits on a picture and
the screen reader often doesn't read it (seen live in Misty Village: never
read, only "Join Matchmaking?"). The player's matchmaking code then got the
closest text — the title — and clicked it, which does nothing, every 4 s.

FindMatchSpot is a mixin (first in the bases) that changes only that case:
asked for "find match" and given the title (or nothing), it returns the
button's real place, measured from the title (same layout at the Summer ring
and in Misty Village: 0.195 title-widths right of its centre, 0.26 down).
The player's code in macro.py is unchanged and does the rest (captcha
reading, typing, Submit) with its own timing.
"""
from __future__ import annotations

from .macro import MacroThread
from .vision.ocr import OcrLine
from .vision.screens import _norm

FIND_DX, FIND_DY = 0.195, 0.26     # × the title's width, from its centre
PLAY_DX = -0.195                   # Play Here, mirror-opposite


def matchmaking_title(lines: list[OcrLine]) -> OcrLine | None:
    for line in lines:
        text = _norm(line.text)
        if "joinmatchmaking" in text or ("matchmaking" in text and "join" in text):
            return line
    return None


def find_match_spot(lines: list[OcrLine]) -> OcrLine | None:
    """A small box on the Find Match button, from the "Join Matchmaking?" title."""
    title = matchmaking_title(lines)
    if title is None or title.w < 50:
        return None
    x = title.x + title.w / 2 + FIND_DX * title.w
    y = title.y + title.h / 2 + FIND_DY * title.w
    return OcrLine("Find Match", int(x - 10), int(y - 10), 20, 20)


class FindMatchSpot:
    def _line(self, det, keyword: str, exact: bool = False, threshold: float = 0.8):
        line = MacroThread._line(det, keyword, exact, threshold)
        if _norm(keyword) != "findmatch":
            return line
        if line is None or "matchmaking" in _norm(line.text) or "join" in _norm(line.text):
            spot = find_match_spot(det.lines)
            if spot is not None:
                return spot
        return line
