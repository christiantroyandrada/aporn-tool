"""The <OUT>/_work/<target>/ layout, deliverable naming, and .fit-only sub staging."""
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

_FIT_SUFFIXES = (".fit", ".fits")


@dataclass
class Workspace:
    out_root: Path      # user-chosen; ONLY deliverables live at this level
    target: str

    @property
    def work(self) -> Path:        # everything scratch is namespaced per target (O2)
        return self.out_root / "_work" / self.target

    @property
    def lights(self) -> Path:      # hardlinked raw .fit subs
        return self.work / "00_lights"

    @property
    def process(self) -> Path:     # SIRIL sequences + calibrated/registered frames
        return self.work / "01_process"

    @property
    def linear(self) -> Path:      # the golden linear stack lives here
        return self.work / "02_linear"

    @property
    def previews(self) -> Path:
        return self.work / "previews"

    @property
    def logs(self) -> Path:        # generated .ssf/.py + per-stage stdout
        return self.work / "logs"

    @property
    def manifest_path(self) -> Path:
        return self.work / "aporntool.json"

    def create(self) -> None:
        for d in (self.lights, self.process, self.linear, self.previews, self.logs):
            d.mkdir(parents=True, exist_ok=True)

    def deliverable(self, ext: str) -> Path:
        # Final images sit at the OUT root, e.g. M31_final.tif.
        return self.out_root / f"{self.target}_final.{ext}"


def iter_fits(folder) -> list:
    # Only real FITS subs — Seestar folders also hold .jpg + _thn.jpg that SIRIL would wrongly ingest.
    out = []
    for f in sorted(Path(folder).iterdir()):
        if f.is_file() and f.suffix.lower() in _FIT_SUFFIXES:
            out.append(f)
    return out


def count_fits(folder) -> int:
    return len(iter_fits(folder))


def stage_fits(sources, dest) -> int:
    # Bring every .fit from each source into one clean lights dir. Hardlink (instant, no extra
    # disk); fall back to a copy across drives/filesystems that can't hardlink.
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    staged = 0
    for src in sources:
        for f in iter_fits(src):
            target = dest / f.name
            if target.exists():
                continue
            try:
                os.link(f, target)
            except OSError:
                shutil.copy2(f, target)
            staged += 1
    return staged
