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
"walk": { "key": "d", "seconds": 4.0, "jumps": 2 }
```

Hold `key` for `seconds`, then (still holding it) jump `jumps` times, then
place. `"jump": true` instead taps Space the whole way. The zones must
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

Set up: Snowy Town (D for 4 s, then jump twice), Storm Hideout (W for 2 s), Dungeon Throne (W for 0.6 s), Rain Village (D for 3 s). No walk: Shibuya District, Puppet Island, Mountain Temple, Sky Island, Assassin Park.

## Infinity Castle zones (`maps/infinity_mansion/`)

Separate from the Summer zones above: the same map is played from another spot there,
and the circles mark the path where damage units must go. Saved: Snowy Town.

## General mode zones (`maps/general/`)

General mode looks here first, then falls back to the Summer zones above.
Each map can give **different units different zones** (`zone_sets`), one
screenshot per group of units, all from the same zoomed-out camera:

```python
from maacro.general.maps import create_general_map
create_general_map("Shibuya District", [(["1", "5", "6"], "ground.png"), (["4"], "phoenix.png")])
```

A unit that isn't in any group uses automatic spots. Saved: Shibuya District
(units 1, 5, 6 on the ground loops around the spawn; unit 4, Phoenix, on the
green patches: left strip, top-left, bus roof, right road).
