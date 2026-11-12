# Map zones

One `<map>.json` per map: where MAACRO tries to place units on that map.

## Making one

Take a screenshot of the whole Roblox window in a match (zoomed out, after any
walk below), then:

- circle the areas where units can go in **pure white**,
- scribble over anything inside a circle that units can't use in **pure red**.

Then save it with `maacro.maps.create_map("<Map Name>", <screenshot>)`.

Tip: treat every building and piece of furniture (roofs, vents, stalls, domes,
benches…) as a red area. Some of them don't show red in placement mode, but
units can't actually go there.

## Walking before placing

A map can have a walk in its JSON, done once per match before the first unit:

```json
"walk": { "key": "d", "seconds": 4.0, "jump": true }
```

Hold `key` for `seconds` (tapping Space if `jump`), then place. The zones must
be drawn from where the walk ends.

Maps that are better with a short walk first (tip from a friend, not set up
yet — add a walk when we get them):

- Cursed Festival
- Magic Town
- Virtual Dungeon
- Magic Hills
- Sky Aircraft
- Ant Kingdom
- Haunted Mansion (zones saved, no walk yet)
- Adventurer Town

Set up: Snowy Town (D + jump, 4 s).
