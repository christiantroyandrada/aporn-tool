"""Load/save the single aporntool.config.json: tool paths, Seestar optics, catalogs, AND every
tunable pipeline parameter (stack/register, GraXpert, crop, SPCC, and per-mode finish knobs).

Design contract — defaults live in CODE, the file only OVERLAYS:
  * No config file (absent / deleted / empty / corrupt) -> Config.default() -> the pipeline runs
    exactly as it always has. The file is never required.
  * A present file overrides only the keys it sets; missing keys keep their default.
  * Unknown keys and type-mismatched / non-finite values are ignored (kept at default), never fatal.
So a user can drop the file, delete half of it, or hand-edit it wrong, and the tool still runs.
"""
import json
import math
from dataclasses import dataclass, field, asdict, is_dataclass, fields
from pathlib import Path


@dataclass
class StackParams:
    sigma_low: float = 3.0            # `stack ... rej <low> <high>` winsorized sigma clip
    sigma_high: float = 3.0
    feather_mosaic: int = 100         # mosaic-only `-feather=` (seams are permanent without it)
    filter_round: str = "2.5k"        # `seqapplyreg -filter-round=`
    filter_wfwhm: str = "2.5k"        # star-cluster-only extra `-filter-wfwhm=` cull


@dataclass
class GraxpertParams:
    bge_smoothing: float = 0.0        # background-extraction smoothing
    bge_correction: str = "Subtraction"  # background-extraction mode (Subtraction | Division)
    denoise_strength: float = 0.8     # AI denoise strength (1.0 over-sharpens)


@dataclass
class CropParams:
    bg_frac: float = 0.25             # signal threshold = max(peak*1e-4, bg_frac*median)
    margin_frac: float = 0.02         # inward margin on the detected rectangle
    target_blocks: int = 700          # downsample large frames to ~this many cells/axis


@dataclass
class SpccParams:
    sensor: str = "Sony IMX662"
    osc_filter: str = "UV/IR Block"
    whiteref: str = "Average Spiral Galaxy"
    catalog: str = "localgaia"


@dataclass
class MosaicFinishParams:
    autostretch_clip: float = -2.8    # `autostretch -linked <clip> <bg>`
    autostretch_bg: float = 0.15
    ght_d: float = 0.8                # `ght -D= -B= -SP= -HP= -human`
    ght_b: float = 3.0
    ght_sp: float = 0.15
    ght_hp: float = 0.85
    rmgreen: float = 1.0              # `rmgreen <amount>` green-cast removal
    satu: float = 0.7
    star_reduce: float = 0.5          # fraction of stars blended back after StarNet


@dataclass
class EmissionFinishParams:
    subsky_degree: int = 1            # `subsky <degree>` gradient polynomial
    satu: float = 0.7                 # `satu <amount> <bg>`
    satu_bg: float = 0.1


@dataclass
class ClusterFinishParams:
    subsky_degree: int = 1            # `subsky <degree>` gradient polynomial
    denoise_mod: float = 0.5          # `denoise -mod=` (light — stars are the subject)
    ght_d: float = 0.7
    ght_b: float = 3.0
    ght_hp: float = 0.9
    satu: float = 0.6
    satu_bg: float = 0.1


@dataclass
class ReflectionFinishParams:
    target_bg: float = 0.35
    shadows_clip: float = -2.8
    sat_r: float = 0.30
    sat_g: float = 1.3
    sat_b: float = 4.5
    midboost: float = 0.55
    lc: float = 1.3
    bgpull: float = 0.08
    gamma: float = 0.85
    bg_desat: float = 0.14
    bg_desat_soft: float = 0.14
    st_bright: float = 1.5
    st_sat: float = 1.2


@dataclass
class MilkyWayFinishParams:
    # Wide-field cellphone/camera Milky Way finish. GraXpert removes the light-pollution gradient
    # and denoises; SIRIL then stretches + gently saturates. No StarNet (the stars ARE the subject)
    # and no SPCC (no plate solve at a ~24mm phone field).
    # NOTE: bge_smoothing/bge_correction/denoise_strength are DELIBERATELY duplicated from
    # GraxpertParams (not shared) because wide-field needs very different values — a high BGE
    # smoothing so the large-scale Milky Way band isn't fitted and subtracted as "background",
    # unlike the DSO default of 0.0. Tune these under pipeline.milkyway_finish, not pipeline.graxpert.
    bge_smoothing: float = 1.0        # HIGH on purpose: keep GraXpert BGE from eating the MW band
    bge_correction: str = "Subtraction"
    denoise_strength: float = 0.8
    autostretch_clip: float = -2.5    # `autostretch -linked <clip> <bg>`
    autostretch_bg: float = 0.20
    rmgreen: float = 1.0              # neutralise skyglow green cast
    satu: float = 0.5                 # gentle saturation (phone colour is already processed)
    satu_bg: float = 0.1


@dataclass
class PipelineParams:
    stack: StackParams = field(default_factory=StackParams)
    graxpert: GraxpertParams = field(default_factory=GraxpertParams)
    crop: CropParams = field(default_factory=CropParams)
    spcc: SpccParams = field(default_factory=SpccParams)
    mosaic_finish: MosaicFinishParams = field(default_factory=MosaicFinishParams)
    emission_finish: EmissionFinishParams = field(default_factory=EmissionFinishParams)
    cluster_finish: ClusterFinishParams = field(default_factory=ClusterFinishParams)
    reflection_finish: ReflectionFinishParams = field(default_factory=ReflectionFinishParams)
    milkyway_finish: MilkyWayFinishParams = field(default_factory=MilkyWayFinishParams)
    jpeg_quality: int = 95            # deliverable .jpg quality, all modes


@dataclass
class Config:
    tool_paths: dict = field(default_factory=dict)   # e.g. {"siril": "/opt/siril"}
    seestar_focal_mm: float = 150.0                   # Seestar S30 default optics
    seestar_pixel_um: float = 2.9
    catalog_astro: str | None = None                  # local Gaia astrometry catalog (file)
    catalog_photo: str | None = None                  # local Gaia SPCC catalog (folder)
    pipeline: PipelineParams = field(default_factory=PipelineParams)   # all tunable knobs

    @classmethod
    def default(cls) -> "Config":
        return cls()


def _overlay(obj, data) -> None:
    # Overlay a dict of overrides onto a dataclass instance IN PLACE. Guards:
    #   * unknown keys -> ignored (kept at default)
    #   * nested dataclass field -> recurse only if the override is a dict
    #   * numeric field -> set only for a real, finite number (reject bool, NaN, Infinity)
    #   * other scalar -> set only if the override's type matches (a None default accepts anything)
    # This is what makes a partial / hand-edited / wrong-typed file safe instead of fatal.
    if not isinstance(data, dict):
        return
    valid = {f.name for f in fields(obj)}
    for key, value in data.items():
        if key not in valid:
            continue
        cur = getattr(obj, key)
        if is_dataclass(cur):
            _overlay(cur, value)                      # nested group; non-dict value ignored
        elif cur is None or isinstance(cur, bool):
            setattr(obj, key, value)                  # optional/None or bool: accept as-is
        elif isinstance(cur, (int, float)):
            # numbers interchangeable (int/float), but reject bool (a subclass of int) and any
            # non-finite value (NaN/Infinity) so they can't reach a SIRIL command
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                setattr(obj, key, value)
        elif isinstance(value, type(cur)):
            setattr(obj, key, value)                  # str->str, dict->dict, list->list
        # else: type mismatch -> keep the default


def load_config(path) -> Config:
    cfg = Config.default()
    path = Path(path)
    if not path.exists():
        return cfg                                    # no file -> pure defaults (guard)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        # Corrupt/unreadable config must never crash a run — warn and fall back to defaults.
        print(f"  WARNING: could not read config {path} ({e}); using built-in defaults.")
        return cfg
    _overlay(cfg, data)
    return cfg


def save_config(cfg: Config, path) -> None:
    # asdict recurses the nested pipeline params, so the written file is a full, editable template.
    Path(path).write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
