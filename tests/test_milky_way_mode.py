"""dso-milky-way wiring: image ingest, wide-field target, preflight needs, config params, CLI parse."""
import json

from aporntool.workspace import iter_images, count_images, stage_images
from aporntool.detect import resolve_target_wide
from aporntool.preflight import MODE_TOOLS, MODE_NEEDS_GRAXPERT, run_preflight
from aporntool.config import Config, MilkyWayFinishParams, load_config
from aporntool.cli import build_parser, MODES, WIDE_MODES


# --- image ingest ------------------------------------------------------------

def test_iter_images_accepts_stills_and_ignores_fits_and_junk(tmp_path):
    for name in ("a.jpg", "b.JPEG", "c.png", "d.tif", "e.tiff", "f.heic"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "raw.fit").write_bytes(b"x")     # a FITS sub is NOT a wide-field still
    (tmp_path / "notes.txt").write_bytes(b"x")
    names = sorted(f.name for f in iter_images(tmp_path))
    assert names == ["a.jpg", "b.JPEG", "c.png", "d.tif", "e.tiff", "f.heic"]
    assert count_images(tmp_path) == 6


def test_iter_images_skips_own_deliverables_and_thumbnails(tmp_path):
    # Pointing --in at a folder that already holds a prior run's outputs must not restack them.
    (tmp_path / "IMG_1.jpg").write_bytes(b"x")          # a real frame
    (tmp_path / "MilkyWay_final.jpg").write_bytes(b"x")  # our own deliverable → skip
    (tmp_path / "MilkyWay_final.png").write_bytes(b"x")  # our own deliverable → skip
    (tmp_path / "IMG_1_thn.jpg").write_bytes(b"x")       # thumbnail sidecar → skip
    names = [f.name for f in iter_images(tmp_path)]
    assert names == ["IMG_1.jpg"]


def test_stage_images_hardlinks_only_stills(tmp_path):
    src = tmp_path / "night"; src.mkdir()
    (src / "IMG_1.jpeg").write_bytes(b"x")
    (src / "IMG_1.fit").write_bytes(b"x")        # ignored by the image stager
    dest = tmp_path / "_work" / "MilkyWay" / "00_lights"
    n = stage_images([src], dest)
    assert n == 1
    assert (dest / "IMG_1.jpeg").exists() and not (dest / "IMG_1.fit").exists()


def test_stage_images_disambiguates_cross_source_collisions(tmp_path):
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    (a / "IMG_2162.jpeg").write_bytes(b"one")
    (b / "IMG_2162.jpeg").write_bytes(b"two")
    dest = tmp_path / "lights"
    assert stage_images([a, b], dest) == 2
    assert (dest / "IMG_2162.jpeg").exists() and (dest / "s1_IMG_2162.jpeg").exists()


# --- wide-field target -------------------------------------------------------

def test_resolve_target_wide_defaults_to_milkyway():
    t = resolve_target_wide(None)
    assert t.name == "MilkyWay" and t.mode == "milky-way"


def test_resolve_target_wide_honours_explicit_name():
    t = resolve_target_wide("Rho Ophiuchi")
    assert t.name == "Rho Ophiuchi"


# --- preflight ---------------------------------------------------------------

def test_milky_way_needs_siril_and_graxpert_not_starnet():
    assert MODE_TOOLS["dso-milky-way"] == ["siril", "graxpert"]
    assert "dso-milky-way" in MODE_NEEDS_GRAXPERT


def test_milky_way_preflight_passes_with_siril_graxpert_and_models(tmp_path):
    # GraXpert models present → all checks OK; no StarNet check for this mode.
    for kind in ("bge", "denoise"):
        d = tmp_path / f"{kind}-ai-models" / "v1"; d.mkdir(parents=True)
        (d / "model.onnx").write_bytes(b"x")
    results = run_preflight("dso-milky-way",
                            tool_paths={"siril": "/siril", "graxpert": "/graxpert"},
                            graxpert_model_root=tmp_path, siril_starnet_exe="")
    names = {r.name for r in results}
    assert all(r.ok for r in results)
    assert "graxpert-models" in names and "siril-starnet" not in names


def test_milky_way_preflight_flags_missing_graxpert_models(tmp_path):
    results = run_preflight("dso-milky-way",
                            tool_paths={"siril": "/siril", "graxpert": "/graxpert"},
                            graxpert_model_root=tmp_path)   # empty → no models
    models = next(r for r in results if r.name == "graxpert-models")
    assert not models.ok


# --- config params -----------------------------------------------------------

def test_milkyway_finish_defaults_protect_the_band():
    p = MilkyWayFinishParams()
    assert p.bge_smoothing >= 1.0        # high on purpose (don't subtract the MW)
    assert Config.default().pipeline.milkyway_finish.bge_smoothing == p.bge_smoothing


def test_milkyway_finish_param_overlay(tmp_path):
    path = tmp_path / "aporntool.config.json"
    path.write_text(json.dumps({"pipeline": {"milkyway_finish": {"bge_smoothing": 0.5,
                                                                  "satu": 0.9}}}))
    cfg = load_config(path)
    assert cfg.pipeline.milkyway_finish.bge_smoothing == 0.5
    assert cfg.pipeline.milkyway_finish.satu == 0.9
    # untouched keys keep their default
    assert cfg.pipeline.milkyway_finish.autostretch_clip == MilkyWayFinishParams().autostretch_clip


def test_milkyway_finish_overlay_rejects_bad_types(tmp_path):
    path = tmp_path / "aporntool.config.json"
    path.write_text(json.dumps({"pipeline": {"milkyway_finish": {"bge_smoothing": "loads",
                                                                 "satu": True}}}))
    cfg = load_config(path)   # bad types ignored, defaults kept, never fatal
    d = MilkyWayFinishParams()
    assert cfg.pipeline.milkyway_finish.bge_smoothing == d.bge_smoothing
    assert cfg.pipeline.milkyway_finish.satu == d.satu


# --- CLI parse ---------------------------------------------------------------

def test_dso_milky_way_is_a_registered_mode():
    assert "dso-milky-way" in MODES and "dso-milky-way" in WIDE_MODES


def test_parser_accepts_dso_milky_way():
    parser = build_parser()
    args = parser.parse_args(["dso-milky-way", "--in", "/some/folder"])
    assert args.command == "dso-milky-way" and args.inputs == ["/some/folder"]
