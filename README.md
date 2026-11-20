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

- Modes for **Story** (through the acts, or farm one), **Infinite** (Replay after each run),
  **Challenge**, **any other stage** (legend, raids, portals), **Summer Event**,
  **Infinity Castle** and **Sky Portal**.
- Places and upgrades units by your per-unit settings, using circled placement zones per
  map (and walks to a better spot first on some maps).
- Picks cards (Star Golem first, buffs over debuffs, the mildest debuff when all are red,
  never enemy regen).
- Recovers on its own: retries, other ways past a stuck screen, Reconnect after a
  disconnect, restarts its own parts if one stops — and alerts you if it truly can't.
- **Session goals:** stop by itself after N runs, after so long, or after too many losses
  in a row — then a Discord summary, and optionally close Roblox.
- **Auto-rejoin:** opens Roblox again on your private server link (or a public server)
  when it closes, crashes or stays disconnected.
- **Stats page:** every run ever recorded — totals, today, streaks, runs per hour, insights
  (best map per hour, card styles compared, where the losses are), a 14-day chart, and results
  per map, per stage kind and per day (misread map names are matched up).
- **Time to goal:** how long until the session goal at this session's pace.
- **Overnight:** keeps the PC awake, carries on after a crash or a Windows restart, opens with
  Windows, starts at a clock time, and restarts Roblox every few hours between matches.
- **Loss replays:** a short video of the minutes before each defeat (`!replay` on Discord).
- **Profiles and share codes:** keep a setup per stage or team, switch in one click, and
  share a setup as one line of text (`MAACRO1:…`).
- **Per-unit plans:** upgrade a unit only up to N, place or upgrade it only from wave N.
- **Setup check:** finds window, screen-reading and unit-setup problems before they cost runs.
- **Profiles by map:** a profile named after a map is used by itself on that map.
- **Discord remote control:** `!status`, `!stats`, `!ss`, `!start`, `!stop`, `!rejoin`,
  `!mode story`, `!goal 50`, `!replay` from your phone, through a Discord bot of your own.
- **Actions:** click text, press or hold keys on any screen (Any Stage) — e.g. walk a lobby
  route and press Play.
- Changeable start/stop hotkeys (F1/F3 by default).
- Discord updates: run results, drops with pictures, stuck and rejoin alerts.

## Modes

Pick the mode on the Main page (stop the macro to switch). Each mode has its own
controller and its own settings tab on the Configs page; only one runs at a time.

- **Summer Event** — the original macro: lobby → ring → matchmaking → match → back to the lobby.
- **Story** — start the first act; a win → Next Stage, a defeat → Retry, or farm one act. After
  the last act it replays it or stops.
- **Infinite** — plays each run until the defeat that ends it, then Replay; logs the wave reached.
- **Challenge** — plays the challenge, then Replay if offered, otherwise Return to lobby.

Story, Infinite and Challenge can also **start from the lobby by itself** (their Configs tab):
Areas → Play Area / Challenges → walk into a door → (map → act / Infinite → difficulty →
Select) → play. **Record** the walk once by walking it yourself (camera turns included); a
failed step saves what MAACRO saw in `logs/lobby/`. A walk is steps separated by commas, timed
to the millisecond:

| Step | Does |
|---|---|
| `w+d 2` | hold W and D for 2 s |
| `w until select world 6` | hold W until that text shows (at most 6 s) |
| `turn 240` / `turn -150` | turn the camera right / left (mouse counts, right button held) |
| `wait 0.5` | pause |
- **Any Stage** — for everything else (legend stages, raids, portals, someone else's lobby). Start a stage yourself; MAACRO places, upgrades and waits. Set
  *After the match* on its Configs tab to **Replay** (farm the stage) or **Next Stage**
  (go on through the acts), and it keeps going by itself. It never clicks Play or Return
  to lobby; the Actions page can add those.
- **Infinity Castle** (Infinity Mansion) — start it inside the castle. It plays a room, then
  presses Next Room (or Retry after a defeat), forever, until you stop it. No lobby,
  matchmaking or captcha. Damage units (ticked on their unit card) go in the circled path
  zones of `maps/infinity_mansion/`; the other units are kept out of them.

All modes recover by themselves when a screen gets stuck (retries, then other ways
to get past it, then a beep after 10 minutes) and click Reconnect after a disconnect.

## Layout

- `maacro/capture.py` — finds the Roblox window and captures it
- `maacro/vision/ocr.py` — reads text off the screen (Windows built-in text recognition)
- `maacro/vision/screens.py` — decides which game screen is showing
- `maacro/game_state.py` — steadies detection, counts each win/loss once
- `maacro/detector.py` — background thread tying capture + detection together
- `maacro/stats.py` — wins, losses, win rate, session time
- `maacro/history.py` — all-time results from `runs/runs.csv` (Stats page), map-name matching
- `maacro/goals.py`, `maacro/app_settings.py` — session goals and app-wide settings
- `maacro/relaunch.py` — server links and auto-rejoin
- `maacro/profiles.py` — saved setups and share codes; `maacro/auto_profile.py` — picked by map
- `maacro/remote.py` — Discord remote control (bot commands)
- `maacro/lobby_start.py` — starting a stage from the lobby; `maacro/walk_record.py` — recording the walk
- `maacro/night_guard.py` — overnight: keep awake, resume, start with Windows, fresh Roblox;
  `maacro/loss_replay.py` — loss replay videos
- `maacro/unit_plan.py` — per-unit upgrade limits and wave timing; `maacro/setup_check.py` — setup check
- `maacro/macro.py` — the Summer Event controller (run loop, placing, upgrading, cards)
- `maacro/infinity_castle/` — the Infinity Castle controller, settings and map zones
- `maacro/modes.py` — the list of modes (controller + settings per mode)
- `maacro/ui/` — the window, pages and theme
- `FLOW.md` — how one run works, step by step

## Progress

1. [x] App shell: live view, overview, process log
2. [x] Detect screens (lobby, win, loss…) and count results automatically
3. [x] Run loop: Play → walk to ring → Find Match → (captcha: player) → vote Yes → Next → Return to lobby
   - F1 = start, F3 = stop (changeable in Settings). Uses the real mouse/keyboard while running.
4. [x] In the match: place units (order on the Configs page), upgrade to Max via the unit manager, pick cards
   - Numbers (card votes, yen) go through `maacro/vision/numbers.py` (`NumberReader`); providers are
     registered in `PROVIDERS`, so another reader can be added later. The verification screen is
     read only by the optional captcha helper (`screen-number-typer`).
5. [x] Drop tracking, Discord updates, settings
6. [x] Modes: Summer Event and Infinity Castle; per-unit settings; self-recovery
7. [x] General AA: Any Stage with Replay / Next Stage, session goals, auto-rejoin, Stats page,
   profiles and share codes, hotkeys

## License and credits

MIT — see [LICENSE](LICENSE). You're free to copy, change and share MAACRO; keep the
license file. Libraries used and thanks: [CREDITS.md](CREDITS.md). Want to improve it or
add maps/modes? See [CONTRIBUTING.md](CONTRIBUTING.md). What changed: [CHANGELOG.md](CHANGELOG.md).

MAACRO is fan-made and not affiliated with Roblox or Anime Adventures. Using macros may go
against a game's rules — use it at your own risk.
