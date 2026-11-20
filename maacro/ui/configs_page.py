"""The Configs page: one settings tab per mode, each with a card per hotbar
unit (enabled, name, placements, placement and upgrade priority) plus the
mode's switches.

The cards are another way to edit the same settings as before: on Save they
become the placement order ("6 5 5 5 1 1") and upgrade priority ("6 5 1")
the macro already uses, so nothing about how a mode plays changes.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QRadioButton, QScrollArea, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget,
)

from ..config import VALID_KEYS, MacroConfig
from ..general.config import GeneralConfig
from ..infinity_castle.config import InfinityConfig
from .. import profiles
from ..summer_config import SummerConfig
from ..sky_portal.config import SkyPortalConfig
from ..stage_modes import ChallengeConfig, InfiniteConfig, StoryConfig
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
                 wave_option: bool = False, parent=None):
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
        self.place_wave = self.upgrade_wave = None
        if wave_option:
            grid.addWidget(QLabel("From wave: place · upgrade", objectName="Muted"), 6, 1)
            waves = QWidget()
            waves.setStyleSheet("background: transparent;")
            row = QHBoxLayout(waves)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            self.place_wave = self._wave_spin("Don't place this unit before this wave "
                                              "(e.g. a late-game unit). Start = right away.")
            self.upgrade_wave = self._wave_spin("Don't upgrade this unit before this wave (money "
                                                "goes to the others first). Start = right away.")
            row.addWidget(self.place_wave)
            row.addWidget(self.upgrade_wave)
            grid.addWidget(waves, 7, 1)
        self.enabled.toggled.connect(self._enable)
        self.upgrade.toggled.connect(lambda _: self._enable(self.enabled.isChecked()))

    @staticmethod
    def _wave_spin(tip: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, 999)
        spin.setSpecialValueText("Start")
        spin.setToolTip(tip)
        return spin

    @staticmethod
    def _spin(low: int, high: int, tip: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setToolTip(tip)
        return spin

    def _enable(self, on: bool) -> None:
        for widget in (self.placements, self.place_priority, self.upgrade, self.path, self.farm, self.cap,
                       self.place_wave, self.upgrade_wave):
            if widget is not None:
                widget.setEnabled(on)
        self.upgrade_priority.setEnabled(on and self.upgrade.isChecked())

    def set_values(self, values: dict, on_path: bool, farm: bool = False, cap: int = 0,
                   place_wave: int = 0, upgrade_wave: int = 0) -> None:
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
        if self.place_wave is not None:
            self.place_wave.setValue(int(place_wave or 0))
            self.upgrade_wave.setValue(int(upgrade_wave or 0))
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
                 choices: dict[str, tuple[str, list[tuple[str, str]]]] | None = None,
                 mode_key: str = "", lobby: dict | None = None, parent=None):
        super().__init__(parent)
        self.config_class = config_class
        self.mode_key = mode_key
        self.ic = issubclass(config_class, InfinityConfig)
        self.farm = "farm_units" in getattr(config_class, "__dataclass_fields__", {})
        self.caps = "upgrade_caps" in getattr(config_class, "__dataclass_fields__", {})
        self.waves = "place_from_wave" in getattr(config_class, "__dataclass_fields__", {})
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.cards = {}
        for index, key in enumerate(VALID_KEYS):
            card = UnitCard(key, path_option=self.ic, farm_option=self.farm, cap_option=self.caps,
                            wave_option=self.waves)
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
        # Starting from the lobby (Story / Infinite / Challenge): a panel of its own.
        self.lobby_fields: dict[str, QWidget] = {}
        if lobby:
            layout.addWidget(self._lobby_box(lobby))

        actions = QHBoxLayout()
        save = QPushButton("Save", objectName="StartButton")
        save.clicked.connect(self.save)
        reset = QPushButton("Defaults")
        reset.clicked.connect(lambda: self.show_config(self.config_class()))
        actions.addWidget(save)
        actions.addWidget(reset)
        read_names = QPushButton("Read names from the game")
        read_names.setToolTip("During a match, read each unit's name off the hotbar into the empty "
                              "name boxes (check them, then Save).")
        read_names.clicked.connect(self._read_names)
        actions.addWidget(read_names)
        self.message = QLabel("")
        actions.addWidget(self.message)
        actions.addStretch()
        layout.addLayout(actions)
        if mode_key:
            layout.addWidget(self._profiles_box())
        layout.addStretch()
        self.show_config(config_class.load())

    # --- starting from the lobby -----------------------------------------------
    def _lobby_box(self, lobby: dict) -> QFrame:
        """lobby: {"tile": "Play Area" / "Challenges", "stage": True for the
        map / act / difficulty fields, "acts": include the Act / Difficulty boxes}."""
        box, box_layout = panel("Start from the lobby")
        steps = (f"Areas → {lobby['tile']} → walk into a door"
                 + (" → the map → " + ("Act / difficulty" if lobby.get("acts") else "Infinite") + " → Select"
                    if lobby.get("stage") else "") + " → Start (if shown) → play.")
        box_layout.addWidget(QLabel(f"In the lobby, MAACRO goes there itself: {steps} If a step fails it "
                                    "presses Cancel and tries again a bit later.", objectName="Muted",
                                    wordWrap=True))
        check = QCheckBox("Start from the lobby by itself")
        box_layout.addWidget(check)
        self.lobby_fields["lobby_start"] = check
        form = QFormLayout()
        if lobby.get("stage"):
            world = QLineEdit(placeholderText="As in the Select World list, e.g. Walled City")
            world.setToolTip("The map's name as the Select World list shows it (the list is scrolled "
                             "until it's found).")
            form.addRow("Map", world)
            self.lobby_fields["world"] = world
        if lobby.get("acts"):
            act = QComboBox()
            for n in "123456":
                act.addItem(f"Act {n}", n)
            form.addRow("Act", act)
            self.lobby_fields["act"] = act
            difficulty = QComboBox()
            difficulty.addItem("Normal", "normal")
            difficulty.addItem("Hard", "hard")
            form.addRow("Difficulty", difficulty)
            self.lobby_fields["difficulty"] = difficulty
        walk = QLineEdit(placeholderText="w+d 2")
        walk.setToolTip("How to walk from where the teleport puts you into a door: keys held together "
                        "joined by +, then seconds; steps separated by commas (e.g. 'w+d 2' or "
                        "'w 1, d 0.5'). It stops early once the world window shows.")
        walk_row = QHBoxLayout()
        walk_row.addWidget(walk, 1)
        self.record_walk_button = QPushButton("Record")
        self.record_walk_button.setToolTip(
            "Walk it once yourself: press Record, switch to Roblox (teleported in front of the doors) "
            "and walk into the door. MAACRO only reads the keys you press and writes the walk here "
            "(it stops 1.5 s after you let go; Esc cancels).")
        self.record_walk_button.clicked.connect(self._record_walk)
        walk_row.addWidget(self.record_walk_button)
        form.addRow("Walk into the door", walk_row)
        self.lobby_fields["lobby_walk"] = walk
        sprint = QCheckBox("Sprint (hold Shift while walking)")
        sprint.setToolTip("Set by Record from whether you held Shift, so the walk plays back at "
                          "the speed it was recorded.")
        form.addRow("", sprint)
        self.lobby_fields["walk_sprint"] = sprint
        box_layout.addLayout(form)
        self.walk_note = QLabel("", objectName="Muted", wordWrap=True)
        self.walk_note.hide()
        box_layout.addWidget(self.walk_note)
        return box

    def _record_walk(self) -> None:
        from ..walk_record import WalkRecorder
        recorder = getattr(self, "_walk_recorder", None)
        if recorder is not None and recorder.isRunning():
            recorder.requestInterruption()
            return
        recorder = WalkRecorder(parent=self)
        self._walk_recorder = recorder
        recorder.status.connect(self._walk_status)
        recorder.done.connect(self._walk_recorded)
        recorder.failed.connect(lambda text: self._walk_status(text, theme.WARN))
        recorder.finished.connect(lambda: self.record_walk_button.setText("Record"))
        self.record_walk_button.setText("Stop")
        recorder.start()

    def _walk_status(self, text: str, color: str | None = None) -> None:
        self.walk_note.setText(text)
        self.walk_note.setStyleSheet(f"color: {color};" if color else "")
        self.walk_note.show()

    def _walk_recorded(self, route: str, sprint: bool) -> None:
        self.lobby_fields["lobby_walk"].setText(route)
        self.lobby_fields["walk_sprint"].setChecked(sprint)
        self._walk_status(f"Recorded: {route}" + (" (sprinting)" if sprint else "")
                          + " — press Save to keep it.", theme.WIN)

    def _show_lobby(self, config) -> None:
        for name, widget in self.lobby_fields.items():
            value = getattr(config, name, None)
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(0, widget.findData(value)))
            else:
                widget.setText(str(value or ""))

    def _lobby_problem(self) -> str:
        if not self.lobby_fields:
            return ""
        from ..lobby_start import parse_route
        walk = self.lobby_fields["lobby_walk"].text().strip() or "w+d 2"
        try:
            parse_route(walk)
        except ValueError as exc:
            return f"Walk into the door: {exc}."
        on = self.lobby_fields["lobby_start"].isChecked()
        world = self.lobby_fields.get("world")
        if on and world is not None and not world.text().strip():
            return "Start from the lobby: type the map's name (as in the Select World list)."
        return ""

    def _apply_lobby(self, config) -> None:
        for name, widget in self.lobby_fields.items():
            if isinstance(widget, QCheckBox):
                setattr(config, name, widget.isChecked())
            elif isinstance(widget, QComboBox):
                setattr(config, name, widget.currentData())
            else:
                text = widget.text().strip()
                setattr(config, name, text or ("w+d 2" if name == "lobby_walk" else ""))

    # --- names off the hotbar ---------------------------------------------
    capture = None          # set by ConfigsPage

    def _read_names(self) -> None:
        if self.capture is None:
            return
        _, frame = self.capture.latest_frame()
        if frame is None:
            self._message("No picture of Roblox yet — open it (not minimized), in a match.", theme.LOSS)
            return
        from ..vision.ocr import OcrReader
        from ..vision.unit_names import read_slot_names
        try:
            found = read_slot_names(frame, OcrReader())
        except Exception as exc:
            self._message(f"Couldn't read the hotbar: {exc}", theme.LOSS)
            return
        if not found:
            self._message("No names read — be in a match with the hotbar showing.", theme.LOSS)
            return
        filled = []
        for key, name in sorted(found.items()):
            card = self.cards.get(key)
            if card is not None and not card.name.text().strip():
                card.name.setText(name)
                filled.append(f"{key} = {name}")
        read = ", ".join(f"{k} = {n}" for k, n in sorted(found.items()))
        if filled:
            self._message(f"Filled {', '.join(filled)} (read: {read}). Check them and press Save.", theme.WIN)
        else:
            self._message(f"Read: {read}. Every name box already had a name — nothing changed.", theme.MUTED)

    # --- profiles and share codes ------------------------------------------
    def _profiles_box(self) -> QFrame:
        box, box_layout = panel("Profiles & sharing")
        box_layout.addWidget(QLabel(
            "Keep a setup per stage or team and switch in one click. A share code is this setup "
            "as one line of text — send it to a friend, or paste theirs.", objectName="Muted",
            wordWrap=True))
        row = QHBoxLayout()
        self.profile_box = QComboBox()
        self.profile_box.setMinimumWidth(220)
        self.profile_box.setToolTip("Saved profiles for this mode.")
        row.addWidget(self.profile_box, 1)
        for text, slot, tip in (
                ("Load", self._load_profile, "Use this profile (saved as the mode's setup right away)."),
                ("Delete", self._delete_profile, "Delete this profile."),
        ):
            button = QPushButton(text)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            row.addWidget(button)
        box_layout.addLayout(row)
        row = QHBoxLayout()
        self.profile_name = QLineEdit(placeholderText="Profile name, e.g. Shibuya Act 6 — farm team")
        row.addWidget(self.profile_name, 1)
        save_as = QPushButton("Save as profile")
        save_as.setToolTip("Save the setup above (also saved as the mode's setup) under this name.")
        save_as.clicked.connect(self._save_profile)
        row.addWidget(save_as)
        box_layout.addLayout(row)
        row = QHBoxLayout()
        self.code_edit = QLineEdit(placeholderText="Paste a share code (MAACRO1:…)")
        row.addWidget(self.code_edit, 1)
        import_button = QPushButton("Import code")
        import_button.clicked.connect(self._import_code)
        row.addWidget(import_button)
        copy_button = QPushButton("Copy share code")
        copy_button.setToolTip("Save the setup above and copy it as a share code.")
        copy_button.clicked.connect(self._copy_code)
        row.addWidget(copy_button)
        box_layout.addLayout(row)
        self._refresh_profiles()
        return box

    def _refresh_profiles(self, select: str = "") -> None:
        names = profiles.list_profiles(self.mode_key)
        self.profile_box.clear()
        self.profile_box.addItems(names)
        self.profile_box.setPlaceholderText("No profiles yet" if not names else "")
        if select in names:
            self.profile_box.setCurrentText(select)

    def _save_profile(self) -> None:
        name = self.profile_name.text().strip() or self.profile_box.currentText()
        if not name:
            self._message("Type a name for the profile first.", theme.LOSS)
            return
        if not self.save():
            return
        try:
            used = profiles.save_profile(self.mode_key, name, self.config_class.load())
        except (ValueError, OSError) as exc:
            self._message(f"Couldn't save the profile: {exc}", theme.LOSS)
            return
        self._refresh_profiles(used)
        self.profile_name.clear()
        self._message(f"Profile '{used}' saved.", theme.WIN)

    def _load_profile(self) -> None:
        name = self.profile_box.currentText()
        if not name:
            self._message("No profile picked.", theme.LOSS)
            return
        try:
            config = profiles.load_profile(self.mode_key, name, self.config_class)
            config.save()
        except (ValueError, OSError) as exc:
            self._message(f"Couldn't load '{name}': {exc}", theme.LOSS)
            return
        self.show_config(config)
        self._message(f"Profile '{name}' loaded — it applies the next time you press Start.", theme.WIN)

    def _delete_profile(self) -> None:
        name = self.profile_box.currentText()
        if not name:
            return
        if QMessageBox.question(self, "Delete profile", f"Delete the profile '{name}'?") \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            profiles.delete_profile(self.mode_key, name)
        except (ValueError, OSError) as exc:
            self._message(f"Couldn't delete: {exc}", theme.LOSS)
            return
        self._refresh_profiles()
        self._message(f"Profile '{name}' deleted.", theme.MUTED)

    def _copy_code(self) -> None:
        if not self.save():
            return
        code = profiles.share_code(self.mode_key, self.config_class.load())
        QApplication.clipboard().setText(code)
        self._message(f"Share code copied ({len(code)} characters) — paste it anywhere.", theme.WIN)

    def _import_code(self) -> None:
        try:
            mode, data = profiles.read_code(self.code_edit.text())
        except ValueError as exc:
            self._message(str(exc), theme.LOSS)
            return
        if mode and mode != self.mode_key:
            self._message(f"That code is for another mode ({mode}) — open that mode's tab to import it.",
                          theme.LOSS)
            return
        config = profiles.apply_data(self.config_class.load(), data)
        try:
            config.save()
        except OSError as exc:
            self._message(f"Couldn't save: {exc}", theme.LOSS)
            return
        self.show_config(config)
        self.code_edit.clear()
        self._message("Code imported and saved — it applies the next time you press Start.", theme.WIN)

    def show_config(self, config: MacroConfig) -> None:
        path = set(getattr(config, "path_units", []))
        farm = set(getattr(config, "farm_units", []))
        caps = getattr(config, "upgrade_caps", {}) or {}
        place_waves = getattr(config, "place_from_wave", {}) or {}
        upgrade_waves = getattr(config, "upgrade_from_wave", {}) or {}
        for key, values in cards_from_config(config).items():
            self.cards[key].set_values(values, key in path, key in farm, caps.get(key, 0),
                                       place_waves.get(key, 0), upgrade_waves.get(key, 0))
        for name, box in self.switches.items():
            box.setChecked(bool(getattr(config, name)))
        for name, buttons in self.choices.items():
            current = getattr(config, name, None)
            (buttons.get(current) or next(iter(buttons.values()))).setChecked(True)
        self._show_lobby(config)

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

    def save(self) -> bool:
        cards = {key: card.values() for key, card in self.cards.items()}
        order, upgrades = config_lists(cards)
        if not order:
            self._message("Enable at least one unit.", theme.LOSS)
            return False
        problem = self._lobby_problem()
        if problem:
            self._message(problem, theme.LOSS)
            return False
        config = self.config_class.load()
        config.placement_order, config.upgrade_priority = order, upgrades
        config.unit_names = {key: cards[key]["name"] for key in VALID_KEYS}
        if self.ic:
            config.path_units = [k for k, card in self.cards.items()
                                 if card.path is not None and card.path.isChecked() and cards[k]["enabled"]]
        if self.caps:
            config.upgrade_caps = {k: card.cap.value() for k, card in self.cards.items()
                                   if card.cap is not None and card.cap.value() > 0}
        if self.waves:
            config.place_from_wave = {k: card.place_wave.value() for k, card in self.cards.items()
                                      if card.place_wave.value() > 0 and cards[k]["enabled"]}
            config.upgrade_from_wave = {k: card.upgrade_wave.value() for k, card in self.cards.items()
                                        if card.upgrade_wave.value() > 0 and cards[k]["enabled"]}
        if self.farm:
            config.farm_units = [k for k, card in self.cards.items()
                                 if card.farm is not None and card.farm.isChecked() and cards[k]["enabled"]]
        for name, box in self.switches.items():
            setattr(config, name, box.isChecked())
        for name, buttons in self.choices.items():
            setattr(config, name, next((v for v, b in buttons.items() if b.isChecked()), next(iter(buttons))))
        self._apply_lobby(config)
        try:
            config.save()
        except OSError as exc:
            self._message(f"Couldn't save: {exc}", theme.LOSS)
            return False
        place_only = [k for k in dict.fromkeys(order) if k not in upgrades]
        self._message(f"Saved. Placement order: {order_text(order)} · upgrades: {' '.join(upgrades) or 'none'}"
                      + (f" · place only: {' '.join(place_only)}" if place_only else ""), theme.WIN)
        return True

    def _message(self, text: str, color: str) -> None:
        self.message.setStyleSheet(f"color: {color};")
        self.message.setText(text)


class ConfigsPage(QWidget):
    def __init__(self, capture=None, parent=None):
        super().__init__(parent)
        ModeSettings.capture = capture
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
            ("hard", "Hard — red cards as much as possible (the highest + Secret Drop Rate first, "
                     "then the most SummerPearls, the mildest danger among equals)"),
            ("smart", "Smart — Hard while winning; after a defeat, Easy for the next 2 runs"),
        ])}, mode_key="summer"), "Summer Event")
        tabs.addTab(ModeSettings(InfinityConfig, {
            "place_units": "Place units",
            "upgrade_units": "Upgrade units to Max (unit manager, F)",
            "auto_vote_start": "Vote Yes on 'Vote start'",
            "fast_economy": "Fast economy: place and upgrade twice as often (money comes fast)",
        }, mode_key="infinity_castle"), "Infinity Castle")
        stage_switches = {
            "place_units": "Place units",
            "upgrade_units": "Upgrade units to Max (unit manager, F)",
            "use_map_zones": "Use saved map zones (and the walk some maps need); off = automatic spots, never moves",
            "auto_vote_start": "Vote Yes on 'Vote start'",
            "auto_card_pick": "Pick cards if a card vote shows up (off = wait)",
        }
        tabs.addTab(ModeSettings(StoryConfig, stage_switches, {
            "story_progress": ("After the match", [
                ("next", "Go through the acts — a win → Next Stage, a defeat → Retry the act"),
                ("farm", "Farm this act — always Replay"),
            ]),
            "last_act": ("After the last act (a win with no Next Stage)", [
                ("replay", "Replay it (keep farming the last act)"),
                ("stop", "Stop the macro (and post a Discord summary)"),
            ]),
        }, mode_key="story", lobby={"tile": "Play Area", "stage": True, "acts": True}), "Story")
        tabs.addTab(ModeSettings(InfiniteConfig, stage_switches, {
            "after_defeat": ("After the defeat that ends a run", [
                ("replay", "Replay (start a new run)"),
                ("none", "Leave it to me"),
            ]),
        }, mode_key="infinite", lobby={"tile": "Play Area", "stage": True}), "Infinite")
        tabs.addTab(ModeSettings(ChallengeConfig, stage_switches, {
            "challenge_after": ("After the challenge", [
                ("replay_or_lobby", "Replay if the game offers it, otherwise Return to lobby"),
                ("lobby", "Always Return to lobby (then your lobby Actions, or you, join the next)"),
                ("none", "Leave it to me"),
            ]),
        }, mode_key="challenge", lobby={"tile": "Challenges"}), "Challenge")
        tabs.addTab(ModeSettings(GeneralConfig, {
            "place_units": "Place units",
            "upgrade_units": "Upgrade units to Max (unit manager, F)",
            "use_map_zones": "Use saved map zones (and the walk some maps need); off = automatic spots, never moves",
            "auto_vote_start": "Vote Yes on 'Vote start' (off = wait)",
            "auto_card_pick": "Pick cards if a card vote shows up (off = wait)",
        }, {"after_match": ("After the match", [
            ("none", "Leave it to me — wait on the results screen"),
            ("replay", "Replay the same stage (farm it)"),
            ("next", "Next Stage — go on to the next act/stage (Replay when there's none)"),
        ])}, mode_key="general"), "Any Stage")
        tabs.addTab(ModeSettings(SkyPortalConfig, {
            "place_units": "Place units",
            "upgrade_units": "Upgrade units to Max (unit manager, F)",
            "use_map_zones": "Use the Sky Portal spots (maps/sky_portal); off = automatic spots",
            "auto_vote_start": "Vote Yes on 'Vote start'",
            "auto_card_pick": "Pick cards if a card vote shows up (off = wait)",
        }, mode_key="sky_portal"), "Sky Portal")
        layout.addWidget(tabs)
