"""The <OUT>/_work/<target>/ layout, deliverable naming, and .fit-only sub staging."""
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

_FIT_SUFFIXES = (".fit", ".fits")
# Wide-field (dso-milky-way) ingests already-debayered camera/phone stills instead of raw FITS.
# All of these are formats SIRIL's `convert` reads natively (JPEG/PNG/TIFF/HEIF).
_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic")
# DSLR/mirrorless raw formats SIRIL reads via libraw (Bayer/CFA — need debayering, like a Seestar sub).
_RAW_SUFFIXES = (".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2", ".pef", ".srw", ".raw")

# For DSO ingest we accept FITS *or* DSLR frames, but a folder is treated as ONE format so we never
# mix a Seestar sub with its preview .jpg, or a DSLR raw with its in-camera .jpg. Highest-priority
# format present in the folder wins. `debayer` says whether the frames are still a CFA mosaic (raw
# FITS / camera raw) vs already-debayered RGB (TIFF/JPEG exports).
_LIGHT_GROUPS = (
    ("fits", _FIT_SUFFIXES, True),
    ("raw", _RAW_SUFFIXES, True),
    ("tiff", (".tif", ".tiff"), False),
    ("jpeg", (".jpg", ".jpeg", ".png"), False),
)


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
    def darks(self) -> Path:       # staged dark frames (DSLR calibration; empty for Seestar)
        return self.work / "00_darks"

    @property
    def flats(self) -> Path:       # staged flat frames (DSLR calibration)
        return self.work / "00_flats"

    @property
    def bias(self) -> Path:        # staged bias/offset frames (DSLR calibration)
        return self.work / "00_bias"

    @property
    def process(self) -> Path:     # SIRIL sequences + calibrated/registered frames, incl. masters
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
        for d in (self.lights, self.darks, self.flats, self.bias,
                  self.process, self.graxpert, self.finish, self.previews):
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


def _iter_suffixed(folder, suffixes) -> list:
    out = []
    for f in sorted(Path(folder).iterdir()):
        if f.is_file() and f.suffix.lower() in suffixes:
            out.append(f)
    return out


def _is_sidecar(f) -> bool:
    # Our OWN outputs, not capture frames: a prior run's <TARGET>_final.* deliverable or a _thn
    # thumbnail. Excluded from ingest so pointing --in at a folder that holds outputs can't restack them.
    stem = f.stem.lower()
    return stem.endswith("_final") or stem.endswith("_thn")


def iter_fits(folder) -> list:
    # Only real FITS subs — Seestar folders also hold .jpg + _thn.jpg that SIRIL would wrongly ingest.
    return _iter_suffixed(folder, _FIT_SUFFIXES)


def count_fits(folder) -> int:
    return len(iter_fits(folder))


def iter_images(folder) -> list:
    # Wide-field stills (JPEG/HEIC/PNG/TIFF) for dso-milky-way.
    return [f for f in _iter_suffixed(folder, _IMAGE_SUFFIXES) if not _is_sidecar(f)]


def detect_light_kind(folder):
    # Which capture format dominates this folder, as (kind, needs_debayer). Highest-priority format
    # present wins (FITS > raw > TIFF > JPEG) so one folder is never mixed (a Seestar sub with its
    # .jpg preview, or a DSLR raw with its in-camera JPEG). (None, False) if no light frames.
    files = [f for f in Path(folder).iterdir() if f.is_file() and not _is_sidecar(f)]
    for kind, suffixes, debayer in _LIGHT_GROUPS:
        if any(f.suffix.lower() in suffixes for f in files):
            return kind, debayer
    return None, False


def iter_lights(folder) -> list:
    # DSO light frames of the folder's dominant format (see detect_light_kind), sidecars excluded.
    kind, _ = detect_light_kind(folder)
    if kind is None:
        return []
    suffixes = next(s for k, s, _ in _LIGHT_GROUPS if k == kind)
    return [f for f in _iter_suffixed(folder, suffixes) if not _is_sidecar(f)]


def count_lights(folder) -> int:
    return len(iter_lights(folder))


def stage_lights(sources, dest) -> int:
    # Stage the dominant-format light (or calibration) frames from each source into one dir.
    return _stage(sources, dest, iter_lights)


def count_images(folder) -> int:
    return len(iter_images(folder))


def stage_fits(sources, dest) -> int:
    # Bring every .fit from each source into one clean lights dir. Hardlink (instant, no extra
    # disk); fall back to a copy across drives/filesystems that can't hardlink.
    return _stage(sources, dest, iter_fits)


def stage_images(sources, dest) -> int:
    # Same collision-safe hardlink staging as stage_fits, for wide-field stills.
    return _stage(sources, dest, iter_images)


def _stage(sources, dest, iterfn) -> int:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    staged = 0
    renamed = 0
    for i, src in enumerate(sources):
        for f in iterfn(src):
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
