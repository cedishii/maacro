"""The Modes page: pick which game mode MAACRO plays, and its role (Solo /
Leader or Party Member). Same choices as the Mode and Role boxes on the Main
page (they stay in sync)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from ..modes import MODES
from ..party import BEHAVIORS

DESCRIPTIONS = {
    "summer": ("Start it in the lobby. Each run: Play → walk to the ring → Find Match → "
               "(you type the captcha, MAACRO presses Submit) → vote Yes → place, upgrade and "
               "pick cards → Next → Return to lobby → again."),
    "infinity_castle": ("Start it inside Infinity Mansion. Each room: vote Yes → place (damage "
                        "units on the circled path) and upgrade → Next → Next Room, or Retry "
                        "after a defeat → again, forever. Never goes back to the lobby; no "
                        "matchmaking, captcha or cards."),
    "story": ("Start the first act yourself. Each act: vote Yes → place and upgrade → a win → "
              "Next Stage, a defeat → Retry the act. Or farm one act (always Replay). After the last "
              "act: replay it, or stop. Never clicks Play or Return to lobby."),
    "infinite": ("Start an Infinite run yourself. MAACRO places and upgrades as long as the waves "
                 "keep coming; after the defeat that ends the run it presses Replay and goes again. "
                 "The log keeps the wave reached and the session's best."),
    "challenge": ("Start a challenge yourself. MAACRO plays it, then presses Replay if the game "
                  "offers one, otherwise Return to lobby. In the lobby, your lobby Actions (Actions "
                  "page, Challenge) can walk to the next challenge; otherwise it waits for you."),
    "misty_village": ("Goes to Misty Village by itself (Play → Misty Village → walk right → stages), "
                      "plays the Night stage whenever it's open (20 waves), otherwise Day (15 waves), "
                      "and Replays; back to the lobby to switch when night opens or ends. Or tick "
                      "'Day stages only' on its Configs tab."),
    "general": ("For anything else (legend stages, raids, portals, someone else's lobby…). Start "
                "the match yourself; MAACRO zooms out, places your units and upgrades them. After "
                "the match it waits, or presses Replay / Next Stage if you set that on its Configs "
                "tab. Never clicks Play or Return to lobby."),
    "sky_portal": ("Join the party leader's Sky Portal. MAACRO waits in the lobby and through "
                   "the vote (votes Yes — the vote is everyone's), zooms out, places every unit on its spot, maxes the farm units "
                   "(Bulby, C.E.O.) first, then upgrades the damage units (Elyssia, Fishi) as "
                   "fast as money allows. Never clicks Play, Next, Replay or Return to lobby."),
}

ROLE_DESCRIPTIONS = {
    "solo": ("MAACRO does everything: plays the match and decides what's next (Play, walking "
             "to the ring, Find Match, Return to lobby, Next Room / Retry)."),
    "party": ("You're in someone else's party. The leader moves around the lobby, picks the "
              "portal and presses Return to lobby / Retry / Next Room. MAACRO waits for each "
              "match to load, then plays it: votes Yes, places and upgrades units, picks "
              "Summer cards, closes popups, presses Next on its own results and Reconnect if "
              "disconnected. It never clicks the leader's choices."),
}


class ModesPage(QWidget):
    def __init__(self, main_page, parent=None):
        super().__init__(parent)
        self.main_page = main_page
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(widgetResizable=True)       # seven modes: scroll, don't squash
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Modes", objectName="PageTitle"))
        layout.addWidget(QLabel("Pick what MAACRO plays, then press Start (F1). Each mode has its "
                                "own settings tab on the Configs page.", objectName="Muted"))
        self.cards: dict[str, tuple[QFrame, QPushButton, QLabel]] = {}
        for mode in MODES:
            card = QFrame(objectName="Card")
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 12, 16, 14)
            box.setSpacing(6)
            top = QHBoxLayout()
            top.addWidget(QLabel(mode.label, objectName="PanelTitle"))
            badge = QLabel("", objectName="Muted")
            top.addWidget(badge)
            top.addStretch()
            button = QPushButton("Use this mode", objectName="StartButton")
            button.clicked.connect(lambda _=False, key=mode.key: self._choose(key))
            top.addWidget(button)
            box.addLayout(top)
            text = QLabel(DESCRIPTIONS.get(mode.key, ""), objectName="Muted")
            text.setWordWrap(True)
            box.addWidget(text)
            layout.addWidget(card)
            self.cards[mode.key] = (card, button, badge)
        layout.addSpacing(8)
        layout.addWidget(QLabel("Role", objectName="PageTitle"))
        layout.addWidget(QLabel("Works with every mode above.", objectName="Muted"))
        self.role_cards: dict[str, tuple[QFrame, QPushButton, QLabel]] = {}
        row = QHBoxLayout()
        for key, label in BEHAVIORS.items():
            card = QFrame(objectName="Card")
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 12, 16, 14)
            box.setSpacing(6)
            top = QHBoxLayout()
            top.addWidget(QLabel(label, objectName="PanelTitle"))
            badge = QLabel("", objectName="Muted")
            top.addWidget(badge)
            top.addStretch()
            button = QPushButton("Use this role", objectName="StartButton")
            button.clicked.connect(lambda _=False, k=key: self.main_page.set_behavior(k))
            top.addWidget(button)
            box.addLayout(top)
            text = QLabel(ROLE_DESCRIPTIONS.get(key, ""), objectName="Muted")
            text.setWordWrap(True)
            box.addWidget(text)
            box.addStretch()
            row.addWidget(card, 1)
            self.role_cards[key] = (card, button, badge)
        layout.addLayout(row)
        self.note = QLabel("", objectName="Muted")
        layout.addWidget(self.note)
        layout.addStretch()
        main_page.mode_changed.connect(self.refresh)
        main_page.behavior_changed.connect(self.refresh)
        main_page.stats.changed.connect(self.refresh)
        self.refresh()

    def _choose(self, key: str) -> None:
        self.main_page.set_mode(key)

    def refresh(self, *_) -> None:
        running = self.main_page.stats.running
        for key, (card, button, badge) in self.cards.items():
            selected = key == self.main_page.mode
            badge.setText("● selected" if selected else "")
            card.setStyleSheet("#Card { border-color: #8b5cf6; }" if selected else "")
            button.setVisible(not selected)
            button.setEnabled(not running)
        for key, (card, button, badge) in self.role_cards.items():
            selected = key == self.main_page.behavior
            badge.setText("● selected" if selected else "")
            card.setStyleSheet("#Card { border-color: #8b5cf6; }" if selected else "")
            button.setVisible(not selected)
            button.setEnabled(not running)
        self.note.setText("Stop the macro (F3) to switch modes or roles." if running else "")
