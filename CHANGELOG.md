# Changelog

## Unreleased

**New**
- **Cards: Easy / Hard on the Main page** (under Mode and Role, when Summer Event is
  selected). Saved at once; a running Summer macro uses it from the next card pick.
- **Summer Event card picks: Easy / Hard** (Configs → Summer Event). Easy: green first; red
  only for + Secret Drop Rate (the mildest of those) and the Star Golem card during Starfall.
  Hard: red cards as much as possible (+ Secret Drop Rate ones first, then the most
  SummerPearls, the mildest danger among equals; enemy regen still last), then the Star
  Golem card, then green.
- **Light mode** (Settings → Performance), for slower PCs: 3 pictures and 2 screen reads a
  second instead of 5 and 4; reacts a little slower. Measured: screen reading in a busy match
  21% → 12% of a CPU core.
- **Infinity Castle — green spots:** Phoenix (key 4) is placed only on the spots the game
  paints green when you pick it up; with no green spot free, the other units go first and
  Phoenix is tried again later (`green_units` in its settings).
- **Sky Portal, wave 10:** from wave 10 Phoenix/Marco is upgraded to at least upgrade 2
  before anything else, even if the farm isn't maxed yet (against leaks).
- **Sky Portal, new spot:** during Vote start it zooms out, votes Yes, then walks to the
  placing spot (Shift held: forward 4 s, left 3 s, forward 2 s — `walk_route` in its
  settings). Bulby on the green patch, 3 C.E.O. around it, 2 Elyssia on the path (up to
  upgrade 2), 3 Phoenix/Marco on the snow ledges (Max). Farm units first, then Phoenix and
  Elyssia. Spots beside the hotbar can be used now.
- **Sky Portal, new setup:** Bulby, 3 C.E.O., 2 Elyssia, 2 Fishi, then Phoenix ×Max on the
  balcony (avoiding the marked spot); Water Goddess isn't placed. Farm units maxed first,
  then Elyssia up to upgrade 2, Fishi up to 6, Phoenix up to 4 — read from the bar under
  each card ("Upgrade up to" on the Sky Portal Configs tab). Spots are now on the zoomed-out
  match view (the vote-start picture was more zoomed in). The log says when the unit list
  scrolls.
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
- The "Starting…" box has properly rounded corners (the window around it is see-through).
- **Opens smoothly:** a "Starting…" box is up in ~0.3 s while MAACRO loads (was 1.5 s of
  nothing); the full window shows at ~1.0 s (was ~1.5 s). The sidebar symbols cost Windows a
  ~350 ms font search on the first draw — the theme now names the font that has them.
  Only the Main page is built at launch; the others are built quietly right after, so every
  first click is instant (Configs took ~150 ms the first time).
- **Even less screen reading:** a picture that hasn't changed since the last read (menus, end
  screens, waiting) reuses that read for up to 1 s instead of running text recognition again
  (any real change — a banner, a number, a button — is read: checked region by region);
  while the macro only watches the match (all placed and maxed), it reads every 0.6 s. The
  log says how many reads were saved when the macro stops.
- **Screen reading ~2× cheaper:** the fuzzy text matching (half the cost of every read: thousands
  of difflib comparisons) skips comparisons that can't match and remembers answers — the same
  answers as before (checked on 832,416 cases), 87 ms → ~27 ms per read, ~0.3 ms when the text
  hasn't changed. Pictures are copied once instead of twice.
- **Opens faster, lighter when idle:** the window shows before screen capture starts, and
  MAACRO only lowers its priority once it's open. With the macro stopped and no page showing
  the game, it takes one picture and does one screen read a second. The live view is only
  built while it's on screen (Discord drop posts use the newest picture instead).
- **Lag / Roblox crashes:** lighter on the PC. While Roblox is in front its picture is copied
  from the screen instead of PrintWindow (which made Windows render the game again for every
  picture); 5 pictures a second instead of 8; screen reading at most half a CPU core (every
  250 ms, resting as long as each read takes); MAACRO runs below normal priority so Roblox
  gets the CPU first.
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
