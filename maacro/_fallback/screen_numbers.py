"""Stand-in for the optional `screen_numbers` helper (github.com/cedishii/screen-number-typer).

Only used when the real package isn't installed (e.g. pip couldn't fetch it
because Git isn't installed). Nothing is read: the player types the
verification number and MAACRO presses Submit, as described in FLOW.md.
"""


def read_number(image=None, **_kwargs) -> str:
    return ""


def type_text(text, click_at=None, **_kwargs) -> None:
    return None
