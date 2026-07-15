"""Composite dual-layer finish — the shared star/nebula separate-and-recombine core.

Standard modern DSO workflow (StarNet/StarXTerminator, confirmed as best practice): remove the
stars, process the starless *nebula* layer and the *stars* layer independently, then recombine with
a screen blend. This module is that core, shared by every non-cluster DSO mode (mosaic / emission /
reflection). Star clusters deliberately do NOT use it — there the stars ARE the subject.

Each mode supplies a PROFILE: the same processing chain, different colour emphasis and star strength.
"""
import subprocess
from pathlib import Path

import numpy as np

# Reuse the proven reflection primitives (VdB106-validated) — one implementation, shared everywhere.
from aporntool.stages.reflection_finish import (
    autostretch, fix_starnet_grid, scnr_green, saturate, midtone_boost,
    local_contrast, darken_background, desaturate_background, process_stars,
    screen_blend, save_deliverables,
)


def composite_layers(starless, stars, star_strength=1.0):
    # Screen-blend the star layer back over the processed nebula layer, scaled by star_strength:
    #   0.0 -> nebula only (stars fully suppressed), 1.0 -> full stars (keep-all default).
    # Screen never darkens below the nebula layer, so partial strengths reduce stars cleanly.
    stars = np.clip(np.asarray(stars, np.float64) * float(star_strength), 0, 1)
    return screen_blend(starless, stars)


# Per-mode processing profiles. Same chain (scnr -> saturate -> midtone -> local contrast ->
# darken bg -> desaturate bg -> screen-blend stars), tuned per target class.
EMISSION = dict(
    target_bg=0.28, shadows_clip=-2.8, scnr=True,
    sat_r=1.15, sat_g=0.5, sat_b=0.8,     # keep crimson Halpha, kill green cast, tame blue noise
    midboost=0.55, lc=1.0,                # lift nebula midtones so faint Halpha shows
    bgpull=0.10, gamma=0.95,              # gentle bg pull — keep faint Halpha above the floor (#2)
    bg_desat=0.08, bg_desat_soft=0.12,    # clean deep-sky chroma noise but keep nebula colour
    st_bright=1.3, st_sat=1.15,
    star_strength=1.0,                    # rich Milky-Way field: keep all stars
)
REFLECTION = dict(                        # reproduces the VdB106-validated reflection look
    target_bg=0.35, shadows_clip=-2.8, scnr=True,
    sat_r=0.30, sat_g=1.3, sat_b=4.5,
    midboost=0.55, lc=1.3,
    bgpull=0.08, gamma=0.85,
    bg_desat=0.14, bg_desat_soft=0.14,
    st_bright=1.5, st_sat=1.2,
    star_strength=1.0,
)
GALAXY = dict(                            # mosaic/galaxy: balanced colour, moderate star reduction
    target_bg=0.25, shadows_clip=-2.8, scnr=True,
    sat_r=1.0, sat_g=0.8, sat_b=1.1,
    midboost=0.40, lc=1.0,
    bgpull=0.08, gamma=0.88,
    bg_desat=0.10, bg_desat_soft=0.12,
    st_bright=1.3, st_sat=1.15,
    star_strength=0.5,                    # mosaic blends ~half the stars back (#10 keep-some-back)
)
PROFILES = {
    "dso-galaxy": GALAXY,
    "dso-emission-nebula": EMISSION,
    "dso-reflection-nebula": REFLECTION,
}


def run_composite_finish(clean_fits, out_stem, *, mode, starnet_exe, runner=subprocess.run,
                         scratch_dir=None, params=None, star_strength=None, jpeg_quality=95):
    # stretch -> StarNet -> process starless (nebula) + process stars -> screen-blend -> deliverables.
    # StarNet scratch tifs stay in scratch_dir (never beside the deliverables, FR-4).
    import tifffile
    from astropy.io import fits

    prof = dict(PROFILES[mode])
    if params:
        prof.update(params)                       # config overrides
    if star_strength is not None:
        prof["star_strength"] = float(star_strength)   # explicit --star-reduce wins

    d = fits.getdata(str(clean_fits)).astype(np.float64)
    img = np.moveaxis(d, 0, -1) if d.ndim == 3 else np.stack([d] * 3, -1)
    img = np.clip(img, 0, None)
    mx = np.percentile(img, 99.995) or 1.0
    stretched = autostretch(np.clip(img / mx, 0, 1),
                            target_bg=prof["target_bg"], shadows_clip=prof["shadows_clip"])

    work = Path(scratch_dir) if scratch_dir else Path(out_stem).parent
    work.mkdir(parents=True, exist_ok=True)
    tin, tout = work / "_sn_in.tif", work / "_sn_out.tif"
    tifffile.imwrite(str(tin), (stretched * 65535 + 0.5).astype(np.uint16), photometric="rgb")
    runner([str(starnet_exe), "-i", str(tin), "-o", str(tout)], capture_output=True, text=True)

    starless = fix_starnet_grid(tifffile.imread(str(tout)).astype(np.float64) / 65535.0)
    stars = np.clip(stretched - starless, 0, 1)

    sl = scnr_green(starless) if prof.get("scnr") else starless
    sl = saturate(sl, prof["sat_r"], prof["sat_g"], prof["sat_b"])
    sl = midtone_boost(sl, prof["midboost"])
    sl = local_contrast(sl, prof["lc"])
    sl = darken_background(sl, prof["bgpull"], prof["gamma"])
    sl = desaturate_background(sl, prof["bg_desat"], prof["bg_desat_soft"])
    st = process_stars(stars, prof["st_bright"], prof["st_sat"])

    combined = composite_layers(sl, st, prof["star_strength"])
    save_deliverables(combined, out_stem, jpeg_quality)
    return Path(str(out_stem) + ".tif")
