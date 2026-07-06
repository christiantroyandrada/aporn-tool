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
    def graxpert(self) -> Path:    # GraXpert BGE/denoise intermediates (mosaic finish)
        return self.work / "03_graxpert"

    @property
    def finish(self) -> Path:      # scratch cwd for SIRIL finish scripts (bare-name gotcha)
        return self.work / "05_finish"

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
        for d in (self.lights, self.process, self.linear, self.graxpert, self.finish,
                  self.previews, self.logs):
            d.mkdir(parents=True, exist_ok=True)

    def deliverable(self, ext: str) -> Path:
        # Final images sit at the OUT root, e.g. M31_final.tif.
        return self.out_root / f"{self.target}_final.{ext}"

    def clean(self) -> int:
        # Post-success cleanup (opt-in --clean): delete every working file EXCEPT the golden anchor
        # (02_linear/<TARGET>_Linear.fit), the manifest, and logs/. Reclaims almost all the disk a
        # run leaves behind while keeping a cheap re-finish -- the bge/finish stages read the anchor,
        # so `--from bge` / `--from finish` still work without re-stacking. Returns bytes actually
        # freed (hardlinked staged subs share their data with your originals, so deleting them frees
        # nothing and they are not counted). Safe to call repeatedly -- missing dirs are ignored.
        anchor = self.linear / f"{self.target}_Linear.fit"
        freed = 0
        for d in (self.lights, self.process, self.graxpert, self.finish, self.previews):
            freed += _freed_bytes(d)
            shutil.rmtree(d, ignore_errors=True)
        if self.linear.exists():
            for entry in self.linear.iterdir():
                if entry == anchor:
                    continue                       # the one file we must keep
                freed += _freed_bytes(entry)
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink()
        return freed


def _freed_bytes(path) -> int:
    # Sum the sizes of regular files whose data is actually released by deleting them. A hardlinked
    # file (st_nlink > 1 -- e.g. a staged sub still linked from your originals) frees no disk, so it
    # is not counted, keeping the reported "reclaimed" number honest.
    path = Path(path)
    if not path.exists():
        return 0
    files = [path] if path.is_file() else [f for f in path.rglob("*") if f.is_file()]
    total = 0
    for f in files:
        st = f.stat()
        if st.st_nlink == 1:
            total += st.st_size
    return total


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
    renamed = 0
    for i, src in enumerate(sources):
        for f in iter_fits(src):
            target = dest / f.name
            if target.exists():
                # Same file already staged (idempotent re-run) → skip, don't recount.
                if os.path.samefile(f, target):
                    continue
                # A DIFFERENT file with the same name (e.g. two nights both have Light_0001.fit)
                # → tag with the source index so BOTH survive instead of silently dropping one.
                target = dest / f"s{i}_{f.name}"
                renamed += 1
                if target.exists() and os.path.samefile(f, target):
                    continue
            try:
                os.link(f, target)       # hardlink = instant, no extra disk
            except OSError:
                shutil.copy2(f, target)  # different drive/FS → fall back to a copy
            staged += 1
    if renamed:
        # Don't let a night silently vanish — tell the user we disambiguated collisions.
        print(f"  note: renamed {renamed} colliding sub name(s) across sources (s<N>_ prefix) so none are dropped")
    return staged
