"""A faster fuzzy_in with exactly the same answers.

screens.fuzzy_in compares the keyword with every window of the text using
difflib, and the screen reading calls it thousands of times per read (each
keyword against each line): that was half the cost of reading the screen.

Two shortcuts that can't change an answer:
- a window whose upper bound (difflib's quick ratios: letters in common,
  ignoring order) is below the threshold can't reach it, so it's skipped;
- answers are remembered: the same keyword meets the same text read after
  read.

install() puts it in place of screens.fuzzy_in, also in the modules that
imported the name. screens.py itself isn't changed.
"""
from __future__ import annotations

import sys
from difflib import SequenceMatcher
from functools import lru_cache

from . import screens as _screens

_norm = _screens._norm
_original = _screens.fuzzy_in


@lru_cache(maxsize=16384)   # a few MB at most
def _fuzzy(keyword: str, text: str, threshold: float) -> bool:
    key, hay = _norm(keyword), _norm(text)
    if not key or not hay:
        return False
    if key in hay:
        return True
    n = len(key)
    matcher = SequenceMatcher(None)
    matcher.set_seq1(key)           # same sides as the original: a = keyword, b = window
    for size in (n - 1, n, n + 1):
        if size <= 0:
            continue
        # Even a perfect match of this length can't reach the threshold.
        if 2.0 * min(size, n) / (size + n) < threshold:
            continue
        for start in range(0, max(1, len(hay) - size + 1)):
            matcher.set_seq2(hay[start:start + size])
            if matcher.real_quick_ratio() < threshold or matcher.quick_ratio() < threshold:
                continue
            if matcher.ratio() >= threshold:
                return True
    return False


def fuzzy_in(keyword: str, text: str, threshold: float = 0.8) -> bool:
    """True if `keyword` appears in `text`, allowing a few wrong letters."""
    return _fuzzy(keyword, text, threshold)


fuzzy_in.__doc__ = _original.__doc__
fuzzy_in._fast = True


def install() -> None:
    """Use the fast one everywhere screens.fuzzy_in was imported."""
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "__name__", "").startswith("maacro") \
                and getattr(module, "fuzzy_in", None) is _original:
            module.fuzzy_in = fuzzy_in


install()
