"""Pure SIRIL command lists for per-mode finishing (ported from the /dso-* skills + M31 scripts)."""


def crop_cmds(box) -> list:
    # Optional crop; box is "X Y W H" from --crop, or None to skip (use the full frame).
    return [f"crop {box}"] if box else []


def deliverable_save_cmds(name) -> list:
    # The four FR-27 deliverables (.fit/.tif/.png/.jpg). SIRIL `save` writes .fit.
    return [f"save {name}", f"savetif {name}", f"savepng {name}", f"savejpg {name} 95"]


def mosaic_finish_cmds(clean_name, out_name, *, star_reduce=0.5) -> list:
    # From 5_Stretch.ssf + dso_mosaic.bat: stretch/colour → StarNet star mask → blend some back.
    return [
        f"load {clean_name}",
        "autostretch -linked -2.8 0.15",
        "ght -D=0.8 -B=3 -SP=0.15 -HP=0.85 -human",
        "rmgreen 1",
        "satu 0.7",
        f"save {out_name}_stretched",
        f"load {out_name}_stretched",
        "starnet",                                  # → starless + starmask_<name>
        f"save {out_name}_starless",
        # Blend a fraction of the stars back (full removal looks AI-generated, #10).
        f'pm "${out_name}_starless$+$starmask_{out_name}_stretched$*{star_reduce}"',
    ] + deliverable_save_cmds(out_name)


def emission_finish_cmds(anchor, out_name, *, box, spcc) -> list:
    # Route A (proven on M8): crop → gradient → local-Gaia platesolve + SPCC → denoise → stretch.
    return [
        f"load {anchor}",
        *crop_cmds(box),
        "subsky 1",
        "platesolve -catalog=localgaia",
        spcc,
        "denoise",
        "autostretch -linked",
        "satu 0.7 0.1",                            # keep all stars (rich field)
    ] + deliverable_save_cmds(out_name)


def cluster_finish_cmds(anchor, out_name, *, box, spcc) -> list:
    # §4.8 authored: light denoise + highlight-protected stretch; stars are the subject.
    return [
        f"load {anchor}",
        *crop_cmds(box),
        "subsky 1",
        "platesolve -catalog=localgaia",
        spcc,
        "denoise -mod=0.5",
        "autostretch -linked",
        "ght -D=0.7 -B=3 -HP=0.9 -human",
        "satu 0.6 0.1",
    ] + deliverable_save_cmds(out_name)
