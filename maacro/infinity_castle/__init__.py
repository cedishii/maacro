"""Infinity Castle mode (the game calls it "Infinity Mansion"): play a room,
press Next Room (or Retry after a defeat), repeat until stopped.

Separate from Summer Event: it has its own controller, settings and map
zones, and reuses Summer's placing/upgrading by subclassing MacroThread
(macro.py itself is never changed for this mode).
"""
