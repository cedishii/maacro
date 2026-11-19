"""Named setups per mode ("Shibuya Act 6 — Bulby farm", "Raid team"…) and
share codes, so a working setup can be kept, switched to in one click, and
passed to a friend as a line of text.

Profiles are saved as profiles/<mode>/<name>.json (the same fields as the
mode's own config file). A share code is "MAACRO1:" followed by the setup,
compressed and base64-encoded; importing one only ever sets fields the mode's
config already has, with values of the same type.
"""
from __future__ import annotations

import base64
import json
import re
import zlib
from dataclasses import asdict, fields
from pathlib import Path

from .config import VALID_KEYS

PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"
# Fields that are lists of hotbar keys: anything else in them is dropped.
KEY_LISTS = ("placement_order", "upgrade_priority", "path_units", "farm_units", "green_units")
CODE_PREFIX = "MAACRO1:"
MAX_CODE_LENGTH = 20000


def _safe_name(name: str) -> str:
    name = re.sub(r"[^\w\- ()+.,&']", "", (name or "").strip())[:60].strip(" .")
    if not name:
        raise ValueError("Give the profile a name.")
    return name


def _dir(mode: str, root: Path | None) -> Path:
    if not re.fullmatch(r"[a-z_]+", mode or ""):
        raise ValueError(f"Unknown mode {mode!r}.")
    return (root or PROFILES_DIR) / mode


def list_profiles(mode: str, root: Path | None = None) -> list[str]:
    folder = _dir(mode, root)
    if not folder.is_dir():
        return []
    return sorted((p.stem for p in folder.glob("*.json")), key=str.lower)


def save_profile(mode: str, name: str, config, root: Path | None = None) -> str:
    """Save `config` (a mode's config dataclass) as a profile; returns the name used."""
    name = _safe_name(name)
    folder = _dir(mode, root)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    return name


def load_profile(mode: str, name: str, config_class, root: Path | None = None):
    path = _dir(mode, root) / f"{_safe_name(name)}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return apply_data(config_class(), data)


def delete_profile(mode: str, name: str, root: Path | None = None) -> None:
    (_dir(mode, root) / f"{_safe_name(name)}.json").unlink(missing_ok=True)


def apply_data(config, data: dict):
    """Copy known fields from `data` onto `config`, keeping a field's default
    when the value has a different type (so a bad code can't break a setup)."""
    if not isinstance(data, dict):
        raise ValueError("That setup is empty.")
    for f in fields(config):
        if f.name not in data:
            continue
        value, default = data[f.name], getattr(config, f.name)
        if isinstance(default, bool):
            ok = isinstance(value, bool)
        elif isinstance(default, (int, float)):
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            if ok and isinstance(default, int) and not isinstance(default, bool) and float(value).is_integer():
                value = int(value)
        else:
            ok = isinstance(value, type(default))
        if ok and f.name in KEY_LISTS:
            value = [str(k) for k in value if str(k) in VALID_KEYS][:60]
            ok = bool(value) or f.name != "placement_order"
        if ok:
            setattr(config, f.name, value)
    return config


def share_code(mode: str, config) -> str:
    payload = json.dumps({"mode": mode, "config": asdict(config)}, separators=(",", ":"))
    packed = zlib.compress(payload.encode("utf-8"), 9)
    return CODE_PREFIX + base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")


def read_code(code: str) -> tuple[str, dict]:
    """(mode, config fields) from a share code. Raises ValueError."""
    code = "".join((code or "").split())
    if not code.startswith(CODE_PREFIX):
        raise ValueError("That isn't a MAACRO share code (it should start with MAACRO1:).")
    if len(code) > MAX_CODE_LENGTH:
        raise ValueError("That code is too long.")
    body = code[len(CODE_PREFIX):]
    try:
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        data = json.loads(zlib.decompress(raw, bufsize=65536).decode("utf-8"))
    except (ValueError, zlib.error, UnicodeDecodeError) as exc:
        raise ValueError("That code is damaged (copy it again, all of it).") from exc
    if not isinstance(data, dict) or not isinstance(data.get("config"), dict):
        raise ValueError("That code has no setup in it.")
    return str(data.get("mode", "")), data["config"]
