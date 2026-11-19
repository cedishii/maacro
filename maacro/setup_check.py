"""Setup check: things on the player's side that make MAACRO miss — found
before they cost runs (Main page → Check setup, and on every Start).

Script macros (Capy's and the like) click fixed screen spots, so they come
with a list of required game and display settings. MAACRO finds things on
screen instead, so it needs less, but it still reads text: a small or oddly
shaped window, a missing text-recognition language, or a unit setting that
needs the unit's name (to find its Upg button) all quietly break runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

OK, WARN, ERROR = "ok", "warn", "error"
GOOD_WIDTH = 1600       # px: text reads well from here (made on 1920×991)
MIN_WIDTH, MIN_HEIGHT = 1280, 650


@dataclass
class Facts:
    window_found: bool = False
    minimized: bool = False
    width: int = 0
    height: int = 0
    ocr_error: str = ""
    recent_screens: list[str] = field(default_factory=list)   # last screen reads, oldest first
    mode_key: str = ""
    config: object = None
    rejoin: bool | None = None      # Settings → Rejoin by itself (None = not known)


def check(f: Facts) -> list[tuple[str, str]]:
    """[(level, text)] — every problem found, plus an "ok" line per part that's fine."""
    out: list[tuple[str, str]] = []
    # --- the Roblox window -------------------------------------------------
    if not f.window_found:
        out.append((ERROR, "Roblox isn't open (or its window isn't called 'Roblox')."))
    elif f.minimized:
        out.append((ERROR, "Roblox is minimized — restore it (behind other windows is fine)."))
    elif f.width and f.height:
        size = f"{f.width}×{f.height}"
        ratio = f.width / f.height
        if f.width < MIN_WIDTH or f.height < MIN_HEIGHT:
            out.append((WARN, f"The Roblox window is small ({size}): text is hard to read. Maximize it "
                              "(best: maximized on a 1920×1080 screen)."))
        elif not 1.55 <= ratio <= 2.15:
            out.append((WARN, f"The Roblox window has an unusual shape ({size}). Maximize it so the game "
                              "isn't squeezed."))
        elif f.width < GOOD_WIDTH:
            out.append((WARN, f"The Roblox window is {size}: it works, but maximized on a bigger screen "
                              "reads more reliably."))
        else:
            out.append((OK, f"Roblox window {size}."))
    # --- reading the screen ----------------------------------------------
    if f.ocr_error:
        out.append((ERROR, f"Text recognition isn't working: {f.ocr_error}"))
    reads = [s for s in f.recent_screens if s]
    if f.window_found and not f.minimized and len(reads) >= 10:
        unknown = sum(1 for s in reads if s == "unknown") / len(reads)
        if unknown >= 0.8:
            out.append((WARN, f"{unknown:.0%} of recent screen reads weren't recognised. If you're in the "
                              "lobby or a match, check the Detection page (a window or overlay over "
                              "Roblox, or a very different UI scale, can do this)."))
        else:
            out.append((OK, "Screens are being recognised."))
    if f.rejoin is False:
        out.append((WARN, "Auto-rejoin is off (Settings → Roblox). When Reconnect doesn't work, "
                          "MAACRO then sits on 'Disconnected' until you come back — it once took "
                          "over an hour."))
    # --- the mode's unit setup ---------------------------------------------
    cfg = f.config
    if cfg is not None:
        out.extend(_config_checks(f.mode_key, cfg))
    return out


def _config_checks(mode: str, cfg) -> list[tuple[str, str]]:
    out = []
    order = list(getattr(cfg, "placement_order", []) or [])
    if getattr(cfg, "place_units", True) and not order:
        out.append((ERROR, "No unit is enabled on the Configs page."))
        return out
    names = getattr(cfg, "unit_names", {}) or {}
    priority = list(getattr(cfg, "upgrade_priority", []) or [])
    needs: dict[str, list[str]] = {}

    def need(key: str, why: str) -> None:
        needs.setdefault(key, []).append(why)

    placed = list(dict.fromkeys(order))
    for key in placed:
        if key not in priority and getattr(cfg, "upgrade_units", True):
            need(key, "place only")
    if len([k for k in placed if k in priority]) > 1:
        for key in priority:
            if key in placed:
                need(key, "upgrade priority")
    for field_name, why in (("upgrade_caps", "upgrade limit"), ("upgrade_from_wave", "upgrade from wave"),
                            ("farm_units", "farm unit")):
        value = getattr(cfg, field_name, None) or {}
        keys = value.keys() if isinstance(value, dict) else value
        for key in keys:
            if str(key) in placed and (not isinstance(value, dict) or int(value[key] or 0) > 0):
                need(str(key), why)
    missing = sorted(k for k in needs if not str(names.get(k, "")).strip())
    for key in missing:
        out.append((WARN, f"Unit {key} has no name on the Configs page, so its "
                          f"{', '.join(dict.fromkeys(needs[key]))} can't be applied (the name is how its "
                          "Upg button is found in the unit manager). MAACRO reads it off the hotbar in the next "
                          "match, or press 'Read names from the game' on the Configs page."))
    unplaced = [str(k) for k in (getattr(cfg, "place_from_wave", {}) or {}) if str(k) not in placed]
    if unplaced:
        out.append((WARN, f"'Place from wave' is set for unit(s) {', '.join(sorted(unplaced))}, "
                          "which aren't placed."))
    if mode == "general" and getattr(cfg, "after_match", "none") == "none":
        out.append((OK, "Any Stage waits on the results screen after each match — set 'After the "
                        "match' to Replay or Next Stage on its Configs tab to keep farming."))
    if not missing and not unplaced:
        out.append((OK, f"Unit setup: {len(order)} placements, {len(priority)} upgraded."))
    return out


def summary(results: list[tuple[str, str]]) -> str:
    errors = sum(1 for level, _ in results if level == ERROR)
    warns = sum(1 for level, _ in results if level == WARN)
    if errors:
        return f"{errors} problem{'s' if errors > 1 else ''}" + (f", {warns} to check" if warns else "")
    if warns:
        return f"{warns} thing{'s' if warns > 1 else ''} to check"
    return "All good"
