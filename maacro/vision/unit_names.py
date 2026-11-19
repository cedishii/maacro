"""Unit names from the hotbar: each card has its unit's name under it
("Elyssia (Abyssal)", "C.E.O.", "Bulby"), so the names the unit manager
matching needs (placement.button_unit) can be read instead of typed.

Each slot's strip is read on its own (reading the whole bar runs neighbouring
names together), the name is cleaned to its base ("Elyssia (Abyssal)" →
"Elyssia": the unit manager is matched loosely, and a shorter name survives
misreads better), and several pictures vote.
"""
from __future__ import annotations

import re
from collections import Counter

import cv2
import numpy as np

from .hotbar import CARD_SPACING

NAME_TOP, NAME_BOTTOM = 0.927, 0.965    # × height: the name line under the cards
HALF_WIDTH = 0.029                      # × width, around the card's centre
SLOTS = ("1", "2", "3", "4", "5", "6")


def slot_box(slot: int, width: int, height: int) -> tuple[int, int, int, int]:
    centre = width * (0.5 + (slot - 3.5) * CARD_SPACING)
    return (int(centre - HALF_WIDTH * width), int(NAME_TOP * height),
            int(centre + HALF_WIDTH * width), int(NAME_BOTTOM * height))


def clean_name(text: str) -> str:
    """"Elyssia (Abyssal)" → "Elyssia"; "2000 Y" / "Lv.100" → ""."""
    text = re.sub(r"\(.*?(\)|$)", " ", text or "")              # the variant in brackets
    words = []
    for word in text.split():
        if re.search(r"\d|¥", word):
            continue                                            # prices, levels
        word = re.sub(r"[^A-Za-z.'\-]", "", word).strip("'-") or ""
        word = re.sub(r"^Y(?=[A-Z]\.)", "", word)      # the price's "¥" read onto "C.E.O."
        if not re.fullmatch(r"(?:[A-Za-z]\.)+[A-Za-z]?\.?", word):
            word = word.strip(".")
        if word and word.lower() not in ("lv", "y"):
            words.append(word)
    # The first word is enough when it's a real word (the second is the one
    # most often misread: "Armored Crusader" → "Armor eusader").
    name = words[0] if words and sum(c.isalpha() for c in words[0]) >= 4 else " ".join(words[:2])
    if name and re.fullmatch(r"(?:[A-Z]\.)+[A-Z]?", name.replace(" ", "")):
        name = name.replace(" ", "") + ("" if name.endswith(".") else ".")   # "C.E.O"
    return name if sum(c.isalpha() for c in name) >= 3 or re.fullmatch(r"(?:[A-Z]\.){2,}", name) else ""


def read_slot_names(frame: np.ndarray, ocr) -> dict[str, str]:
    """{slot key: name} for the slots whose name could be read in this picture."""
    height, width = frame.shape[:2]
    names = {}
    for index, key in enumerate(SLOTS, start=1):
        x0, y0, x1, y1 = slot_box(index, width, height)
        crop = frame[max(0, y0):y1, max(0, x0):x1, :3]
        if crop.size == 0:
            continue
        big = cv2.resize(np.ascontiguousarray(crop), None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        big = cv2.copyMakeBorder(big, 16, 16, 16, 16, cv2.BORDER_REPLICATE)
        text = " ".join(line.text for line in ocr.read(big))
        name = clean_name(text)
        if name:
            names[key] = name
    return names


def vote(readings: list[dict[str, str]]) -> dict[str, str]:
    """The most common name per slot over several pictures (ties: the first
    read). A slot read in fewer than half the pictures is left out."""
    out = {}
    for key in SLOTS:
        seen = [r[key] for r in readings if key in r]
        if not seen or len(seen) * 2 < len(readings):
            continue
        counts = Counter(name.lower() for name in seen)
        best = max(counts, key=lambda n: (counts[n], -[s.lower() for s in seen].index(n)))
        out[key] = next(s for s in seen if s.lower() == best)
    return out
