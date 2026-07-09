"""Pure SIRIL command lists for per-mode finishing (ported from the /dso-* skills + M31 scripts).

Tunable stretch/saturation/gradient values come from config (aporntool.config PipelineParams); every
default below equals the value used before centralisation, so with no config the commands are
identical.
"""
from aporntool.config import (
    MosaicFinishParams, EmissionFinishParams, ClusterFinishParams,
)
from aporntool.tools.siril import _g


def crop_cmds(box) -> list:
    # Optional crop; box is "X Y W H" from --crop, or None to skip (use the full frame).
    return [f"crop {box}"] if box else []


def deliverable_save_cmds(name, jpeg_quality=95) -> list:
    # The four FR-27 deliverables (.fit/.tif/.png/.jpg). SIRIL `save` writes .fit.
    return [f"save {name}", f"savetif {name}", f"savepng {name}", f"savejpg {name} {_g(jpeg_quality)}"]


def mosaic_finish_cmds(clean_name, out_name, *, star_reduce=None, params=None, jpeg_quality=95) -> list:
    # From 5_Stretch.ssf + dso_mosaic.bat: stretch/colour → StarNet star mask → blend some back.
    p = params or MosaicFinishParams()
    sr = p.star_reduce if star_reduce is None else star_reduce   # explicit --star-reduce wins
    return [
        f"load {clean_name}",
        f"autostretch -linked {_g(p.autostretch_clip)} {_g(p.autostretch_bg)}",
        f"ght -D={_g(p.ght_d)} -B={_g(p.ght_b)} -SP={_g(p.ght_sp)} -HP={_g(p.ght_hp)} -human",
        f"rmgreen {_g(p.rmgreen)}",
        f"satu {_g(p.satu)}",
        f"save {out_name}_stretched",
        f"load {out_name}_stretched",
        "starnet",                                  # → starless + starmask_<name>
        f"save {out_name}_starless",
        # Blend a fraction of the stars back (full removal looks AI-generated, #10).
        f'pm "${out_name}_starless$+$starmask_{out_name}_stretched$*{_g(sr)}"',
    ] + deliverable_save_cmds(out_name, jpeg_quality)


def emission_finish_cmds(anchor, out_name, *, box, spcc, params=None,
                         catalog="localgaia", jpeg_quality=95) -> list:
    # Route A (proven on M8): crop → gradient → local-Gaia platesolve + SPCC → denoise → stretch.
    p = params or EmissionFinishParams()
    return [
        f"load {anchor}",
        *crop_cmds(box),
        f"subsky {_g(p.subsky_degree)}",
        f"platesolve -catalog={catalog}",
        spcc,
        "denoise",
        "autostretch -linked",
        f"satu {_g(p.satu)} {_g(p.satu_bg)}",       # keep all stars (rich field)
    ] + deliverable_save_cmds(out_name, jpeg_quality)


def cluster_finish_cmds(anchor, out_name, *, box, spcc, params=None,
                        catalog="localgaia", jpeg_quality=95) -> list:
    # §4.8 authored: light denoise + highlight-protected stretch; stars are the subject.
    p = params or ClusterFinishParams()
    return [
        f"load {anchor}",
        *crop_cmds(box),
        f"subsky {_g(p.subsky_degree)}",
        f"platesolve -catalog={catalog}",
        spcc,
        f"denoise -mod={_g(p.denoise_mod)}",
        "autostretch -linked",
        f"ght -D={_g(p.ght_d)} -B={_g(p.ght_b)} -HP={_g(p.ght_hp)} -human",
        f"satu {_g(p.satu)} {_g(p.satu_bg)}",
    ] + deliverable_save_cmds(out_name, jpeg_quality)
