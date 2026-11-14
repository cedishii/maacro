"""The Actions page: your own "on this screen, click/press this" rules for
General mode (see maacro/general/actions.py)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..general.actions import ACTION_SCREENS, KEYS, KINDS, Action, actions_from_config
from ..general.config import GeneralConfig
from . import theme

INTRO = (
    "General mode places units, upgrades them and waits — it never clicks Next, Replay, "
    "Return to lobby or Play by itself. Add actions here to have it do those (or anything "
    "else) for you: when a screen is up, click some text on it or press a key.\n"
    "Text is matched like the screen reading on the Detection page shows it (\"Replay\", "
    "\"Next\", \"Return to lobby\"). Matchmaking and verification screens can't be used. "
    "Changes apply the next time you press Start."
)
EXAMPLES = [
    Action("end", "click", "Replay", 2.0),
    Action("after_end", "click", "Replay", 2.0),
]


def _spin(value: float, high: float, tip: str) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0.0, high)
    spin.setDecimals(1)
    spin.setSingleStep(0.5)
    spin.setSuffix(" s")
    spin.setValue(value)
    spin.setToolTip(tip)
    return spin


class ActionRow(QFrame):
    """One action: on [screen], after [wait], [click text / press key] [target], repeat."""

    def __init__(self, action: Action, on_remove, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        grid = QGridLayout(self)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(8)
        self.enabled = QCheckBox("On")
        self.enabled.setChecked(action.enabled)
        self.screen = QComboBox()
        for key, label in ACTION_SCREENS.items():
            self.screen.addItem(label, key)
        self.screen.setCurrentIndex(max(0, self.screen.findData(action.screen)))
        self.wait = _spin(action.wait, 600, "How long the screen must be up first.")
        self.kind = QComboBox()
        for key, label in KINDS.items():
            self.kind.addItem(label, key)
        self.kind.setCurrentIndex(max(0, self.kind.findData(action.kind)))
        self.text = QLineEdit(placeholderText="Text on screen, e.g. Replay")
        self.key = QComboBox()
        for key in KEYS:
            self.key.addItem(key.upper(), key)
        if action.kind == "key":
            self.key.setCurrentIndex(max(0, self.key.findData(action.target)))
        else:
            self.text.setText(action.target)
        self.repeat = _spin(action.repeat, 600, "Do it again this often while the screen stays "
                                                "up (0 = once each time it shows).")
        remove = QPushButton("Remove")
        remove.clicked.connect(lambda: on_remove(self))

        for column, (label, widget) in enumerate([
                ("", self.enabled), ("When this screen is up", self.screen), ("for", self.wait),
                ("do", self.kind), ("what", self.text), ("again every (0 = once)", self.repeat),
                ("", remove)]):
            grid.addWidget(QLabel(label, objectName="Muted"), 0, column)
            grid.addWidget(widget, 1, column)
        grid.addWidget(self.key, 1, 4)
        grid.setColumnStretch(4, 1)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self._kind_changed()

    def _kind_changed(self) -> None:
        key = self.kind.currentData() == "key"
        self.key.setVisible(key)
        self.text.setVisible(not key)

    def action(self) -> Action:
        kind = self.kind.currentData()
        target = self.key.currentData() if kind == "key" else self.text.text().strip()
        return Action(self.screen.currentData(), kind, target, self.wait.value(),
                      self.repeat.value(), self.enabled.isChecked())


class ActionsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(widgetResizable=True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(QLabel("Actions", objectName="PageTitle"))
        intro = QLabel(INTRO, objectName="Muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(8)
        layout.addLayout(self.rows_layout)
        self.empty = QLabel("No actions yet — General mode only places, upgrades and waits.",
                            objectName="Muted")
        layout.addWidget(self.empty)

        buttons = QHBoxLayout()
        add = QPushButton("Add action")
        add.clicked.connect(lambda: self._add(Action()))
        example = QPushButton("Add example: auto Replay")
        example.setToolTip("Match over → click 'Replay' after 2 s (and the same after the results).")
        example.clicked.connect(lambda: [self._add(a) for a in EXAMPLES])
        save = QPushButton("Save", objectName="StartButton")
        save.clicked.connect(self.save)
        for widget in (add, example, save):
            buttons.addWidget(widget)
        self.message = QLabel("")
        buttons.addWidget(self.message)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()

        self.rows: list[ActionRow] = []
        for action in actions_from_config(GeneralConfig.load().actions):
            self._add(action)

    def _add(self, action: Action) -> None:
        row = ActionRow(Action(**vars(action)), self._remove)
        self.rows.append(row)
        self.rows_layout.addWidget(row)
        self.empty.setVisible(False)

    def _remove(self, row: ActionRow) -> None:
        self.rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self.empty.setVisible(not self.rows)

    def save(self) -> None:
        actions = [row.action() for row in self.rows]
        problems = [f"#{i + 1}: {a.problem()}" for i, a in enumerate(actions) if a.enabled and a.problem()]
        if problems:
            self._message("Not saved — " + "; ".join(problems), theme.LOSS)
            return
        config = GeneralConfig.load()
        config.actions = [vars(a) for a in actions]
        try:
            config.save()
        except OSError as exc:
            self._message(f"Couldn't save: {exc}", theme.LOSS)
            return
        on = sum(a.enabled for a in actions)
        self._message(f"Saved {len(actions)} action(s) ({on} on) for General mode.", theme.WIN)

    def _message(self, text: str, color: str) -> None:
        self.message.setStyleSheet(f"color: {color};")
        self.message.setText(text)
