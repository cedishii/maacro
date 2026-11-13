# Changelog

## Unreleased

**New**
- **General mode:** places units, upgrades them and waits — for any match (story, raids,
  portals…). You start the match and handle everything after it; voting Yes and picking
  cards are optional switches.
- **General mode zones per unit** (`maps/general/`): Shibuya District saved — Elyssia,
  C.E.O. and Bulby on the ground loops, Phoenix on the green patches. General also zooms
  out again once the first wave starts.
- **Role: Party Member** (Summer Event and Infinity Castle): MAACRO plays the matches, the
  party leader picks portals and Return to lobby / Retry / Next Room.

- **More than 6 units** (General and Infinity Castle): upgrades now scroll the Unit
  Overview list (mouse wheel over the cards), not just the first 6 units; the top and the
  bottom of the list take turns.
- **Placements: Max** on the unit cards — place as many as the game's counter allows
  (e.g. 3/3 for Phoenix).

**Fixed**
- Infinity Castle: each room's map is recognised again (it kept Snowy Town's zones and
  walk for every later room). Snowy Town walks right like Summer's and zooms out again.

## v0.2.0 — 2026-11-13

**New**
- **Modes:** Summer Event and the new **Infinity Castle** (Infinity Mansion) — plays a
  room, then Next Room (or Retry after a defeat), forever. Pick it on the Modes page.
- **Per-unit settings cards** on the Configs page (enabled, name, placements, placement
  and upgrade priority), one tab per mode. Infinity Castle: mark damage units to place
  them on the circled path.
- **Discord updates:** a post per run (result, times, streak, map/mode, totals, drops,
  end screen), a "Stage rewards" post per drop with its picture, and alerts when
  MAACRO is stuck. Set up on the Settings page.
- Maps: Shibuya District, Puppet Island, Dungeon Throne, Mountain Temple, Sky Island,
  Assassin Park, Rain Village (walks right 3 s), Infinity Castle Snowy Town.

**Sturdier for long grinds**
- Stuck-screen watchdog: retries, then other ways past the screen, then "try
  everything" (Play if the lobby shows, known buttons, panels, popups), then a beep and
  a Discord alert.
- Clicks Reconnect after a Roblox disconnect; restarts its own background parts if one
  stops; starts over from Play if no teleport comes 20 s after matchmaking.
- Closes a unit's panel that kept the unit manager from closing (units waited forever).
- The lobby's "Travelling Merchant" sign (update 21) is no longer read as a loading screen.
- Lighter on the PC: fewer captures, a slower preview, less copying; screenshots capped
  (30 card picks, 100 end screens).

## v0.1.0
- First version: Summer Event loop (lobby → matchmaking → match → lobby), placing,
  upgrading, card picks, map zones, win/loss tracking.
