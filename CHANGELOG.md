# Changelog

## Unreleased

**New**
- **Sky Portal follows the spawn:** the view is lined up with the reference picture each
  match and every spot shifts with it. Zooms out during the vote; places 2.5× faster.
- **Sky Portal setup:** Bulby (blue), 3 C.E.O. (green), 2 Elyssia (grey), 2 Fishi (red) on
  the exact spots drawn on `maps/sky_portal/sky_portal_units.png`; every unit is placed
  before any upgrade; farm units (Bulby, C.E.O.) are maxed first, then the damage units.
  Smart placing: spots taken → tries close by; a unit missing from the Unit Overview is
  placed again. "Farm unit" tick box on the Sky Portal Configs tab.
- **Sky Portal mode (party member):** waits in the lobby, votes Yes on Vote start (the
  vote is everyone's; switch in its Configs tab), then zooms out, places and
  upgrades your units and waits. Never clicks Play, Next, Replay or Return to lobby. Own
  Configs tab; uses the General map zones (`maps/general/`, e.g. from the Recorder).
- **Recorder page:** place your units by hand (unit key or card, then click) and MAACRO
  records each spot; Save turns them into General mode zones for that map, per unit
  (`maps/general/`). Units you didn't record keep their zones.
- **Actions page:** your own rules for General mode — when a screen is up (lobby, vote
  start, in a match, card vote, match over, after the match), click text on it or press a
  key, once or every N seconds. E.g. auto Replay. Matchmaking/verification screens can't
  be used.
- **Place-only units:** each unit card on the Configs page has an "Upgrade" tick box.
  Untick it and the unit is still placed but never upgraded (it needs its name filled in).
  All modes.
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
- Sky Portal didn't place Fishi: with no Sky Portal settings saved yet it copied the Summer
  units (no Fishi) instead of using its own defaults.
- Upg buttons were matched to a unit called "Fishi" (read as "First"): the cards' button
  labels are no longer taken for unit names.
- Sky Portal: long upgrading in the unit manager no longer counts as "stuck".
- **Card picks behind the unit manager** (all modes): the 5-second peek watched only the
  first screen read after closing the manager, so a card pick that showed up a moment
  later was covered again and skipped (seen at wave 9). It now watches for 2.5 s, and a
  card pick seen while upgrading closes the manager first.
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
