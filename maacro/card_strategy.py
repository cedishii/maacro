"""How Summer Event picks cards: "Easy" or "Hard" (Configs page).

Easy (the default): Star Golem card first; then a red card that adds Secret
drop chance ("+50% Secret Drop Rate"; the mildest if there are several); then
green, then blue/other; all red: the mildest one (cards.choose_card's rules).

Hard: red cards as much as possible: Secret drop ones first — the highest
Secret chance first ("+100%" over "+50%" over "+25%", whatever it pays in
pearls) — then the biggest SummerPearls bonus, then the mildest danger among
equals (so +100% Enemy
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


# The number right before "Secret": "+50% Secret Drop Rate", "•SO% Secret Dr.
# Rate" (S/O read for 5/0), "+15% Secret Portal Chance".
SECRET_RE = re.compile(r"([0-9OoSsIl|]{1,3})\s*[%°]\s*[^A-Za-z0-9]{0,3}\s*secret", re.IGNORECASE)
_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "S": "5", "s": "5", "I": "1", "l": "1", "|": "1"})


def secret_amount(card) -> int | None:
    """How much Secret chance the card adds, in % (None = not read)."""
    found = None
    for match in SECRET_RE.finditer(card.text):
        digits = match.group(1).translate(_DIGIT_FIX)
        if digits.isdigit() and 1 <= int(digits) <= 500:
            found = max(found or 0, int(digits))
    return found


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
        # Highest Secret chance (an unread one counts as the lowest); then the
        # biggest SummerPearls bonus; among equals the mildest danger.
        best = min(pool, key=lambda c: (-(secret_amount(c) or 0) if secret else 0, -(c.pearls or 0),
                                        c.debuff_rank,
                                        c.debuff_amount if c.debuff_amount is not None else 999, c.index))
        pearls = f"+{best.pearls}% pearls" if best.pearls is not None else "pearls unread"
        if secret:
            amount = secret_amount(best)
            why = f"red with +{amount}% Secret" if amount else "red with + Secret (amount unread)"
            others = sorted({secret_amount(c) for c in secret if c is not best and secret_amount(c)},
                            reverse=True)
            if others:
                why += f" (others: {', '.join(f'+{n}%' for n in others)})"
        else:
            why = "red"
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
