"""How Summer Event picks cards: "Easy" or "Secret Chances" (Configs page).

Easy (the default): Star Golem card first; then any red card that adds Secret
Portal drop chance; then green, then blue/other; all red: the mildest one
(cards.choose_card's rules).

Secret Chances: red cards as much as possible: Secret Portal ones first, then
the strongest red (biggest SummerPearls bonus); enemy-regen cards still last.
Then the Star Golem card, then green, then blue/other.

vision/cards.py and macro.py aren't changed: macro.py's choose_card lookup is
wrapped here and only changes while a CardStrategy thread picks a card.
"""
from __future__ import annotations

import re
import threading

from . import macro as _macro
from .vision import cards as _cards

EASY, SECRET = "easy", "secret"
STRATEGIES = {EASY: "Easy", SECRET: "Secret Chances"}

_local = threading.local()
_original = _cards.choose_card


def secret_portal(card) -> bool:
    """The card adds Secret Portal drop chance ("+…% Secret Portal Chance").
    Either word is enough (text recognition sometimes drops one)."""
    text = re.sub(r"[^a-z]", "", card.text.lower())
    return "secret" in text or "portalchance" in text or "secretportal" in text


def choose_easy(cards):
    if not cards:
        return None
    golem = next((c for c in cards if c.star_golem), None)
    if golem is not None:
        return golem, "Star Golem card"
    secret = [c for c in cards if c.color == "red" and secret_portal(c) and not c.regen]
    if secret:
        return secret[0], "red, but + Secret Portal chance"
    return _original(cards)


def choose_secret(cards):
    if not cards:
        return None
    red = [c for c in cards if c.color == "red"]
    usable = [c for c in red if not c.regen] or red
    if usable:
        secret = [c for c in usable if secret_portal(c)]
        if secret:
            return secret[0], "Secret Chances: red with + Secret Portal chance"
        best = max(usable, key=lambda c: (c.pearls or 0, c.debuff_amount or 0, -c.index))
        pearls = f"+{best.pearls}% pearls" if best.pearls is not None else "pearls unread"
        return best, f"Secret Chances: strongest red ({pearls})"
    return _original(cards)


def _choose(cards):
    strategy = getattr(_local, "strategy", None)
    if strategy == SECRET:
        return choose_secret(cards)
    if strategy == EASY:
        return choose_easy(cards)
    return _original(cards)


_choose._card_strategy = True
if not getattr(_macro.choose_card, "_card_strategy", False):
    _macro.choose_card = _choose


class CardStrategy:
    """Mixin: card picks follow settings.card_strategy."""

    def _on_card_pick(self, hwnd: int) -> None:
        _local.strategy = getattr(self.settings, "card_strategy", EASY)
        try:
            super()._on_card_pick(hwnd)
        finally:
            _local.strategy = None
