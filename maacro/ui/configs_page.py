"""The Configs page: placement order, unit names, upgrade priority and switches."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from ..config import VALID_KEYS, MacroConfig, parse_keys
from . import theme
from .widgets import panel


class ConfigsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Configs", objectName="PageTitle"))
        layout.addWidget(QLabel("Changes apply the next time you press Start.", objectName="Muted"))

        row = QHBoxLayout()
        row.setSpacing(12)

        box, box_layout = panel("Placing units")
        form = QFormLayout()
        self.order = QLineEdit()
        self.order.setPlaceholderText("6 5 5 5 1 1")
        self.order.setToolTip("Hotbar keys in the order to place them, one per unit.")
        form.addRow("Placement order", self.order)
        self.priority = QLineEdit()
        self.priority.setPlaceholderText("6 5 1")
        self.priority.setToolTip("Upgrade these keys' units first, in this order.")
        form.addRow("Upgrade priority", self.priority)
        box_layout.addLayout(form)
        box_layout.addWidget(QLabel("Unit name on each key (as shown in the unit manager):",
                                    objectName="Muted"))
        names = QFormLayout()
        self.names: dict[str, QLineEdit] = {}
        for key in VALID_KEYS:
            self.names[key] = QLineEdit()
            names.addRow(f"Key {key}", self.names[key])
        box_layout.addLayout(names)
        box_layout.addStretch()
        row.addWidget(box, 1)

        box, box_layout = panel("Automation")
        self.switches = {
            "place_units": QCheckBox("Place units"),
            "upgrade_units": QCheckBox("Upgrade units to Max (unit manager, F)"),
            "auto_card_pick": QCheckBox("Pick cards (green first, else most votes)"),
            "auto_vote_start": QCheckBox("Vote Yes on 'Vote start'"),
        }
        for box_widget in self.switches.values():
            box_layout.addWidget(box_widget)
        box_layout.addStretch()
        row.addWidget(box, 1)
        layout.addLayout(row, 1)

        actions = QHBoxLayout()
        save = QPushButton("Save", objectName="StartButton")
        save.clicked.connect(self.save)
        reset = QPushButton("Defaults")
        reset.clicked.connect(lambda: self._show(MacroConfig()))
        actions.addWidget(save)
        actions.addWidget(reset)
        self.message = QLabel("")
        actions.addWidget(self.message)
        actions.addStretch()
        layout.addLayout(actions)

        self._show(MacroConfig.load())

    def _show(self, config: MacroConfig) -> None:
        self.order.setText(" ".join(config.placement_order))
        self.priority.setText(" ".join(config.upgrade_priority))
        for key, field in self.names.items():
            field.setText(config.unit_names.get(key, ""))
        for name, box in self.switches.items():
            box.setChecked(bool(getattr(config, name)))

    def save(self) -> None:
        config = MacroConfig.load()
        try:
            config.placement_order = parse_keys(self.order.text())
            config.upgrade_priority = parse_keys(self.priority.text())
        except ValueError as exc:
            self._message(str(exc), theme.LOSS)
            return
        config.unit_names = {key: field.text().strip() for key, field in self.names.items()}
        for name, box in self.switches.items():
            setattr(config, name, box.isChecked())
        try:
            config.save()
        except OSError as exc:
            self._message(f"Couldn't save: {exc}", theme.LOSS)
            return
        self._message("Saved.", theme.WIN)

    def _message(self, text: str, color: str) -> None:
        self.message.setStyleSheet(f"color: {color};")
        self.message.setText(text)
