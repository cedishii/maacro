"""The 'Choose a card...' screen: where the three cards are, their colours,
their vote counts, and which one to pick.

Rule (see FLOW.md):
0. A "Star Golem +100%" card (Starfall weather) → always pick it.
1. Any non-red card (green = buff) → pick it, green first.
2. All red → the card with the most votes; tie → the first of the highest.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from .numbers import Box, NumberReader
from .ocr import OcrLine
from .screens import _norm, fuzzy_in

# Positions as fractions of D = distance from the title to the "Vote ends in" line.
CARD_SPACING = 0.578
CARD_HALF_WIDTH = 0.20      # inner part of the card used for the colour sample
COLOR_TOP, COLOR_BOTTOM = 0.30, 0.70
VOTE_TOP, VOTE_BOTTOM = 0.80, 0.95
VOTE_HALF_WIDTH = 0.07


@dataclass
class Card:
    index: int
    center: tuple[float, float]     # where to click
    color: str                      # "red", "green" or "other" (blue etc.)
    vote_box: Box
    votes: int | None = None
    text_box: Box = (0, 0, 0, 0)    # where the card's own text is
    text: str = ""                  # e.g. "Enemy Health I +30% SummerPearls +50% Enemy Health"
    pearls: int | None = None       # the "+30% SummerPearls" bonus

    @property
    def star_golem(self) -> bool:
        """The Starfall card with "Star Golem +100%" chance. "golem" alone
        counts too, in case OCR garbles "Star"."""
        return "golem" in re.sub(r"[^a-z]", "", self.text.lower())

    @property
    def debuff_rank(self) -> int:
        """Lower = milder debuff, per the player: Enemy Health, then Physical
        Resist only, then anything else (magic resist, both resists, regen…)."""
        text = self.text.lower()
        if "health" in text:
            return 0
        if "physical" in text and "magic" not in text:
            return 1
        return 2


def _find(lines: list[OcrLine], keyword: str) -> OcrLine | None:
    for line in lines:
        if fuzzy_in(keyword, line.text):
            return line
    return None


def classify_color(bgr: np.ndarray) -> str:
    """Red (debuff), green (buff) or other, from the average colour of a card."""
    b, g, r = (float(v) for v in bgr.reshape(-1, bgr.shape[-1])[:, :3].mean(axis=0))
    if r > g * 1.4 and r > b * 1.2:
        return "red"
    if g > r * 1.3 and g >= b * 0.9:
        return "green"
    return "other"


# The span is also about this many times the width of the "Choose a card..." title,
# which helps when "Vote ends in" is hidden (e.g. under a player's name).
SPAN_PER_TITLE_WIDTH = 2.34


# Where the cards sit on a full live frame (1920×991 capture): the title's
# top at 23.3% of the height, centred, span 52.4% of the height. Used when
# the title can't be read (something drawn over it, e.g. a boss health bar).
TITLE_Y_PER_HEIGHT = 0.233
SPAN_PER_HEIGHT = 0.524


def _layout(frame: np.ndarray, lines: list[OcrLine]) -> tuple[float, float, float]:
    """(centre x, title top y, span) of the card pick."""
    height, width = frame.shape[:2]
    title = _find(lines, "choose a card")
    bottom = _find(lines, "vote ends in")
    if title is not None and title.w >= 20:
        span = SPAN_PER_TITLE_WIDTH * title.w
        if bottom is not None and 0.85 * span < bottom.y - title.y < 1.15 * span:
            span = bottom.y - title.y
        return title.center_x, title.y, span
    span = SPAN_PER_HEIGHT * height
    if bottom is not None:
        # "Vote ends in: …" is centred under the cards, one span below the title.
        return bottom.center_x, bottom.y - span, span
    return width / 2, TITLE_Y_PER_HEIGHT * height, span


def find_cards(frame: np.ndarray, lines: list[OcrLine]) -> list[Card]:
    """The three cards, left to right. Falls back on the "Vote ends in" line,
    then on the usual spot on screen, when the title can't be read."""
    cx, title_y, span = _layout(frame, lines)
    cards = []
    for index, offset in enumerate((-1, 0, 1)):
        x = cx + offset * CARD_SPACING * span
        top = int(title_y + COLOR_TOP * span)
        bot = int(title_y + COLOR_BOTTOM * span)
        left = int(x - CARD_HALF_WIDTH * span)
        right = int(x + CARD_HALF_WIDTH * span)
        sample = frame[max(0, top):bot, max(0, left):right]
        color = classify_color(sample) if sample.size else "red"
        vote_box = (int(x - VOTE_HALF_WIDTH * span), int(title_y + VOTE_TOP * span),
                    int(x + VOTE_HALF_WIDTH * span), int(title_y + VOTE_BOTTOM * span))
        text_box = (int(x - 0.26 * span), int(title_y + 0.08 * span),
                    int(x + 0.26 * span), int(title_y + 0.75 * span))
        cards.append(Card(index, (x, title_y + 0.45 * span), color, vote_box, text_box=text_box))
    return cards


PEARLS_RE = re.compile(r"(\d{1,3})\s*%\s*summ", re.IGNORECASE)


def read_card_texts(cards: list[Card], lines: list[OcrLine]) -> None:
    """Give each card the text written on it, and its SummerPearls bonus."""
    for card in cards:
        left, top, right, bottom = card.text_box
        own = [l for l in lines if left <= l.center_x <= right and top <= l.y + l.h / 2 <= bottom]
        own.sort(key=lambda l: l.y)
        card.text = " ".join(l.text for l in own)
        match = PEARLS_RE.search(card.text)
        card.pearls = int(match.group(1)) if match else None


def read_votes(frame: np.ndarray, cards: list[Card], reader: NumberReader) -> None:
    for card in cards:
        text = reader.read(frame, card.vote_box)
        card.votes = int(text) if text and text.isdigit() and len(text) <= 2 else None


def needs_votes(cards: list[Card]) -> bool:
    """Vote counts only matter when every card is red and the best ones tie on
    pearls and debuff (call read_card_texts first). Skipping them saves time."""
    if not cards or any(c.color != "red" for c in cards):
        return False
    keys = sorted((c.pearls if c.pearls is not None else 999, c.debuff_rank) for c in cards)
    return len(keys) > 1 and keys[0] == keys[1]


def choose_card(cards: list[Card]) -> tuple[Card, str] | None:
    """The card to vote for and a short reason, or None if there are no cards."""
    if not cards:
        return None
    # 0. Starfall's Star Golem card beats everything.
    golem = next((c for c in cards if c.star_golem), None)
    if golem is not None:
        return golem, "Star Golem card"
    # 1. Buffs: green first, then blue / any other non-red colour.
    for wanted, label in (("green", "green card"), ("other", "blue/other card")):
        special = [c for c in cards if c.color == wanted]
        if special:
            return special[0], label
    # 2. All red: the smallest SummerPearls bonus (bigger bonus = bigger debuff),
    #    then the mildest debuff (Enemy Health, then Physical Resist), then the
    #    most votes, then the leftmost.
    if any(c.pearls is not None or c.text for c in cards):
        def rank(c: Card):
            return (c.pearls if c.pearls is not None else 999, c.debuff_rank,
                    -(c.votes or 0), c.index)
        best = min(cards, key=rank)
        name = best.text.split("+")[0].strip(" •-") or f"card {best.index + 1}"
        pearls = f"+{best.pearls}% pearls" if best.pearls is not None else "pearls unread"
        return best, f"all red, mildest: {name} ({pearls})"
    known = [c for c in cards if c.votes is not None]
    if known:
        best = max(known, key=lambda c: c.votes)     # max keeps the first on a tie
        return best, f"all red, most votes ({best.votes})"
    middle = cards[len(cards) // 2]
    return middle, "all red, unreadable → middle"


# The Vote button sits at a fixed spot relative to the title (measured on two
# screenshots of different sizes): left of centre, below the cards.
VOTE_DX, VOTE_DY = -0.20, 1.125     # × span


def predicted_vote_button(lines: list[OcrLine], frame: np.ndarray) -> tuple[float, float]:
    """Where Vote will be, from the card layout (it may not be drawn yet)."""
    cx, title_y, span = _layout(frame, lines)
    return cx + VOTE_DX * span, title_y + VOTE_DY * span


def vote_button(lines: list[OcrLine], title: OcrLine | None = None) -> tuple[float, float] | None:
    """Where the Vote button is. It's often not read, but it sits mirror-opposite Cancel."""
    for line in lines:
        if _norm(line.text) == "vote":
            return line.center_x, line.y + line.h / 2
    title = title or _find(lines, "choose a card")
    cancel = next((l for l in lines if _norm(l.text) == "cancel"), None)
    if title is None or cancel is None:
        return None
    return 2 * title.center_x - cancel.center_x, cancel.y + cancel.h / 2
