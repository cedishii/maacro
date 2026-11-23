# Changelog

## Unreleased

**Fixed**
- **Day zones on a Night stage.** The loading screen shows "Misty Village" and "Night Stage" on
  separate lines, and the Day map matched the first; a map named for Day / Night now needs that
  word in the same text.
- **Misty Village: the lobby read as a match no longer gets match keys.** Live, the lobby (and the
  stage window, whose "for first clear" reads like the unit manager's First buttons) was read as a
  match / the unit manager: MAACRO pressed O, tried placing, and pressed F, which in the lobby
  opens the Store (the Exclusive Shop). With the lobby's buttons on screen it now does the lobby
  step instead. The Night timer is read up to 3 times before picking Day.
- **Misty Village: Find Match pressed even when the window is misread.** Live, "Join Matchmaking?"
  was up but read as "In match" (the stage window's "Level Info" under it) and nothing was pressed;
  the window's title now hands it to the player's matchmaking/captcha code whatever the reading.
- **Misty Village: no "placing" on the lobby.** The stage window has a "Level Info" button, which the
  screen reader takes for a match; when no match started after the captcha, MAACRO pressed hotbar
  keys and clicked the lobby for 8 minutes while an Exclusive Shop (Robux Purchase buttons) was
  open. With the stage window up it now only waits, and after 90 s presses Cancel and starts over.
  "Exclusive Shop" is closed like the village shop, before anything else. The "back to the lobby
  for Night/Day" note is only logged when it's really done.
- **Stray clicks in the unit list.** Upgrade clicks could land while the list was still moving
  (right after the jump to the top) or while the panel was sliding back in after the card-pick
  peek, opening a unit's panel or its targeting menu. Clicks now wait until the list and the panel
  stand still on two reads in a row; an open targeting menu is closed (by clicking the title, so
  no unit's targeting changes) before anything else. The sliding panel was also mistaken for "the
  list went back to the top"; that's waited out now (seen live on two screenshots).
- **Slow to get through the list.** A read that missed the "Unit Overview" title (common right after
  the card-pick peek) sent a scroll in progress back to the top; it now waits for the next read.
  Each part of the list is upgraded for 6 s (was 10 s) and a part with nothing to do is left after
  1 s (was 1.5 s).
- **A list left at the bottom was taken for "all maxed".** Each sweep assumed the list starts at the
  top; when it had been left at the bottom (all Max there), the first scroll down didn't move it, so
  it was taken for a list that doesn't scroll. Every sweep now starts by going to the top.
- **Summer Event never scrolled the Unit Overview.** The scrolling was only in the other modes, so with
  more than 8 units Summer upgraded what was on screen, then called everything "maxed". Summer now
  scrolls too (every mode is checked by a test).
- **The 5-second card-pick peek no longer restarts the sweep.** It closes the manager for ~3 s, which
  counted as "reopened → back to the top", so a long list never got past its first parts. If the
  game really did put the list back at the top, the picture shows it and the count starts over.
- **Unit Overview scrolling got stuck at the bottom.** The panel is see-through, so the game's text
  behind it was read as part of the list; it changed on every read, the bottom was never noticed,
  and the macro kept scrolling down (up to 15 steps, 10 s each) instead of going back up. A
  "First" button OCR missed on one read had the same effect. Now only the cards are compared (each
  "First" button and the unit name on that card), and a small misread doesn't count as a move.
- **New units are checked straight away.** After a unit is placed, when the manager is opened again,
  and after a "maxed" recheck, upgrading starts from the top of the list. A short list that didn't
  scroll before is checked again when a unit is placed.
- Going back to the top is checked; if the list didn't move up, it's scrolled up again.
- **Scrolls are now checked on the picture, not only the text.** Text reading misses a lot on the
  Unit Overview (on a real Infinity Castle screenshot: 4 of 6 "First" buttons, one unit name), so
  the cards' picture is compared before and after each scroll (small blocks, brightness evened out:
  a scroll changes 80–95 % of the blocks, the game moving behind the see-through panel ~35 % at
  most). Only when the picture can't tell does the text decide. Checked on real screenshots, even
  with no card text read at all.

**New**
- **The game's auto upgrade (T).** "Use the game's auto upgrade" on Configs (Summer and every Any
  Stage-based mode): in the unit manager MAACRO presses T until "Auto Upgs Active" shows (T toggles,
  so never while it's on), then closes it and leaves upgrading to the game for the match. If it
  doesn't turn on after 3 tries, MAACRO upgrades by itself as before.
- **Configs boxes are click-to-pick lists** (placements, priorities, upgrade cap), and the mouse
  wheel never changes a box anywhere in MAACRO: it scrolls the page.
- **Misty Village: land and air zones.** Day Stage zones from the player's drawings (red = land,
  orange = air; maps/general/misty_village_day.json). Each unit has an **"Air unit"** tick on the
  Misty Village Configs tab: air units go in the orange zones, the rest in the red ones. Maps can be
  made the same way for other stages (`create_kind_map`, pen colours read from the drawing). A map
  named for Day never matches the Night stage (and the other way round).
- **"No upgrades" per unit** on every Configs tab (was an unclear "Upgrade · priority" tick): the unit
  is placed and never upgraded; its upgrade priority / cap / wave grey out.
- **Misty Village: "Day stages only" on the Main page** too (like Summer's card picks), applied
  right away, even while running.
- **Play only, never Areas** (Misty Village, Story, Infinite): when the Play window doesn't open or
  the tile isn't found, it tries Play again later instead of opening Areas (Challenge still uses
  Areas → Challenges). The Play button is also found by a close read or its usual place.
- **Misty Village: Replay first.** "Return to lobby" is only taken after 4 tries without Replay read
  (live, the first read had only "Return to lobby"), unless it's switching Day ↔ Night. The shop
  closer only reacts to "Village Shop" now and saves a picture each time it closes one.
- **Misty Village: Find Match is clicked on the button.** Its label is never read there, so the
  matchmaking code got the "Join Matchmaking?" title and clicked it (nothing happened, every 4 s).
  The button's place now comes from the title (`find_match.py`; the code in macro.py is unchanged).
  Live: Find Match → captcha in 1 s → number read and typed → Submit → match found. Misty Village
  only for now. The Play window's tiles are also clicked by place when their labels aren't read.
- **Lobby Play button (update 21.5).** Play opens "Where do you want to Play?" (Summer Event / Misty
  Village / Regular Stages). Misty Village and Story / Infinite (Regular Stages) now go that way;
  the Areas window is the fallback when the Play window doesn't open, and stays the way for
  Challenges.
- **Misty Village: the village shop is closed when it pops up**, with the red X next to its title
  (found by colour, `close_x.py`). Never while the unit manager is open, and never an X the size
  of the unit cards' ones (those sell the unit).
- **Misty Village mode** (update 21.5). From the lobby: Areas → scrolls to Misty Village → walks right
  (D 5 s, then S 0.5 s if the stages window didn't pop up) → **Night** stage whenever it's open
  ("Dawn breaks in …"), otherwise **Day** ("Night falls in …"; misread digits like "51:oq" are
  handled) → Select → Find Match and the captcha with the player's own matchmaking code. After a
  match: Replay, but back to the lobby to switch to Night when it opens, or to Day when dawn comes.
  **Day stages only** on its Configs tab plays Day every time. Tested live: lobby route, Day pick,
  Select, a 15-wave win with placing and scrolling upgrades, Return to lobby, and back in.
- **MAACRO notices when it was updated.** Stopping and starting (F3 / F1) keeps running the code
  that was loaded when MAACRO opened, so an update did nothing until MAACRO was closed and opened
  again. Now Start says so and offers **Restart now** (the new copy waits for the old one to close;
  settings are kept) or starting the old version anyway.
- **Record your play, MAACRO plays it back** (Settings → *Your own play*, off until you switch it
  on). A **Record** button sits under Start / Stop. Recording starts when the match starts (the
  vote is over) and stops when you press Return to lobby; it reads your real keyboard and mouse
  (keys, clicks and where they were, the wheel, camera turns — read only, MAACRO's own clicks
  left out) and stamps each action with its wave and the seconds into that wave. On a recorded map
  the mode then plays your recording during the match instead of its own placing and upgrading;
  each action waits for its wave, so a faster or slower run stays in step. Card votes stay with
  the card strategy; lobby, results and rejoin work as before.
  - When a map that isn't recorded yet is loading ("Travelling to… Fiend City / Summer Hunt"),
    MAACRO comes to the front and asks whether to record it; a recorded map is just played.
  - Pressing Record on a recorded map asks "redo the recording?" first; a lost match asks whether
    to keep it. Recordings are listed (and can be deleted) in Settings.
- **Accurate walks and turns.** Walks are timed to the millisecond (keys used to be let go up to
  0.15 s late) and can do more than hold keys: `turn 240` / `turn -150` turns the camera the way
  a hand does (right button held, the mouse moved by exact counts in small even steps, so the
  same turn every time), `w until select world 6` walks until a text shows (at most 6 s), and
  `wait 0.5` pauses. **Record** now catches camera turns too (the mouse's raw movement while the
  right button is held: Roblox locks the cursor then, so its position doesn't change). Read
  only; nothing is pressed while recording.
- **Overnight** (Settings): *Keep the PC awake* while the macro runs (a sleeping or locked PC
  gives black pictures); *Carry on after a crash or a PC restart* (MAACRO starts the macro again
  20 s after it opens, Stop cancels); *Open MAACRO when Windows starts*; *Start at* a clock time;
  *Fresh Roblox every N hours*, restarted only between matches.
- **Loss replays:** a ~20 s sped-up video of the last 3 minutes before each defeat
  (`runs/<time>_loss.mp4`, the newest 10), so you can see where the defence broke. Small pictures
  kept in memory (~3 MB), saved in the background. Discord: `!replay`.
- **Record the walk into the door** (Configs → *Start from the lobby* → Record): walk it once
  yourself in Roblox; MAACRO only reads the keys you hold (like the hotkeys) and writes the walk
  ("w+d 1.8, w 0.4"), with Sprint on if you held Shift. Fingers not lifting together are folded
  away, pauses dropped.
- **A picture of every failed lobby step** in `logs/lobby/` (the newest 20), named after what
  failed, so a step that misses in the game can be fixed from what MAACRO saw.
- **Time to goal** on the Main page and in Discord status: "38 runs left · ≈ 5 h (done ≈ 21:40)",
  from this session's pace (the gaps between matches included); the soonest goal wins.
- **Stats: Insights and a 14-day chart** — best map for pearls per hour, card styles compared,
  where most losses are, the slowest map, this week against last; wins and losses per day.
- **Discord `!mode` and `!goal`:** `!mode story` switches mode (and starts it again if it was
  running), `!mode` lists them; `!goal 50` stops after 50 runs this session.
- **Start from the lobby by itself** (Story, Infinite, Challenge → Configs → *Start from the
  lobby*): Areas → Play Area / Challenges → walk into a door (W+D 2 s by default, editable;
  stops early once Select World shows) → Story / Infinite: scroll the Select World list to the
  map → Act N (or Infinite) → Normal / Hard → Select → Start if shown. Text is read on zoomed
  crops with the buttons' usual places as a fallback (the Areas button on the right edge, the
  tiles from the window's title). A failed step presses Cancel and retries later (30 s; 5 min
  for challenges); three failures in a row raise a "check the game" alert. With auto-rejoin,
  a disconnect now ends back in the stage too.
- **Story, Infinite and Challenge modes** (built on Any Stage's tested match play, each with its
  own Configs tab, Actions list and profiles):
  - *Story*: a win → Next Stage (on through the acts), a defeat → Retry; or farm one act
    (always Replay). After the last act (a win with no Next Stage, seen twice): replay it, or
    stop with a Discord summary.
  - *Infinite*: plays until the defeat that ends the run, then Replay; the log keeps the wave
    reached and the session's best. Stats show "Infinite" as its own stage kind.
  - *Challenge*: Replay if the game offers it, otherwise Return to lobby (or always lobby, or
    leave it to you); lobby Actions can walk to the next challenge.
- **Actions per mode** (Actions page → "Actions for").

**Changed**
- Any Stage is now for legend stages, raids, portals and the rest; Story has its own mode.
- The Modes page scrolls (seven modes no longer squash their descriptions).
- **Stop at a clock time** (Settings → Session goals): e.g. 07:00 — started at 23:00, it stops
  at 07:00 the next morning.
- **Discord status post every N minutes** (Settings → Discord updates): a picture of the game
  plus screen, map, wave, results, runtime and goal, while the macro runs.
- **Unit names read off the hotbar:** a placed unit with no name (needed to find its Upg button
  for upgrade priority, limits, farm units…) gets it from the name under its hotbar card at
  the start of a match — several pictures vote, the base name is kept ("Elyssia (Abyssal)" →
  "Elyssia") — and it's saved on the Configs page (not while a map profile is in use). Configs
  also has a *Read names from the game* button.
- **Smart card picks** (Summer): Hard while winning; after a defeat, Easy for the next 2 runs,
  then Hard again — one lost run (no pearls at all) costs more than a few Hard runs earn.
- **Card style per run:** runs.csv records the style each run was played with, and the Stats
  page compares them (*By card style*: win %, pearls per run with losses counted as 0, pearls
  per hour).
- Stats groups show pearls per run and per hour.
- **Auto-rejoin is on by default** (still only while the macro runs). In the logs, two
  disconnects where Reconnect never worked cost 46 and 68 minutes; rejoin restarts Roblox after
  2 minutes. The setup check warns when it's off.
- **Per-unit timing and upgrade limits, every mode** (Configs → unit cards): *Upgrade up to*
  (stop after N upgrades, read from the bar under the unit's card — was Sky Portal only),
  *From wave: place* (keep a unit back until that wave; the others go first, and upgrading
  goes on meanwhile) and *From wave: upgrade* (money goes to the other units until then).
  Saved in profiles and share codes too.
- **Setup check** (Main page → Roblox → Check, and on every Start): Roblox open / minimized,
  window size and shape, Windows text recognition, how many screen reads are recognised, and
  unit settings that can't work (e.g. an upgrade limit on a unit with no name — the name is
  how its Upg button is found). Problems go to the log.
- **Summer Hard card picks take the highest Secret chance:** among red cards with Secret drop
  chance, the one with the biggest "+N% Secret Drop Rate" wins (+100% over +50% over +25%),
  even if another pays more SummerPearls; equal Secret chance → most pearls → mildest danger.
  Misreads like "SO%" (50%) are understood; an unread amount counts as the lowest. The log
  shows the others' amounts.
- **Profiles by map:** name a profile after a map ("Shibuya District", or "Rain Village Summer
  Hunt" for one stage kind) and its team and plan are used by themselves whenever a match on
  that map starts — before anything is placed; other maps use the mode's own setup. Works in
  every mode (Settings → Profiles by map, on by default).
- **Discord remote control** (Settings): with a bot of your own, type `!status`, `!stats`,
  `!ss` (screenshot), `!start`, `!stop`, `!rejoin` or `!help` in your channel — answered for
  your user ID only. "Test connection" connects the bot once (Discord requires it before a new
  bot may post) and posts a hello. No extra packages.
- **Hold-key actions** (Actions page): hold a key for up to 30 s — a few in a row walk a route
  (e.g. lobby → portal), then a "click text" action presses the button there.
- **Any Stage mode** (was "General"): for story, legend stages, raids, challenges and portals.
  New *After the match* choice on its Configs tab: leave it to you (as before), **Replay** the
  stage, or **Next Stage** (Replay when there's no next one). It presses Next on the results
  screen and then Replay / Next Stage — never Return to lobby or "Waiting for Players"; if the
  button text can't be read 3 times, it presses Replay's usual spot.
- **Stats page** (sidebar): every run in `runs/runs.csv` — all-time runs, win rate, today,
  best win streak, runs per hour, average stage time, and tables per map, per stage kind
  (Act, Summer Hunt, Infinity Mansion, Portal…), per day, and the latest 50 runs. Misread
  map names ("Shibuya DistVi Act 6", "Rain MILage") are matched to the real map. The Main
  page shows **All-time Runs** too.
- **Session goals** (Settings): stop after N runs, after so many minutes, or after N losses
  in a row; a Discord summary is posted (with a ping), and Roblox can be closed too.
- **Auto-rejoin** (Settings → Roblox): paste a private server link (share link or
  `privateServerLinkCode` link; empty = a public server). While the macro runs it opens
  Roblox again when it's closed/crashed (60 s), restarts it when the Disconnected box stays
  up (120 s), and optionally when stuck on one screen. At most 6 times an hour, 3 min apart.
  "Open Roblox now" checks the link.
- **Profiles and share codes** (Configs, every mode): save the setup under a name, load it
  in one click, copy it as a `MAACRO1:` share code or import a friend's. Imported values are
  checked (wrong types and unknown keys are ignored).
- **Hotkeys** (Settings): pick the start and stop keys (F1–F12).
- `runs.csv` now records the mode of each run (older files get the new column by themselves).

**Changed**
- Settings page reorganised into Session goals, Roblox, Hotkeys, Discord and Performance.
- The SummerPearls row on the Main page only shows in Summer Event (or once pearls are earned).
- Check boxes are drawn as clear rounded squares (unticked ones were hard to see).
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
- Pearls per hour counted the pearls of runs whose stage time wasn't read, so a map could look
  far better than it is.
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
