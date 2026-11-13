# MAACRO

[![Latest release](https://img.shields.io/github/v/release/cedishii/maacro)](https://github.com/cedishii/maacro/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A free, open-source macro for **Anime Adventures** (Roblox) on Windows. It watches the
Roblox window, plays for you — placing and upgrading units, picking cards, moving on to
the next match — recovers by itself when something gets stuck, and posts results and
drops to Discord.

## Download

1. Install **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/)
   (tick *Add python.exe to PATH*).
2. Download **`MAACRO-v*.zip`** from the
   [latest release](https://github.com/cedishii/maacro/releases/latest) and extract it.
3. Double-click **`run.bat`**. The first time it installs what it needs (a few minutes),
   then MAACRO opens.

Keep Roblox open (behind other windows is fine, not minimized). Press **F1** to start,
**F3** to stop.

Or by hand:

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

## Features

- Two modes: **Summer Event** and **Infinity Castle** (see below).
- Places and upgrades units by your per-unit settings, using circled placement zones per
  map (and walks to a better spot first on some maps).
- Picks cards (Star Golem first, buffs over debuffs, the mildest debuff when all are red,
  never enemy regen).
- Recovers on its own: retries, other ways past a stuck screen, Reconnect after a
  disconnect, restarts its own parts if one stops — and alerts you if it truly can't.
- Discord updates: run results, drops with pictures, stuck alerts.
- Tracks wins, losses, win rate, pearls and drops per session.

## Modes

Pick the mode on the Main page (stop the macro to switch). Each mode has its own
controller and its own settings tab on the Configs page; only one runs at a time.

- **Summer Event** — the original macro: lobby → ring → matchmaking → match → back to the lobby.
- **Infinity Castle** (Infinity Mansion) — start it inside the castle. It plays a room, then
  presses Next Room (or Retry after a defeat), forever, until you stop it. No lobby,
  matchmaking or captcha. Damage units (ticked on their unit card) go in the circled path
  zones of `maps/infinity_mansion/`; the other units are kept out of them.

Both modes recover by themselves when a screen gets stuck (retries, then other ways
to get past it, then a beep after 10 minutes) and click Reconnect after a disconnect.

## Layout

- `maacro/capture.py` — finds the Roblox window and captures it
- `maacro/vision/ocr.py` — reads text off the screen (Windows built-in text recognition)
- `maacro/vision/screens.py` — decides which game screen is showing
- `maacro/game_state.py` — steadies detection, counts each win/loss once
- `maacro/detector.py` — background thread tying capture + detection together
- `maacro/stats.py` — wins, losses, win rate, session time
- `maacro/macro.py` — the Summer Event controller (run loop, placing, upgrading, cards)
- `maacro/infinity_castle/` — the Infinity Castle controller, settings and map zones
- `maacro/modes.py` — the list of modes (controller + settings per mode)
- `maacro/ui/` — the window, pages and theme
- `FLOW.md` — how one run works, step by step

## Progress

1. [x] App shell: live view, overview, process log
2. [x] Detect screens (lobby, win, loss…) and count results automatically
3. [x] Run loop: Play → walk to ring → Find Match → (captcha: player) → vote Yes → Next → Return to lobby
   - F1 = start, F3 = stop. Uses the real mouse/keyboard while running.
4. [x] In the match: place units (order on the Configs page), upgrade to Max via the unit manager, pick cards
   - Numbers (card votes, yen) go through `maacro/vision/numbers.py` (`NumberReader`); providers are
     registered in `PROVIDERS`, so another reader can be added later. The verification screen is
     read only by the optional captcha helper (`screen-number-typer`).
5. [x] Drop tracking, Discord updates, settings
6. [x] Modes: Summer Event and Infinity Castle; per-unit settings; self-recovery

## License and credits

MIT — see [LICENSE](LICENSE). You're free to copy, change and share MAACRO; keep the
license file. Libraries used and thanks: [CREDITS.md](CREDITS.md). Want to improve it or
add maps/modes? See [CONTRIBUTING.md](CONTRIBUTING.md). What changed: [CHANGELOG.md](CHANGELOG.md).

MAACRO is fan-made and not affiliated with Roblox or Anime Adventures. Using macros may go
against a game's rules — use it at your own risk.
