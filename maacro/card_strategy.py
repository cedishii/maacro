"""How Summer Event picks cards: "Easy" or "Hard" (Configs page).

Easy (the default): Star Golem card first; then a red card that adds Secret
drop chance ("+50% Secret Drop Rate"; the mildest if there are several); then
green, then blue/other; all red: the mildest one (cards.choose_card's rules).

Hard: red cards as much as possible: Secret drop ones first, then the biggest
SummerPearls bonus, then the mildest danger among equals (so +100% Enemy
Speed isn't taken when +10 Enemy Shield pays the same); enemy-regen cards
still last. Then the Star Golem card, then green, then blue/other.

vision/cards.py and macro.py aren't changed: macro.py's choose_card lookup is
wrapped here and only changes while a CardStrategy thread picks a card.
"""
from __future__ import annotations

import re
import threading

from . import macro as _macro
from .vision import cards as _cards
from .vision.cards import _mildness, _without_regen

EASY, HARD = "easy", "hard"
STRATEGIES = {EASY: "Easy", HARD: "Hard"}
SECRET = HARD           # the first name of Hard ("secret" in a saved config still means Hard)

_local = threading.local()
_original = _cards.choose_card


def secret_portal(card) -> bool:
    """The card adds Secret drop chance ("+50% Secret Drop Rate"; "Secret
    Portal" in some events). "secret" is enough (it's never on other cards)."""
    text = re.sub(r"[^a-z]", "", card.text.lower())
    return "secret" in text or "secretdrop" in text or "dropratesecret" in text


def choose_easy(cards):
    if not cards:
        return None
    golem = next((c for c in cards if c.star_golem), None)
    if golem is not None:
        return golem, "Star Golem card"
    secret = [c for c in cards if c.color == "red" and secret_portal(c) and not c.regen]
    if secret:
        best = min(secret, key=lambda c: (*_mildness(c), c.index))
        return best, f"red, but + Secret drop chance (mildest: {_name(best)})"
    return _original(cards)


def _name(card) -> str:
    """The card's title for the log: its text up to the first number
    ("+ Enemy Shield III +150% SummerPearls …" → "Enemy Shield III")."""
    return re.split(r"\s\+?\d", card.text, maxsplit=1)[0].strip(" •-+") or f"card {card.index + 1}"


def choose_hard(cards):
    if not cards:
        return None
    red = _without_regen([c for c in cards if c.color == "red"])
    if red:
        secret = [c for c in red if secret_portal(c)]
        pool = secret or red
        # Biggest SummerPearls bonus; among equals the mildest danger.
        best = min(pool, key=lambda c: (-(c.pearls or 0), c.debuff_rank,
                                        c.debuff_amount if c.debuff_amount is not None else 999, c.index))
        pearls = f"+{best.pearls}% pearls" if best.pearls is not None else "pearls unread"
        why = "red with + Secret drop chance" if secret else "red"
        return best, f"Hard: {why}, {pearls} ({_name(best)})"
    return _original(cards)


def _choose(cards):
    strategy = getattr(_local, "strategy", None)
    if strategy in (HARD, "secret"):
        return choose_hard(cards)
    if strategy == EASY:
        return choose_easy(cards)
    return _original(cards)


_choose._card_strategy = True
if not getattr(_macro.choose_card, "_card_strategy", False):
    _macro.choose_card = _choose


choose_secret = choose_hard     # its first name


class CardStrategy:
    """Mixin: card picks follow settings.card_strategy."""

    def _on_card_pick(self, hwnd: int) -> None:
        _local.strategy = getattr(self.settings, "card_strategy", EASY)
        try:
            super()._on_card_pick(hwnd)
        finally:
            _local.strategy = None
