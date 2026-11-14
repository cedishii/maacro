"""Sky Portal settings, saved to sky_portal_config.json."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..general.config import GENERAL_CONFIG_PATH, GeneralConfig

SKY_PORTAL_CONFIG_PATH = Path(__file__).resolve().parents[2] / "sky_portal_config.json"


@dataclass
class SkyPortalConfig(GeneralConfig):
    @classmethod
    def load(cls, path: Path = SKY_PORTAL_CONFIG_PATH) -> "SkyPortalConfig":
        if not path.exists():
            # First use: General's unit setup (or Summer's, via General).
            config = cls()
            for key, value in vars(GeneralConfig.load(GENERAL_CONFIG_PATH)).items():
                setattr(config, key, value)
            config.actions = []
            config.auto_card_pick = False
            config.auto_vote_start = False
            return config
        config = super().load.__func__(cls, path)
        config.auto_vote_start = False      # never votes: the leader / the timer starts it
        return config

    def save(self, path: Path = SKY_PORTAL_CONFIG_PATH) -> None:
        self.auto_vote_start = False
        super().save(path)
