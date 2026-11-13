"""Recording each finished run: result, map, waves, time, SummerPearls earned.

Each run is added to runs/runs.csv and the end screen is saved next to it
(runs/<time>_<result>.png), so drops can be checked and, once there are
examples, recognised automatically.
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .vision.ocr import OcrLine, OcrReader

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"
CSV_FIELDS = ["time", "result", "map", "waves", "duration", "pearls", "drops", "screenshot"]


@dataclass
class RunRecord:
    result: str                 # "win" / "loss"
    map_name: str = ""
    waves: int | None = None
    duration: str = ""          # "30:33"
    pearls: int | None = None   # SummerPearls earned
    drops: str = ""             # filled in once drops can be recognised
    screenshot: str = ""


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text.replace("O", "0").replace("o", "0"))


def _read_crop(image: np.ndarray, box, ocr: OcrReader) -> str | None:
    left, top, right, bottom = (int(v) for v in box)
    crop = image[max(0, top):bottom, max(0, left):right]
    if crop.size == 0 or crop.shape[1] < 4:
        return None
    big = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    big = cv2.copyMakeBorder(big, 20, 20, 20, 20, cv2.BORDER_REPLICATE)
    found = re.search(r"\d{2,}", " ".join(l.text for l in ocr.read(big)).replace("O", "0"))
    return found.group(0) if found else None


def read_pearls(frame: np.ndarray, lines: list[OcrLine], ocr: OcrReader) -> int | None:
    """SummerPearls earned, from the end screen ("+55 XP   +4391 [pearl]").

    The pearl icon right after the number is often read as an extra "0" or
    "@", so it's read three ways and the answer two of them agree on wins:
    A) the number with the icon cut off, B) the whole word re-read enlarged,
    C) the word as first read (dropping a merged icon), D) the "+4391" counter
    at the top left.
    """
    image = frame[..., :3]
    height, width = image.shape[:2]
    xp = next((l for l in lines if re.search(r"\bxp\b", l.text.lower()) and "+" in l.text
               and "progress" not in l.text.lower()), None)
    candidates: dict[str, str | None] = {"A": None, "B": None, "C": None, "D": None}
    if xp is not None:
        row = [l for l in lines if abs((l.y + l.h / 2) - (xp.y + xp.h / 2)) < xp.h * 1.2]
        # The pearls are "+NNNN"; other numbers on the row (XP Progress panel) aren't.
        words = [w for l in row for w in (l.words or ()) if w.x > xp.x + xp.w * 0.3
                 and w.text.strip().startswith("+") and "xp" not in w.text.lower()
                 and len(_digits(w.text)) >= 2]
        if words:
            word = max(words, key=lambda w: len(_digits(w.text)))
            pad = 6
            candidates["A"] = _read_crop(image, (word.x - pad, word.y - pad,
                                                 word.x + word.w - 0.9 * word.h, word.y + word.h + pad), ocr)
            candidates["B"] = _read_crop(image, (word.x - pad, word.y - pad,
                                                 word.x + word.w + pad, word.y + word.h + pad), ocr)
            raw = _digits(word.text)
            # Icon read as a separate token ("+6111 •") → the digits are right;
            # icon merged into the word ("+113540") → drop its last character.
            merged = word.text.rstrip()[-1:] not in "0123456789" or len(raw) >= 5
            following = [w for l in row for w in (l.words or ()) if w.x > word.x + word.w]
            if following and not _digits(following[0].text):
                merged = False
            candidates["C"] = raw[:-1] if merged and len(raw) > 1 else raw
    top = next((l for l in lines if l.text.strip().startswith("+") and l.y < 0.2 * height
                and l.x < 0.45 * width and len(_digits(l.text)) >= 3), None)
    if top is not None:
        raw = _digits(top.text)
        candidates["D"] = raw[:-1] if len(raw) > 1 else raw

    values = [v for v in candidates.values() if v]
    if not values:
        return None
    value, votes = Counter(values).most_common(1)[0]
    if votes < 2:
        value = next(candidates[k] for k in ("A", "B", "D", "C") if candidates[k])
    return int(value)


def read_run(frame: np.ndarray, lines: list[OcrLine], ocr: OcrReader, result: str,
             map_name: str = "") -> RunRecord:
    record = RunRecord(result=result, map_name=map_name)
    for line in lines:
        text = line.text
        if "wave" in text.lower() and "complet" in text.lower():
            found = re.search(r"(\d+)\s*$", text)
            record.waves = int(found.group(1)) if found else None
        elif "time" in text.lower() and "total" in text.lower():
            found = re.search(r"(\d+:\d{2}(?::\d{2})?)", text)
            record.duration = found.group(1) if found else ""
    try:
        record.pearls = read_pearls(frame, lines, ocr)
    except Exception:
        record.pearls = None
    return record


KEEP_RUN_SHOTS = 100     # end-screen pictures kept (the CSV keeps every run)


def prune_files(folder: Path, pattern: str, keep: int) -> None:
    """Delete all but the newest `keep` files matching `pattern`, so long
    grinds don't slowly fill the disk with screenshots."""
    try:
        files = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime)
        for old in files[:-keep] if keep else files:
            old.unlink(missing_ok=True)
    except OSError:
        pass


def save_run(record: RunRecord, frame: np.ndarray) -> Path:
    """Add the run to runs/runs.csv and save the end screen. Returns the CSV path."""
    RUNS_DIR.mkdir(exist_ok=True)
    now = datetime.now()
    shot = RUNS_DIR / f"{now:%Y%m%d_%H%M%S}_{record.result}.png"
    cv2.imwrite(str(shot), np.ascontiguousarray(frame[..., :3]))
    prune_files(RUNS_DIR, "*_*.png", KEEP_RUN_SHOTS)
    record.screenshot = shot.name
    path = RUNS_DIR / "runs.csv"
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        if new:
            writer.writeheader()
        writer.writerow({"time": f"{now:%Y-%m-%d %H:%M:%S}", "result": record.result,
                         "map": record.map_name, "waves": record.waves or "",
                         "duration": record.duration, "pearls": record.pearls or "",
                         "drops": record.drops, "screenshot": record.screenshot})
    return path
