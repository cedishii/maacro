# MAACRO

A macro for Anime Adventures (Roblox). It watches the Roblox window, shows it live,
and tracks runs, wins, losses and win rate.

## Run

Double-click `run.bat`. The first time, it sets up Python packages.

Or by hand:

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

Keep Roblox open (it can be behind other windows, but not minimized).

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
     never read.
5. [ ] Item tracking, Discord updates, settings
