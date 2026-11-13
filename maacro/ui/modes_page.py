"""The Modes page: pick which game mode MAACRO plays, and its role (Solo /
Leader or Party Member). Same choices as the Mode and Role boxes on the Main
page (they stay in sync)."""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

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
    "general": ("For anything else (story, raids, portals…). Start the match yourself; MAACRO "
                "zooms out, places your units, upgrades them to Max and waits. It never clicks "
                "Play, Next, Replay or Return to lobby — you do. Voting Yes and picking cards "
                "are off unless you switch them on in its Configs tab."),
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
        layout = QVBoxLayout(self)
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
