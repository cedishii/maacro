"""Story, Infinite and Challenge modes, built on Any Stage (general/).

All three play the match the same tested way as Any Stage (zoom out, place,
upgrade, close popups, Reconnect, your own Actions) and differ in what comes
after the match:

  Story      a win → Next Stage (on through the acts), a defeat → Retry the
             act; or farm one act (always Replay). After the last act (a win
             with no Next Stage button): replay it, or stop.
  Infinite   endless waves until a defeat → Replay. Logs the wave reached and
             the session's best.
  Challenge  Replay if the game offers it, otherwise Return to lobby — then
             your lobby Actions (Actions page) can walk to the next challenge;
             or always Return to lobby; or leave it to you.

None of them clicks Play or matchmaking: you start the first stage (or add
lobby Actions for it). Each has its own settings file and Configs tab.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Signal

from .config import MacroConfig
from .general.config import GeneralConfig
from .general.controller import LOBBY_WORDS, NEXT_WORDS, REPLAY_WORDS, GeneralThread
from .lobby_start import LobbyStarter, StagePicker

ROOT = Path(__file__).resolve().parents[1]
STORY_CONFIG_PATH = ROOT / "story_config.json"
INFINITE_CONFIG_PATH = ROOT / "infinite_config.json"
CHALLENGE_CONFIG_PATH = ROOT / "challenge_config.json"
UNIT_FIELDS = ("placement_order", "unit_names", "upgrade_priority")
LAST_ACT_READS = 2      # after-match checks without a Next Stage button before calling it the last act


def _load(cls, path: Path):
    """The saved settings, or on first use the Summer unit setup with this
    mode's own defaults."""
    if path.exists():
        return MacroConfig.load.__func__(cls, path)
    config = cls()
    summer = MacroConfig.load()
    for name in UNIT_FIELDS:
        setattr(config, name, getattr(summer, name))
    return config


@dataclass
class StoryConfig(GeneralConfig):
    auto_vote_start: bool = True
    # "next": a win → Next Stage, a defeat → Retry; "farm": always Replay.
    story_progress: str = "next"
    # After the last act (a win with no Next Stage): "replay" it or "stop".
    last_act: str = "replay"
    # Start from the lobby by itself: Areas → Play Area → walk in → map → act.
    lobby_start: bool = False
    lobby_walk: str = "w+d 2"
    world: str = ""                 # as in the Select World list, e.g. "Walled City"
    act: str = "1"                  # "1" … "6"
    difficulty: str = "normal"      # "normal" / "hard"

    @classmethod
    def load(cls, path: Path = STORY_CONFIG_PATH) -> "StoryConfig":
        return _load(cls, path)

    def save(self, path: Path = STORY_CONFIG_PATH) -> None:
        MacroConfig.save(self, path)


@dataclass
class InfiniteConfig(GeneralConfig):
    auto_vote_start: bool = True
    # After the defeat that ends a run: "replay" or "none" (leave it to you).
    after_defeat: str = "replay"
    # Start from the lobby by itself: Areas → Play Area → walk in → map → Infinite.
    lobby_start: bool = False
    lobby_walk: str = "w+d 2"
    world: str = ""

    @classmethod
    def load(cls, path: Path = INFINITE_CONFIG_PATH) -> "InfiniteConfig":
        return _load(cls, path)

    def save(self, path: Path = INFINITE_CONFIG_PATH) -> None:
        MacroConfig.save(self, path)


@dataclass
class ChallengeConfig(GeneralConfig):
    auto_vote_start: bool = True
    # "replay_or_lobby": Replay if there's one, else Return to lobby;
    # "lobby": always Return to lobby; "none": leave it to you.
    challenge_after: str = "replay_or_lobby"
    # Start from the lobby by itself: Areas → Challenges → walk into the door.
    lobby_start: bool = False
    lobby_walk: str = "w+d 2"

    @classmethod
    def load(cls, path: Path = CHALLENGE_CONFIG_PATH) -> "ChallengeConfig":
        return _load(cls, path)

    def save(self, path: Path = CHALLENGE_CONFIG_PATH) -> None:
        MacroConfig.save(self, path)


def act_number(map_name: str | None) -> int | None:
    """6 from "Shibuya District Act 6" (None if no act is in the title)."""
    match = re.search(r"\bact\s*([1-9])\b", map_name or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


class StoryThread(StagePicker, GeneralThread):
    INTRO = ("Story mode — plays the act; a win → Next Stage, a defeat → Retry (or farm one act: "
             "Replay). Start the first act yourself, or switch on 'Start from the lobby'.")
    AREA_TILE, LOBBY_KIND = "play area", "story"

    def _stage_choice(self) -> tuple[str, str, str]:
        cfg = self.settings
        act = str(getattr(cfg, "act", "1"))
        difficulty = str(getattr(cfg, "difficulty", "normal")).lower()
        return (str(getattr(cfg, "world", "")), act if act in "123456" and len(act) == 1 else "1",
                difficulty if difficulty in ("normal", "hard") else "normal")
    # The mode asks the Main page to stop it (e.g. the last act is cleared).
    stop_requested = Signal(str)

    def run(self) -> None:
        self._last_result = None
        self._no_next_reads = 0
        self._acts_cleared = 0
        super().run()

    def _progress(self) -> str:
        value = getattr(self.settings, "story_progress", "next")
        return value if value in ("next", "farm") else "next"

    def _after_words(self):
        if self._progress() == "next" and getattr(self, "_last_result", None) == "win":
            return NEXT_WORDS + REPLAY_WORDS
        return REPLAY_WORDS

    def _record_run(self, det) -> None:
        super()._record_run(det)
        if getattr(det, "result", None) == "win":
            self._acts_cleared = getattr(self, "_acts_cleared", 0) + 1
            where = self.detector.tracker.map_name or "the act"
            self.log.emit(f"Story: {where} cleared ({self._acts_cleared} this session).", "Info")
        elif getattr(det, "result", None) == "loss":
            self.log.emit("Story: defeat — retrying the act.", "Warn")

    def _on_after_end(self, hwnd: int) -> None:
        det = self.detector.latest
        if (det is not None and det.screen == "after_end" and self._progress() == "next"
                and getattr(self, "_last_result", None) == "win"
                and getattr(self.settings, "last_act", "replay") == "stop"):
            if self._after_button(det, NEXT_WORDS) is None and self._after_button(det, REPLAY_WORDS):
                self._no_next_reads = getattr(self, "_no_next_reads", 0) + 1
                if self._no_next_reads >= LAST_ACT_READS:
                    if self._cooldown("story_stop", 60):
                        self.log.emit("Story: no Next Stage after a win — that was the last act. "
                                      "Stopping (Configs → Story → After the last act).", "Info")
                        self.stop_requested.emit("the last story act is cleared")
                    return
            else:
                self._no_next_reads = 0
        super()._on_after_end(hwnd)

    def _new_match(self) -> None:
        super()._new_match()
        self._no_next_reads = 0


class InfiniteThread(StagePicker, GeneralThread):
    INTRO = ("Infinite mode — plays until the defeat that ends the run, then Replay. Start the "
             "first run yourself, or switch on 'Start from the lobby'.")
    AREA_TILE, LOBBY_KIND = "play area", "infinite"

    def _stage_choice(self) -> tuple[str, str, str]:
        return str(getattr(self.settings, "world", "")), "infinite", "hard"

    def run(self) -> None:
        self._best_wave = 0
        self._last_result = None
        super().run()

    def _after_words(self):
        return REPLAY_WORDS if getattr(self.settings, "after_defeat", "replay") == "replay" else None

    def _record_run(self, det) -> None:
        wave = self.detector.tracker.wave
        super()._record_run(det)
        if isinstance(wave, int) and wave > 0:
            best = max(getattr(self, "_best_wave", 0), wave)
            note = " — a new best this session!" if wave == best and wave > getattr(self, "_best_wave", 0) else ""
            self._best_wave = best
            self.log.emit(f"Infinite: reached wave {wave} (best this session: {best}){note}", "Info")


class ChallengeThread(LobbyStarter, GeneralThread):
    AREA_TILE, LOBBY_KIND = "challenges", "challenge"

    INTRO = ("Challenge mode — plays the challenge, then Replay if the game offers it, otherwise "
             "Return to lobby (lobby Actions can walk you to the next one).")

    def _after_words(self):
        value = getattr(self.settings, "challenge_after", "replay_or_lobby")
        if value == "lobby":
            return LOBBY_WORDS
        if value == "none":
            return None
        return REPLAY_WORDS + LOBBY_WORDS

    def _on_lobby(self, hwnd: int) -> None:
        if self._lobby_ready():
            LobbyStarter._on_lobby(self, hwnd)
            return
        if getattr(self, "_actions", None) is not None and any(
                a.screen == "lobby" for a in self._actions.actions):
            self._wait("in the lobby — running your lobby Actions to the next challenge")
        else:
            self._wait("in the lobby — join the next challenge (or add lobby Actions to do it)")
