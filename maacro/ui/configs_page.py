"""The Configs page: one settings tab per mode, each with a card per hotbar
unit (enabled, name, placements, placement and upgrade priority) plus the
mode's switches.

The cards are another way to edit the same settings as before: on Save they
become the placement order ("6 5 5 5 1 1") and upgrade priority ("6 5 1")
the macro already uses, so nothing about how a mode plays changes.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QRadioButton, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ..config import VALID_KEYS, MacroConfig
from ..general.config import GeneralConfig
from ..infinity_castle.config import InfinityConfig
from ..summer_config import SummerConfig
from ..sky_portal.config import SkyPortalConfig
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
            "placements": min(MAX_PLACEMENTS, max(1, count)),
            "place_priority": first_seen.index(key) + 1 if key in first_seen else len(first_seen) + 1,
            "upgrade_priority": upgrades.index(key) + 1 if key in upgrades else len(upgrades) + 1,
            # Placed but left out of the upgrade priority = place-only.
            "upgrade": key in upgrades or count == 0,
        }
    return cards


def config_lists(cards: dict[str, dict]) -> tuple[list[str], list[str]]:
    """(placement order, upgrade priority) from the cards. Lower priority
    number goes first; ties keep key order. Disabled units are left out, and
    place-only units ("Upgrade" unticked) are left out of the upgrades."""
    enabled = [k for k in VALID_KEYS if cards[k]["enabled"]]
    by_place = sorted(enabled, key=lambda k: (cards[k]["place_priority"], k))
    order = [k for k in by_place for _ in range(cards[k]["placements"])]
    upgrades = sorted((k for k in enabled if cards[k].get("upgrade", True)),
                      key=lambda k: (cards[k]["upgrade_priority"], k))
    return order, upgrades


# "Max" placements: this many copies in the placement order. MacroThread
# never places more than the hotbar counter allows (e.g. 3 for 0/3), so
# Max simply fills the counter, whatever it is.
MAX_PLACEMENTS = 10


def order_text(order: list[str]) -> str:
    """'6 5×3 1×2 4×Max' for the saved message."""
    parts = []
    for key in dict.fromkeys(order):
        n = order.count(key)
        parts.append(key if n == 1 else f"{key}×{'Max' if n >= MAX_PLACEMENTS else n}")
    return " ".join(parts)


class PlacementSpin(QSpinBox):
    """1–9, then "Max" (as many as the game's counter allows)."""

    def __init__(self):
        super().__init__()
        self.setRange(1, MAX_PLACEMENTS)
        self.setToolTip("How many of this unit to place. Max = as many as the game "
                        "allows (the 0/3 counter on its hotbar slot).")

    def textFromValue(self, value: int) -> str:
        return "Max" if value >= MAX_PLACEMENTS else str(value)

    def valueFromText(self, text: str) -> int:
        return MAX_PLACEMENTS if text.strip().lower().startswith("m") else int(text or 1)

    def validate(self, text, pos):
        from PySide6.QtGui import QValidator
        t = text.strip().lower()
        if t == "" or "max".startswith(t) or (t.isdigit() and 1 <= int(t) <= MAX_PLACEMENTS):
            return QValidator.Acceptable if t in ("max",) or t.isdigit() else QValidator.Intermediate, text, pos
        return QValidator.Invalid, text, pos


class UnitCard(QFrame):
    """Settings for one hotbar slot."""

    def __init__(self, key: str, path_option: bool, farm_option: bool = False, cap_option: bool = False,
                 parent=None):
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
        self.placements = PlacementSpin()
        self.place_priority = self._spin(1, 6, "1 = placed first.")
        grid.addWidget(self.placements, 3, 0)
        grid.addWidget(self.place_priority, 3, 1)
        self.upgrade = QCheckBox("Upgrade · priority")
        self.upgrade.setToolTip("Untick to place this unit but never upgrade it "
                                "(needs its name filled in).")
        grid.addWidget(self.upgrade, 4, 0)
        self.upgrade_priority = self._spin(1, 6, "1 = upgraded first.")
        grid.addWidget(self.upgrade_priority, 5, 0)
        self.path = None
        if path_option:
            self.path = QCheckBox("Damage unit (path)")
            self.path.setToolTip("Placed in the circled path zones of the map; "
                                 "other units are kept out of them.")
            grid.addWidget(self.path, 5, 1)
        self.farm = None
        if farm_option:
            self.farm = QCheckBox("Farm unit (maxed first)")
            self.farm.setToolTip("Farm units are upgraded to Max before any other unit "
                                 "(needs the name filled in).")
            grid.addWidget(self.farm, 5, 1)
        self.cap = None
        if cap_option:
            grid.addWidget(QLabel("Upgrade up to", objectName="Muted"), 6, 0)
            self.cap = QSpinBox()
            self.cap.setRange(0, 12)
            self.cap.setSpecialValueText("Max")
            self.cap.setToolTip("Stop upgrading this unit after this many upgrades (the segments "
                                "on its bar in the Unit Overview). Max = all the way.")
            grid.addWidget(self.cap, 7, 0)
        self.enabled.toggled.connect(self._enable)
        self.upgrade.toggled.connect(lambda _: self._enable(self.enabled.isChecked()))

    @staticmethod
    def _spin(low: int, high: int, tip: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setToolTip(tip)
        return spin

    def _enable(self, on: bool) -> None:
        for widget in (self.placements, self.place_priority, self.upgrade, self.path, self.farm, self.cap):
            if widget is not None:
                widget.setEnabled(on)
        self.upgrade_priority.setEnabled(on and self.upgrade.isChecked())

    def set_values(self, values: dict, on_path: bool, farm: bool = False, cap: int = 0) -> None:
        self.enabled.setChecked(values["enabled"])
        self.name.setText(values["name"])
        self.placements.setValue(values["placements"])
        self.place_priority.setValue(min(6, values["place_priority"]))
        self.upgrade_priority.setValue(min(6, values["upgrade_priority"]))
        self.upgrade.setChecked(values.get("upgrade", True))
        if self.path is not None:
            self.path.setChecked(on_path)
        if self.farm is not None:
            self.farm.setChecked(farm)
        if self.cap is not None:
            self.cap.setValue(int(cap or 0))
        self._enable(values["enabled"])

    def values(self) -> dict:
        return {"enabled": self.enabled.isChecked(), "name": self.name.text().strip(),
                "placements": self.placements.value(),
                "place_priority": self.place_priority.value(),
                "upgrade_priority": self.upgrade_priority.value(),
                "upgrade": self.upgrade.isChecked()}


class ModeSettings(QWidget):
    """One mode's tab: unit cards and switches, saved to that mode's file."""

    def __init__(self, config_class: type, switches: dict[str, str],
                 choices: dict[str, tuple[str, list[tuple[str, str]]]] | None = None, parent=None):
        super().__init__(parent)
        self.config_class = config_class
        self.ic = issubclass(config_class, InfinityConfig)
        self.farm = "farm_units" in getattr(config_class, "__dataclass_fields__", {})
        self.caps = "upgrade_caps" in getattr(config_class, "__dataclass_fields__", {})
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.cards = {}
        for index, key in enumerate(VALID_KEYS):
            card = UnitCard(key, path_option=self.ic, farm_option=self.farm, cap_option=self.caps)
            grid.addWidget(card, index // 2, index % 2)
            self.cards[key] = card
        layout.addLayout(grid)

        box, box_layout = panel("Automation")
        self.switches = {name: QCheckBox(text) for name, text in switches.items()}
        for widget in self.switches.values():
            box_layout.addWidget(widget)
        # Pick-one settings: {field: (title, [(value, label), ...])}
        self.choices: dict[str, dict[str, QRadioButton]] = {}
        for name, (title, options) in (choices or {}).items():
            box_layout.addWidget(QLabel(title, objectName="Muted"))
            group = QButtonGroup(self)
            self.choices[name] = {}
            for value, label in options:
                button = QRadioButton(label)
                group.addButton(button)
                box_layout.addWidget(button)
                self.choices[name][value] = button
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
        farm = set(getattr(config, "farm_units", []))
        caps = getattr(config, "upgrade_caps", {}) or {}
        for key, values in cards_from_config(config).items():
            self.cards[key].set_values(values, key in path, key in farm, caps.get(key, 0))
        for name, box in self.switches.items():
            box.setChecked(bool(getattr(config, name)))
        for name, buttons in self.choices.items():
            current = getattr(config, name, None)
            (buttons.get(current) or next(iter(buttons.values()))).setChecked(True)

    def showEvent(self, event) -> None:
        # Pick-one settings can also change elsewhere (Cards on the Main page):
        # show the saved choice. Unsaved unit-card edits are left alone.
        super().showEvent(event)
        if self.choices:
            config = self.config_class.load()
            for name, buttons in self.choices.items():
                current = getattr(config, name, None)
                if current in buttons:
                    buttons[current].setChecked(True)

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
        if self.caps:
            config.upgrade_caps = {k: card.cap.value() for k, card in self.cards.items()
                                   if card.cap is not None and card.cap.value() > 0}
        if self.farm:
            config.farm_units = [k for k, card in self.cards.items()
                                 if card.farm is not None and card.farm.isChecked() and cards[k]["enabled"]]
        for name, box in self.switches.items():
            setattr(config, name, box.isChecked())
        for name, buttons in self.choices.items():
            setattr(config, name, next((v for v, b in buttons.items() if b.isChecked()), next(iter(buttons))))
        try:
            config.save()
        except OSError as exc:
            self._message(f"Couldn't save: {exc}", theme.LOSS)
            return
        place_only = [k for k in dict.fromkeys(order) if k not in upgrades]
        self._message(f"Saved. Placement order: {order_text(order)} · upgrades: {' '.join(upgrades) or 'none'}"
                      + (f" · place only: {' '.join(place_only)}" if place_only else ""), theme.WIN)

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
        tabs.addTab(ModeSettings(SummerConfig, {
            "place_units": "Place units",
            "upgrade_units": "Upgrade units to Max (unit manager, F)",
            "auto_card_pick": "Pick cards",
            "auto_vote_start": "Vote Yes on 'Vote start'",
        }, {"card_strategy": ("Card picks", [
            ("easy", "Easy — green cards first; red only for + Secret Drop Rate (and the "
                     "Star Golem card during Starfall)"),
            ("hard", "Hard — red cards as much as possible (+ Secret Drop Rate ones first, then "
                     "the most SummerPearls, the mildest danger among equals)"),
        ])}), "Summer Event")
        tabs.addTab(ModeSettings(InfinityConfig, {
            "place_units": "Place units",
            "upgrade_units": "Upgrade units to Max (unit manager, F)",
            "auto_vote_start": "Vote Yes on 'Vote start'",
            "fast_economy": "Fast economy: place and upgrade twice as often (money comes fast)",
        }), "Infinity Castle")
        tabs.addTab(ModeSettings(GeneralConfig, {
            "place_units": "Place units",
            "upgrade_units": "Upgrade units to Max (unit manager, F)",
            "use_map_zones": "Use saved map zones (and the walk some maps need); off = automatic spots, never moves",
            "auto_vote_start": "Vote Yes on 'Vote start' (off = wait)",
            "auto_card_pick": "Pick cards if a card vote shows up (off = wait)",
        }), "General")
        tabs.addTab(ModeSettings(SkyPortalConfig, {
            "place_units": "Place units",
            "upgrade_units": "Upgrade units to Max (unit manager, F)",
            "use_map_zones": "Use the Sky Portal spots (maps/sky_portal); off = automatic spots",
            "auto_vote_start": "Vote Yes on 'Vote start'",
            "auto_card_pick": "Pick cards if a card vote shows up (off = wait)",
        }), "Sky Portal")
        layout.addWidget(tabs)
