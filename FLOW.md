# MAACRO — how one run works

Reference screenshots are in `screens/`.

## Lobby → match

| # | Screen | What MAACRO does | Status |
|---|---|---|---|
| 1 | Lobby (`01_lobby`) | Click **Play** | In lobby |
| 2 | Teleported in front of the yellow ring (`02_after_play`) | Hold **W** until the "Join Matchmaking?" box appears (time out → retry from lobby) | Walking to matchmaking |
| 3 | "Join Matchmaking?" (`03_join_matchmaking`) | Click **Find Match** | Joining matchmaking |
| 4 | Captcha (`04_captcha_*`) | **full automated now**Submit**.|
| 5 | "Matchmaking started / Teleporting / Match found" (`05_match_found`) | Wait for the match to load | Matchmaking → Match found |
| 6 | "Vote start: 0/6" (`06_vote_start`) | Click **Yes** right away (setting, on by default). If others are slow, the countdown finishes anyway. | Vote start – waiting |

## In the match

### Placing units (all placed first, then upgrade)
- Hotbar keys 1–6 (`10_hotbar_slots`). Default plan, editable on the Configs page:
  - Order: **6, 5, 5, 5, 1, 1** → Bulby ×1 (key 6), C.E.O. ×3 (key 5), Elyssia ×2 (key 1)
- Units 1, 5 and 6 work from anywhere on the map, so **no saved spots per map** (there are 25+ maps).
- At the start of the match: hold **O** to zoom out (more ground and path on screen).
- Place = press the key → in placement mode the game paints everywhere you **can't** place red
  (roofs, the arrow road). Candidates = ground that isn't red, nearest the yellow-arrow road
  first, spread out; beside units already placed comes first of all. Spots that failed are
  not retried that match. (The dashed circle that follows the mouse is the unit's range:
  blue = can place, red = can't.)
- The mouse is moved to the top of the map after each click: the Place/Rotate/Cancel menu
  follows the mouse and would hide the counter.
- **Proof of placement = the counter above the selected hotbar unit going up** ("0/3" → "1/3";
  red "2/2" = full). The game stays in placement mode after placing, so the Place menu
  closing proves nothing. Units the player already placed are counted too.
- "Not enough money!" (`16_not_enough_money`) → press Q (cancel), wait, retry.
- At most 10 spots per try, so card picks never wait.

### Upgrading
- Open the unit manager with **F** (`09_unit_manager`).
- Priority: units from keys **6 and 5** first, then key **1**. Keep going until every unit shows **Max**.
- Upg buttons are found by colour (solid green) and by their "Upg" text (some units' last
  upgrade is a gold button). "All maxed" = no Upg button or text on 4 reads in a row.
- Clicking "Upg" when it's too expensive does nothing, so spamming is fine.
- Keys: **R** = upgrade, **X** = sell (available as actions).

### Card pick — every few waves (`07_card_pick`, `08_card_pick_green`)
0. A **Star Golem +100%** card (Starfall weather: "Wishing Star … Starfall Card"; any of "golem", "Wishing Star", "Starfall Card" in its text) → always pick it.
1. Any **green / non-red** card → pick it.
2. Enemy **Regen** cards are never picked (unless all three are Regen).
3. All red → the **mildest** card: smallest SummerPearls bonus (a read under 10% is a cut-off number and is ignored), then the mildest kind (Enemy Health, then Physical Resist), then the smallest "+N Enemy …" number, then the most votes, then the leftmost.
3. Click **Vote**.

## End of match
- **Victory** (`11_victory`): yellow "VICTORY!!!" → count a **win**.
- **Defeat** (`12_defeat`): red "DEFEAT" → count a **loss**.
- Click **Next** → "Return to lobby" / "Replay" (`13_after_next`) → click **Return to lobby**, then start again from step 1.

## Stats (app Overview panel)
Wins, losses, win rate, completed runs, session time, current map.
