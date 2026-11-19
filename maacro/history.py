"""All-time results from runs/runs.csv: totals, win rate, streaks, per map,
per stage kind, per day.

The map names in the CSV are read off the screen, so they're often a little
wrong ("Shibuya DistVi Act 6", "Rain MILage Infinity Mansion"). `split_map`
matches them to the known Anime Adventures maps and splits off the stage kind
(Summer Hunt, Infinity Mansion, Portal, Act…), so the same map is counted
once however it was misread.
"""
from __future__ import annotations

import csv
import difflib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

RUNS_CSV = Path(__file__).resolve().parents[1] / "runs" / "runs.csv"

# Anime Adventures maps (story, event, raid and portal maps seen so far).
KNOWN_MAPS = (
    "Adventure Town", "Alien Spaceship", "Ant Kingdom", "Assassin Park", "Cursed Festival",
    "Cursed Womb", "Dungeon Throne", "Fabled Kingdom", "Fiend City", "Future City",
    "Haunted Academy", "Haunted Mansion", "Hellish City", "Magic Hills", "Magic Town",
    "Mountain Temple", "Navy Bay", "Nightmare Train", "Puppet Island", "Rain Village",
    "Ruined City", "Sacred Planet", "Shibuya District", "Sky Aircraft", "Sky Island",
    "Sky Portal", "Snowy Town", "Space Center", "Spirit Town", "Spirit World", "Storm Hideout",
    "Strange Town", "Virtual Dungeon", "Walled City",
)

# Stage kinds, by words in the name (checked fuzzily, in this order).
KINDS = (
    ("Infinity Mansion", ("infinit", "mansion", "room")),
    ("Summer Hunt", ("summer", "hunt")),
    ("Portal", ("portal", "tier")),
    ("Underwater", ("underwater",)),
    ("Act", ("act",)),
)

_letters = re.compile(r"[^a-z]")


def _squash(text: str) -> str:
    return _letters.sub("", text.lower())


def split_map(raw: str) -> tuple[str, str]:
    """("Shibuya District", "Act") from "Shibuya DistVi Act 6". An unknown
    name comes back cleaned up, with kind "" if none is recognised."""
    text = (raw or "").strip(" -'\"")
    if not text:
        return "", ""
    squashed = _squash(text)
    kind = ""
    for name, words in KINDS:
        if any(w in squashed for w in words) or _fuzzy_word(text, words):
            kind = name
            break
    # "Sky Portal" is a map, not a portal stage.
    if kind == "Portal" and "skyportal" in squashed and "tier" not in squashed:
        kind = ""
    best, best_score = "", 0.0
    for known in KNOWN_MAPS:
        k = _squash(known)
        # Compare with the start of the name, about as long as the map name.
        # (skipping up to 2 stray letters read in front of it).
        score = max(difflib.SequenceMatcher(None, k, squashed[start:start + len(k) + 1]).ratio()
                    for start in range(3))
        if k in squashed:
            score = 1.0 + len(k) / 100      # exact match wins; longer exact match first
        if score > best_score:
            best, best_score = known, score
    if best_score >= 0.7:
        # "Haunted Mansion" is a map, not an Infinity Mansion room.
        if (best == "Haunted Mansion" and kind == "Infinity Mansion"
                and not any(w in squashed for w in ("infinit", "room"))):
            kind = ""
        return best, kind
    # Unknown: keep the words before the stage kind / numbers.
    cleaned = re.split(r"\b(?:act|room|tier|summer|infinity|portal)\b|\d", text, maxsplit=1,
                       flags=re.IGNORECASE)[0].strip(" -'")
    return (cleaned or text), kind


def _fuzzy_word(text: str, words: tuple[str, ...]) -> bool:
    for token in re.findall(r"[A-Za-z]{4,}", text.lower()):
        if difflib.get_close_matches(token, words, n=1, cutoff=0.8):
            return True
    return False


def _seconds(duration: str) -> int | None:
    """"25:47" → 1547, "1:02:03" → 3723."""
    parts = (duration or "").split(":")
    if not all(p.isdigit() for p in parts) or len(parts) not in (2, 3):
        return None
    total = 0
    for p in parts:
        total = total * 60 + int(p)
    return total


@dataclass
class Run:
    time: datetime
    result: str
    map: str
    kind: str
    mode: str = ""
    waves: int | None = None
    seconds: int | None = None
    pearls: int | None = None
    raw_map: str = ""
    cards: str = ""             # card style ("easy", "hard", "smart-easy"…); "" if not recorded


def load_runs(path: Path = RUNS_CSV) -> list[Run]:
    runs: list[Run] = []
    try:
        with open(path, newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                try:
                    when = datetime.strptime(row.get("time", ""), "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                result = (row.get("result") or "").strip().lower()
                if result not in ("win", "loss"):
                    continue
                name, kind = split_map(row.get("map", ""))
                waves = row.get("waves", "")
                pearls = row.get("pearls", "")
                runs.append(Run(when, result, name, kind, (row.get("mode") or "").strip(),
                                int(waves) if waves.isdigit() else None,
                                _seconds(row.get("duration", "")),
                                int(pearls) if pearls.isdigit() else None,
                                row.get("map", ""), (row.get("cards") or "").strip().lower()))
    except OSError:
        pass
    return runs


@dataclass
class Group:
    """Results for one map / kind / day."""
    name: str
    wins: int = 0
    losses: int = 0
    seconds: list[int] = field(default_factory=list)
    pearls: int = 0

    @property
    def runs(self) -> int:
        return self.wins + self.losses

    @property
    def win_rate(self) -> float:
        return self.wins / self.runs * 100 if self.runs else 0.0

    @property
    def pearls_per_run(self) -> float:
        """Pearls per run, losses (no pearls) included."""
        return self.pearls / self.runs if self.runs else 0.0

    @property
    def pearls_per_hour(self) -> float:
        played = sum(self.seconds)
        return self.pearls / (played / 3600) if played else 0.0

    @property
    def avg_seconds(self) -> int | None:
        return sum(self.seconds) // len(self.seconds) if self.seconds else None

    def add(self, run: Run) -> None:
        if run.result == "win":
            self.wins += 1
        else:
            self.losses += 1
        if run.seconds:
            self.seconds.append(run.seconds)
        if run.pearls:
            self.pearls += run.pearls


@dataclass
class Summary:
    total: Group
    today: Group
    by_map: list[Group]
    by_kind: list[Group]
    by_day: list[Group]         # newest first
    by_cards: list[Group]       # Summer card styles (runs that recorded one)
    best_win_streak: int
    current_streak: int         # +n wins / -n losses in a row, newest runs
    first: datetime | None
    last: datetime | None
    recent: list[Run]           # newest first

    @property
    def runs_per_hour(self) -> float:
        """Runs per hour of play (sum of stage times)."""
        played = sum(self.total.seconds)
        return self.total.runs / (played / 3600) if played else 0.0


def summarize(runs: list[Run], today: date | None = None, recent: int = 50) -> Summary:
    today = today or date.today()
    total, today_group = Group("All time"), Group("Today")
    maps: dict[str, Group] = {}
    kinds: dict[str, Group] = {}
    days: dict[date, Group] = {}
    cards: dict[str, Group] = {}
    best = streak = 0
    current = 0
    for run in sorted(runs, key=lambda r: r.time):
        total.add(run)
        if run.time.date() == today:
            today_group.add(run)
        maps.setdefault(run.map or "Unknown", Group(run.map or "Unknown")).add(run)
        kind = run.kind or "Other"
        kinds.setdefault(kind, Group(kind)).add(run)
        day = run.time.date()
        days.setdefault(day, Group(day.isoformat())).add(run)
        if run.cards:
            label = card_label(run.cards)
            cards.setdefault(label, Group(label)).add(run)
        if run.result == "win":
            streak += 1
            best = max(best, streak)
            current = current + 1 if current > 0 else 1
        else:
            streak = 0
            current = current - 1 if current < 0 else -1
    ordered = sorted(runs, key=lambda r: r.time)
    return Summary(
        total=total, today=today_group,
        by_map=sorted(maps.values(), key=lambda g: (-g.runs, g.name)),
        by_kind=sorted(kinds.values(), key=lambda g: (-g.runs, g.name)),
        by_day=[days[d] for d in sorted(days, reverse=True)],
        by_cards=sorted(cards.values(), key=lambda g: (-g.runs, g.name)),
        best_win_streak=best, current_streak=current,
        first=ordered[0].time if ordered else None,
        last=ordered[-1].time if ordered else None,
        recent=list(reversed(ordered[-recent:])),
    )


def card_label(value: str) -> str:
    """"smart-easy" → "Smart (Easy)", "hard" → "Hard"."""
    if value.startswith("smart-"):
        return f"Smart ({value[6:].title()})"
    return value.title()


def hms(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
