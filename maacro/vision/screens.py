"""Work out which game screen is showing, from the text on it.

The game's font is chunky, so the text recognition makes small mistakes
("VICTORYi!l", "waye 50"). Keywords are therefore matched loosely.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import numpy as np

from .ocr import OcrLine

SCREEN_LABELS = {
    "lobby": "Lobby",
    "loading": "Loading",
    "join_matchmaking": "Join Matchmaking",
    "captcha": "Captcha",
    "match_found": "Match found",
    "vote_start": "Vote start",
    "in_match": "In match",
    "card_pick": "Card pick",
    "unit_manager": "Unit manager",
    "end": "Match over",
    "after_end": "Return to lobby",
    "unknown": "—",
}

LOBBY_WORDS = ("units", "items", "trade", "dungeon", "store", "summon",
               "servers", "quests", "guild", "profile", "areas")
WAVE_RE = re.compile(r"\bwa[vy]e\W{0,3}(\d{1,3})\b")


@dataclass
class Detection:
    screen: str = "unknown"
    wave: int | None = None
    map_name: str | None = None
    result: str | None = None        # "win" / "loss" on the end screen
    placing: bool = False            # the Place / Rotate / Cancel menu is open
    no_money: bool = False           # "Not enough money!" banner
    yen: int | None = None           # money shown above the hotbar
    leaderboard_close: tuple[float, float] | None = None   # the × of an open damage leaderboard
    # An item drop (charm, portal…) waiting for "Click anywhere to continue":
    # (item name, rarity), either may be "" if not read.
    drop: tuple[str, str] | None = None
    lines: list[OcrLine] = field(default_factory=list)

    @property
    def label(self) -> str:
        return SCREEN_LABELS.get(self.screen, self.screen)


# --- loose text matching ---------------------------------------------------
def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def fuzzy_in(keyword: str, text: str, threshold: float = 0.8) -> bool:
    """True if `keyword` appears in `text`, allowing a few wrong letters."""
    key, hay = _norm(keyword), _norm(text)
    if not key or not hay:
        return False
    if key in hay:
        return True
    n = len(key)
    best = 0.0
    for size in (n - 1, n, n + 1):
        if size <= 0:
            continue
        for start in range(0, max(1, len(hay) - size + 1)):
            ratio = SequenceMatcher(None, key, hay[start:start + size]).ratio()
            if ratio > best:
                best = ratio
                if best >= threshold:
                    return True
    return best >= threshold


def _find(lines: list[OcrLine], keyword: str, threshold: float = 0.8) -> OcrLine | None:
    for line in lines:
        if fuzzy_in(keyword, line.text, threshold):
            return line
    return None


def _any(lines: list[OcrLine], *keywords: str, threshold: float = 0.8) -> bool:
    return any(_find(lines, k, threshold) for k in keywords)


# --- details ---------------------------------------------------------------
def _wave(lines: list[OcrLine]) -> int | None:
    for line in lines:
        match = WAVE_RE.search(line.text.lower())
        if match:
            return int(match.group(1))
    return None


YEN_RE = re.compile(r"^(\d{1,8})\s*[¥YyM]$")


def _yen(lines: list[OcrLine], width: int, height: int) -> int | None:
    """Money above the hotbar, e.g. '1187¥' (the ¥ is often read as Y or M)."""
    for line in lines:
        if line.y < height * 0.6 or abs(line.center_x - width / 2) > width * 0.2:
            continue
        match = YEN_RE.match(line.text.replace(",", "").strip())
        if match:
            return int(match.group(1))
    return None


def _map_name(lines: list[OcrLine], width: int, height: int) -> str | None:
    """The map title shown at the top middle during a match, e.g. 'Sky Island Summer Hunt'."""
    for line in lines:
        if line.y > height * 0.09 or abs(line.center_x - width / 2) > width * 0.25:
            continue
        text = re.sub(r"[^A-Za-z0-9 '\-]", "", line.text).strip()
        if sum(c.isalpha() for c in text) >= 5 and "/" not in line.text \
                and not WAVE_RE.search(text.lower()):
            return text
    return None


def _title_color(frame: np.ndarray, anchor: OcrLine) -> str | None:
    """Colour of the big title above 'Total Time': yellow = win, red = loss."""
    h = max(anchor.h, 8)
    top = max(0, anchor.y - 6 * h)
    bottom = max(top + 1, int(anchor.y - 2.2 * h))
    left = max(0, int(anchor.center_x - 1.5 * anchor.w))
    right = min(frame.shape[1], int(anchor.center_x + 1.5 * anchor.w))
    band = frame[top:bottom, left:right, :3].astype(np.int16)
    if band.size == 0:
        return None
    b, g, r = band[..., 0], band[..., 1], band[..., 2]
    red = int(np.count_nonzero((r > 170) & (g < 70) & (b < 70)))
    yellow = int(np.count_nonzero((r > 200) & (g > 160) & (b < 90)))
    enough = band.shape[0] * band.shape[1] * 0.01
    if red > enough and red > yellow * 1.5:
        return "loss"
    if yellow > enough and yellow > red * 1.5:
        return "win"
    return None


# --- main entry ------------------------------------------------------------
def detect_screen(frame: np.ndarray, lines: list[OcrLine]) -> Detection:
    """Decide which screen `frame` shows. `lines` is the text read from it."""
    height, width = frame.shape[:2]
    det = Detection(lines=lines, wave=_wave(lines))
    det.placing = sum(bool(_find(lines, k, 0.7)) for k in ("place", "rotate", "cancel")) >= 2
    det.no_money = _any(lines, "not enough money", threshold=0.6)

    # The end screen needs "Total Time" plus "Waves Completed" or "Next".
    # "Waves Completed" alone isn't enough: the "Wave Completed!" banner after
    # every wave reads almost the same.
    anchor = _find(lines, "total time", 0.85)
    if anchor and not (_find(lines, "waves completed") or _any(lines, "next", threshold=0.75)):
        anchor = None
    if anchor:
        det.screen = "end"
        det.result = _title_color(frame, anchor)
        if det.result is None:
            if _any(lines, "victory", threshold=0.7):
                det.result = "win"
            elif _any(lines, "defeat", threshold=0.6):
                det.result = "loss"
    elif _any(lines, "return to lobby", "waiting for players"):
        det.screen = "after_end"
    elif _any(lines, "travelling to", "traveling to"):
        det.screen = "loading"
    elif _any(lines, "enter this text"):
        det.screen = "captcha"
    elif _any(lines, "join matchmaking", "find match"):
        det.screen = "join_matchmaking"
    elif _any(lines, "matchmaking started", "teleporting", "match found"):
        det.screen = "match_found"
    elif _any(lines, "vote start", "starts in"):
        det.screen = "vote_start"
    elif _any(lines, "choose a card", "vote ends in"):
        det.screen = "card_pick"
    elif sum(fuzzy_in("first", l.text) for l in lines) >= 2 and _any(lines, "max", "upg"):
        det.screen = "unit_manager"
    elif det.wave is not None or det.placing or det.no_money \
            or _any(lines, "enemies remaining", "level info"):
        det.screen = "in_match"
    elif sum(any(_norm(l.text) == w for l in lines) for w in LOBBY_WORDS) >= 3:
        det.screen = "lobby"

    if det.screen in ("in_match", "card_pick", "unit_manager", "end", "after_end"):
        det.map_name = _map_name(lines, width, height)
    if det.screen == "in_match":
        det.yen = _yen(lines, width, height)
    # The damage leaderboard ("People … Total Damage") sometimes opens at the
    # start of a match. Its × sits up and to the left of the "Total Damage"
    # header (measured: 2.36 header-widths left, 1.7 line-heights up).
    # (Exact letters: "Attack Damage: +37%" in the level modifiers is close otherwise.)
    header = next((l for l in lines if "totaldam" in _norm(l.text)), None)
    if header is not None and det.screen in ("in_match", "unit_manager", "vote_start", "unknown"):
        det.leaderboard_close = (header.x - 2.36 * header.w,
                                 header.y + header.h / 2 - 1.7 * header.h)
    det.drop = _drop(lines)
    return det


RARITIES = ("common", "uncommon", "rare", "epic", "legendary", "mythic", "secret", "exclusive")


def _drop(lines: list[OcrLine]) -> tuple[str, str] | None:
    """The item-drop popup: name, rarity, then "(Click anywhere to continue)"."""
    prompt = next((l for l in lines if fuzzy_in("click anywhere to continue", l.text, 0.75)), None)
    if prompt is None:
        return None
    above = sorted((l for l in lines if l.y < prompt.y and prompt.y - l.y < 12 * prompt.h
                    and abs(l.center_x - prompt.center_x) < prompt.w), key=lambda l: -l.y)

    def rarity_of(line: OcrLine) -> str:
        # Other text can run into it ("Legendary G" with a player name behind).
        return next((w.capitalize() for w in re.findall(r"[a-z]+", line.text.lower())
                     if w in RARITIES), "")
    rarity_line = next((l for l in above if rarity_of(l)), None)
    rarity = rarity_of(rarity_line) if rarity_line else ""
    name = ""
    if rarity_line is not None:
        name_line = next((l for l in above if l.y < rarity_line.y - 0.5 * rarity_line.h), None)
        name = name_line.text.strip() if name_line else ""
    return name, rarity
