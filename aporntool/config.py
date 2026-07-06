"""Load/save the single aporntool.config.json (tool paths + Seestar defaults + catalogs)."""
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class Config:
    tool_paths: dict = field(default_factory=dict)   # e.g. {"siril": "/opt/siril"}
    seestar_focal_mm: float = 150.0                   # Seestar S30 default optics
    seestar_pixel_um: float = 2.9
    catalog_astro: str | None = None                  # local Gaia astrometry catalog (file)
    catalog_photo: str | None = None                  # local Gaia SPCC catalog (folder)

    @classmethod
    def default(cls) -> "Config":
        return cls()


def load_config(path) -> Config:
    cfg = Config.default()
    path = Path(path)
    if path.exists():
        # Overlay saved values onto defaults; unknown keys are ignored (forward-compatible).
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
    return cfg


def save_config(cfg: Config, path) -> None:
    Path(path).write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
