# Contributing / building on MAACRO

MAACRO is MIT-licensed: copy it, change it, share it. Keep the `LICENSE` file (and a
line in your README crediting MAACRO is appreciated). Ideas, fixes and new maps are
welcome as issues or pull requests.

## Getting started

```
git clone https://github.com/cedishii/maacro.git
cd maacro
run.bat            # first run installs the packages, then opens MAACRO
```

Windows 10/11 and Python 3.11+ are needed (text recognition uses Windows' own OCR).

## Where things are

See the *Layout* section of `README.md` and `FLOW.md` (how one run works, step by step).
In short:

- `maacro/macro.py` — the Summer Event controller (run loop, placing, upgrading, cards,
  recovery when a screen gets stuck).
- `maacro/infinity_castle/` — the Infinity Castle controller. It subclasses
  `MacroThread` and only replaces the steps that differ.
- `maacro/modes.py` — the list of modes.
- `maacro/vision/` — reading the screen (OCR, screen detection, cards, numbers).
- `maacro/ui/` — the window.

## Adding a map

1. Zoom out in a match, take a screenshot with the map title at the top.
2. Circle the placement areas in **pure white**; scribble no-go areas in **red**
   (buildings and furniture count as no-go).
3. `python -c "from maacro.maps import create_map; create_map('Map Name', 'shot.png')"`
   (add `walk={"key": "d", "seconds": 3}` if you walk somewhere first).
   For Infinity Castle maps use `maacro.infinity_castle.maps.create_ic_map`.
4. Check the spots land inside your circles, then open a pull request with the
   `maps/*.json` file (screenshots stay local; they're git-ignored).

## Adding a mode

Create a package like `maacro/infinity_castle/`: a settings class (subclass
`MacroConfig`, saved to its own file) and a controller (subclass `MacroThread`,
override the screen handlers that differ). Register it in `maacro/modes.py`; the Main
page, Modes page and Configs page pick it up.

## Rules of thumb

- Never commit personal files: `config.json`, `ic_config.json`, `webhook.json`,
  `logs/`, `runs/`, screenshots (all git-ignored).
- Keep changes small and say what you tested — in the game, or only on screenshots.
- The verification (captcha) code (`_on_join_matchmaking` in `macro.py` and the optional
  `screen-number-typer` helper) is maintained by the project owner; send changes there
  as an issue first.
