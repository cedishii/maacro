"""Sky Portal, as a party member: someone else hosts the portal.

MAACRO waits through the lobby and the vote (it never votes: the vote ends
when the party votes or its timer runs out), then zooms out, places the units
and upgrades them, and waits for the next match. Like General mode it never
clicks Play, Next, Replay or Return to lobby, and it uses the same per-unit
map zones (maps/general/, e.g. from the Recorder page).
"""
from __future__ import annotations

from ..general.controller import GeneralThread
from .config import SkyPortalConfig


class SkyPortalThread(GeneralThread):
    INTRO = ("Sky Portal (party member) — waits for the vote to finish, then places units, "
             "upgrades them and waits. Never votes or clicks Play, Next, Replay or Return to lobby.")

    def __init__(self, capture, detector, settings: SkyPortalConfig | None = None, parent=None):
        super().__init__(capture, detector, settings or SkyPortalConfig(), parent)

    def run(self) -> None:
        self.settings.auto_vote_start = False
        super().run()

    def _on_vote_start(self, hwnd: int) -> None:
        self._wait("vote start (the party votes, or the timer runs out)")

    def _on_lobby(self, hwnd: int) -> None:
        self._wait("in the lobby (the party leader starts the portal)")
