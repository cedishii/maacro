"""Session goals: stop the macro by itself after N runs, after so long, at a
clock time, or after too many losses in a row (Settings → Session goals)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta


def parse_time(text: str) -> tuple[int, int] | None:
    """"07:00" / "7:30" → (7, 0) / (7, 30); anything else → None."""
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", text or "")
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    return (hour, minute) if hour < 24 and minute < 60 else None


def stop_time(text: str, started: datetime) -> datetime | None:
    """The first time it's `text` o'clock after `started` (23:00 start, "07:00"
    → 07:00 the next morning)."""
    hm = parse_time(text)
    if hm is None:
        return None
    target = started.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    return target if target > started else target + timedelta(days=1)


def goal_reached(settings, runs: int, seconds: int, losses_in_row: int,
                 now: datetime | None = None, started: datetime | None = None) -> str:
    """Why the session should end now ("" = keep going). `settings` is an
    AppSettings (the stop_after_* fields and stop_at); `started` is when Start
    was pressed (for stop_at)."""
    at = stop_time(getattr(settings, "stop_at", ""), started) if started else None
    if at is not None and (now or datetime.now()) >= at:
        return f"it's {at:%H:%M} (stop time)"
    if settings.stop_after_runs and runs >= settings.stop_after_runs:
        return f"{runs} runs done (goal: {settings.stop_after_runs})"
    if settings.stop_after_minutes and seconds >= settings.stop_after_minutes * 60:
        return f"ran for {_duration(seconds)} (goal: {_duration(settings.stop_after_minutes * 60)})"
    if settings.stop_after_losses_in_row and losses_in_row >= settings.stop_after_losses_in_row:
        return f"{losses_in_row} losses in a row (limit: {settings.stop_after_losses_in_row})"
    return ""


def goal_text(settings, runs: int) -> str:
    """Short progress text for the Main page, e.g. "12 / 50 runs · 2 h"."""
    parts = []
    if settings.stop_after_runs:
        parts.append(f"{runs} / {settings.stop_after_runs} runs")
    if settings.stop_after_minutes:
        parts.append(f"stop after {_duration(settings.stop_after_minutes * 60)}")
    if settings.stop_after_losses_in_row:
        parts.append(f"{settings.stop_after_losses_in_row} losses in a row")
    hm = parse_time(getattr(settings, "stop_at", ""))
    if hm:
        parts.append(f"until {hm[0]:02d}:{hm[1]:02d}")
    return " · ".join(parts) or "None"


def _duration(seconds: int) -> str:
    h, m = divmod(int(seconds) // 60, 60)
    if h and m:
        return f"{h} h {m} min"
    return f"{h} h" if h else f"{m} min"
