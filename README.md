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

## Layout

- `maacro/capture.py` — finds the Roblox window and captures it
- `maacro/vision/ocr.py` — reads text off the screen (Windows built-in text recognition)
- `maacro/vision/screens.py` — decides which game screen is showing
- `maacro/game_state.py` — steadies detection, counts each win/loss once
- `maacro/detector.py` — background thread tying capture + detection together
- `maacro/stats.py` — wins, losses, win rate, session time
- `maacro/ui/` — the window, pages and theme
- `FLOW.md` — how one run works, step by step; `screens/` — reference screenshots

## Tests

```
.venv\Scripts\python -m unittest discover tests -v
```

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
