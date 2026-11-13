"""The Configs page: one settings tab per mode, each with a card per hotbar
unit (enabled, name, placements, placement and upgrade priority) plus the
mode's switches.

The cards are another way to edit the same settings as before: on Save they
become the placement order ("6 5 5 5 1 1") and upgrade priority ("6 5 1")
the macro already uses, so nothing about how a mode plays changes.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ..config import VALID_KEYS, MacroConfig
from ..infinity_castle.config import InfinityConfig
from . import theme
from .widgets import panel


def cards_from_config(config: MacroConfig) -> dict[str, dict]:
    """Per-key card values from the placement order and upgrade priority."""
    order = list(config.placement_order)
    first_seen = list(dict.fromkeys(order))
    upgrades = list(config.upgrade_priority)
    cards = {}
    for key in VALID_KEYS:
        count = order.count(key)
        cards[key] = {
            "enabled": count > 0,
            "name": config.unit_names.get(key, ""),
            "placements": max(1, count),
            "place_priority": first_seen.index(key) + 1 if key in first_seen else len(first_seen) + 1,
            "upgrade_priority": upgrades.index(key) + 1 if key in upgrades else len(upgrades) + 1,
        }
    return cards


def config_lists(cards: dict[str, dict]) -> tuple[list[str], list[str]]:
    """(placement order, upgrade priority) from the cards. Lower priority
    number goes first; ties keep key order. Disabled units are left out."""
    enabled = [k for k in VALID_KEYS if cards[k]["enabled"]]
    by_place = sorted(enabled, key=lambda k: (cards[k]["place_priority"], k))
    order = [k for k in by_place for _ in range(cards[k]["placements"])]
    upgrades = sorted(enabled, key=lambda k: (cards[k]["upgrade_priority"], k))
    return order, upgrades


class UnitCard(QFrame):
    """Settings for one hotbar slot."""

    def __init__(self, key: str, path_option: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.key = key
        grid = QGridLayout(self)
        grid.setContentsMargins(10, 8, 10, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        grid.addWidget(QLabel(f"Unit {key}", objectName="PanelTitle"), 0, 0)
        self.enabled = QCheckBox("Enabled")
        grid.addWidget(self.enabled, 0, 1)
        self.name = QLineEdit(placeholderText="Name in the unit manager")
        self.name.setToolTip("As shown in the unit manager (used for upgrade priority).")
        grid.addWidget(self.name, 1, 0, 1, 2)
        grid.addWidget(QLabel("Placements", objectName="Muted"), 2, 0)
        grid.addWidget(QLabel("Placement priority", objectName="Muted"), 2, 1)
        self.placements = self._spin(1, 10, "How many of this unit to place.")
        self.place_priority = self._spin(1, 6, "1 = placed first.")
        grid.addWidget(self.placements, 3, 0)
        grid.addWidget(self.place_priority, 3, 1)
        grid.addWidget(QLabel("Upgrade priority", objectName="Muted"), 4, 0)
        self.upgrade_priority = self._spin(1, 6, "1 = upgraded first.")
        grid.addWidget(self.upgrade_priority, 5, 0)
        self.path = None
        if path_option:
            self.path = QCheckBox("Damage unit (path)")
            self.path.setToolTip("Placed in the circled path zones of the map; "
                                 "other units are kept out of them.")
            grid.addWidget(self.path, 5, 1)
        self.enabled.toggled.connect(self._enable)

    @staticmethod
    def _spin(low: int, high: int, tip: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setToolTip(tip)
        return spin

    def _enable(self, on: bool) -> None:
        for widget in (self.placements, self.place_priority, self.upgrade_priority, self.path):
            if widget is not None:
                widget.setEnabled(on)

    def set_values(self, values: dict, on_path: bool) -> None:
        self.enabled.setChecked(values["enabled"])
        self.name.setText(values["name"])
        self.placements.setValue(values["placements"])
        self.place_priority.setValue(min(6, values["place_priority"]))
        self.upgrade_priority.setValue(min(6, values["upgrade_priority"]))
        if self.path is not None:
            self.path.setChecked(on_path)
        self._enable(values["enabled"])

    def values(self) -> dict:
        return {"enabled": self.enabled.isChecked(), "name": self.name.text().strip(),
                "placements": self.placements.value(),
                "place_priority": self.place_priority.value(),
                "upgrade_priority": self.upgrade_priority.value()}


class ModeSettings(QWidget):
    """One mode's tab: unit cards and switches, saved to that mode's file."""

    def __init__(self, config_class: type, switches: dict[str, str], parent=None):
        super().__init__(parent)
        self.config_class = config_class
        self.ic = issubclass(config_class, InfinityConfig)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.cards = {}
        for index, key in enumerate(VALID_KEYS):
            card = UnitCard(key, path_option=self.ic)
            grid.addWidget(card, index // 2, index % 2)
            self.cards[key] = card
        layout.addLayout(grid)

        box, box_layout = panel("Automation")
        self.switches = {name: QCheckBox(text) for name, text in switches.items()}
        for widget in self.switches.values():
            box_layout.addWidget(widget)
        layout.addWidget(box)

        actions = QHBoxLayout()
        save = QPushButton("Save", objectName="StartButton")
        save.clicked.connect(self.save)
        reset = QPushButton("Defaults")
        reset.clicked.connect(lambda: self.show_config(self.config_class()))
        actions.addWidget(save)
        actions.addWidget(reset)
        self.message = QLabel("")
        actions.addWidget(self.message)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addStretch()
        self.show_config(config_class.load())

    def show_config(self, config: MacroConfig) -> None:
        path = set(getattr(config, "path_units", []))
        for key, values in cards_from_config(config).items():
            self.cards[key].set_values(values, key in path)
        for name, box in self.switches.items():
            box.setChecked(bool(getattr(config, name)))

    def save(self) -> None:
        cards = {key: card.values() for key, card in self.cards.items()}
        order, upgrades = config_lists(cards)
        if not order:
            self._message("Enable at least one unit.", theme.LOSS)
            return
        config = self.config_class.load()
        config.placement_order, config.upgrade_priority = order, upgrades
        config.unit_names = {key: cards[key]["name"] for key in VALID_KEYS}
        if self.ic:
            config.path_units = [k for k, card in self.cards.items()
                                 if card.path is not None and card.path.isChecked() and cards[k]["enabled"]]
        for name, box in self.switches.items():
            setattr(config, name, box.isChecked())
        try:
            config.save()
        except OSError as exc:
            self._message(f"Couldn't save: {exc}", theme.LOSS)
            return
        self._message(f"Saved. Placement order: {' '.join(order)} · upgrades: {' '.join(upgrades)}",
                      theme.WIN)

    def _message(self, text: str, color: str) -> None:
        self.message.setStyleSheet(f"color: {color};")
        self.message.setText(text)


class ConfigsPage(QWidget):
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
        layout.setSpacing(12)
        layout.addWidget(QLabel("Configs", objectName="PageTitle"))
        layout.addWidget(QLabel("Each mode has its own settings. Changes apply the next time "
                                "you press Start.", objectName="Muted"))
        tabs = QTabWidget()
        tabs.addTab(ModeSettings(MacroConfig, {
            "place_units": "Place units",
            "upgrade_units": "Upgrade units to Max (unit manager, F)",
            "auto_card_pick": "Pick cards (green first, else most votes)",
            "auto_vote_start": "Vote Yes on 'Vote start'",
        }), "Summer Event")
        tabs.addTab(ModeSettings(InfinityConfig, {
            "place_units": "Place units",
            "upgrade_units": "Upgrade units to Max (unit manager, F)",
            "auto_vote_start": "Vote Yes on 'Vote start'",
            "fast_economy": "Fast economy: place and upgrade twice as often (money comes fast)",
        }), "Infinity Castle")
        layout.addWidget(tabs)
