"""Per-mode SIRIL command lists for the preprocess core (§4.4b). Pure — no I/O, easy to test."""

_SINGLE_PANEL = {"dso-emission-nebula", "dso-reflection-nebula", "dso-star-cluster"}
_SPCC_IN_PREPROCESS = {"dso-mosaic", "dso-reflection-nebula"}   # others SPCC in the finish phase


def is_single_panel(mode: str) -> bool:
    # Mosaic assembles via WCS (no flip); single-panel modes need mirrorx.
    return mode in _SINGLE_PANEL


def spcc_in_preprocess(mode: str) -> bool:
    # Mosaic/reflection color-calibrate before the golden anchor; emission/cluster do it in finish.
    return mode in _SPCC_IN_PREPROCESS


def convert_cmds() -> list:
    # Link all staged .fit in the lights dir into a SIRIL sequence named "light".
    return ["link light -out=../01_process"]


def calibrate_cmds() -> list:
    # Debayer only — the Seestar already calibrated internally, so no darks/flats/bias.
    return ["calibrate light -debayer"]


def register_cmds(mode: str) -> list:
    if mode == "dso-mosaic":
        # WCS-based assembly: plate-solve every frame, then reproject to a common max frame.
        return ["seqplatesolve pp_light -force -nocache",
                "seqapplyreg pp_light -filter-round=2.5k -framing=max"]
    if mode == "dso-star-cluster":
        # Tight round stars are the payoff → also cull the worst FWHM (authored -wfwhm=2.5k).
        return ["register pp_light -2pass",
                "seqapplyreg pp_light -filter-round=2.5k -filter-wfwhm=2.5k"]
    # emission / reflection: star-based 2-pass registration.
    return ["register pp_light -2pass",
            "seqapplyreg pp_light -filter-round=2.5k"]


def stack_cmds(mode: str) -> list:
    # Sigma-clip stack. feather=100 is MANDATORY for mosaics or panel seams are permanent (#1).
    feather = " -feather=100" if mode == "dso-mosaic" else ""
    return [f"stack r_pp_light rej 3 3 -norm=addscale -output_norm -rgb_equal{feather} -out=result"]


def mirrorx_cmds() -> list:
    # Seestar frames are vertically flipped; correct single-panel stacks (mosaic uses WCS instead).
    return ["mirrorx_single result"]
