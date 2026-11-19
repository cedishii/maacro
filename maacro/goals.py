"""Session goals: stop the macro by itself after N runs, after so long, or
after too many losses in a row (Settings → Session goals)."""
from __future__ import annotations


def goal_reached(settings, runs: int, seconds: int, losses_in_row: int) -> str:
    """Why the session should end now ("" = keep going). `settings` is an
    AppSettings (only the stop_after_* fields are read)."""
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
    return " · ".join(parts) or "None"


def _duration(seconds: int) -> str:
    h, m = divmod(int(seconds) // 60, 60)
    if h and m:
        return f"{h} h {m} min"
    return f"{h} h" if h else f"{m} min"
