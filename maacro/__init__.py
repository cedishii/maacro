"""MAACRO - an Anime Adventures macro that watches the Roblox screen."""
__version__ = "0.2.0"

# The fast fuzzy text matching (same answers as screens.fuzzy_in), loaded
# first so every module that imports fuzzy_in gets it.
from .vision import fast_text as _fast_text  # noqa: E402,F401
