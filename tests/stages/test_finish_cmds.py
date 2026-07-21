from aporntool.stages.finish_cmds import (
    crop_cmds, deliverable_save_cmds, mosaic_finish_cmds,
    emission_finish_cmds, cluster_finish_cmds,
)


def test_crop_cmds_optional():
    assert crop_cmds(None) == []
    assert crop_cmds("950 948 1450 2700") == ["crop 950 948 1450 2700"]


def test_deliverable_saves_all_four():
    c = deliverable_save_cmds("M31_final")
    j = "\n".join(c)
    assert "save M31_final" in j and "savetif M31_final" in j
    assert "savepng M31_final" in j and "savejpg M31_final 95" in j


def test_cluster_finish_no_calibrate_skips_platesolve_and_spcc():
    # The fallback path (calibrate=False) omits the (seeded) plate solve + SPCC but still stretches/saves.
    solve = "platesolve 250.4,36.4 -focal=300 -pixelsize=4.29 -catalog=localgaia"
    c = cluster_finish_cmds("M13", "M13_final", box=None, spcc='spcc "-oscsensor=x"', solve=solve,
                            calibrate=False)
    j = "\n".join(c)
    assert "platesolve" not in j and "spcc" not in j
    assert "autostretch -linked" in j and "savejpg M13_final" in j
    # the default (calibrate=True) includes the seeded solve + SPCC
    d = "\n".join(cluster_finish_cmds("M13", "M13_final", box=None, spcc='spcc "-oscsensor=x"',
                                      solve=solve))
    assert solve in d and "spcc" in d


def test_mosaic_finish_stretch_star_blend():
    c = mosaic_finish_cmds("M31_clean", "M31_final", star_reduce=0.5)
    j = "\n".join(c)
    assert "autostretch -linked" in j
    assert "ght -D=0.8" in j and "-human" in j
    assert "rmgreen 1" in j and "satu 0.7" in j
    assert "starnet" in j                       # star reduction
    assert "$*0.5" in j.replace(" ", "")        # pm blend at star_reduce
    assert "savetif M31_final" in j


def test_emission_finish_keeps_stars_and_spccs():
    c = emission_finish_cmds("M8_Linear", "M8_final", box="40 70 1000 1780",
                             spcc='spcc "-oscsensor=Sony IMX662" -catalog=localgaia')
    j = "\n".join(c)
    assert "crop 40 70 1000 1780" in j
    assert "subsky 1" in j and "platesolve -catalog=localgaia" in j
    assert 'spcc "-oscsensor=Sony IMX662"' in j
    assert "autostretch -linked" in j and "satu 0.7 0.1" in j
    assert "starnet" not in j                    # emission keeps all stars


def test_cluster_finish_light_denoise_and_ght():
    c = cluster_finish_cmds("M13_Linear", "M13_final", box=None,
                            spcc='spcc "-oscsensor=Sony IMX662" -catalog=localgaia',
                            solve="platesolve 250.4,36.4 -catalog=localgaia")
    j = "\n".join(c)
    assert "denoise -mod=0.5" in j
    # Default (Seestar FITS) keeps the proven BARE autostretch — byte-identical to pre-0.6.2.
    assert "autostretch -linked\n" in j + "\n"
    assert "autostretch -linked -2.8" not in j
    assert "ght -D=0.7" in j and "-HP=0.9" in j
    assert "satu 0.6 0.1" in j and "starnet" not in j


def test_cluster_finish_dark_background_for_light_polluted_input():
    # DSLR / --stacked callers pass dark_background=True -> explicit dark autostretch target so a
    # light-polluted stack's skyglow doesn't wash the cluster background to grey.
    c = cluster_finish_cmds("M45_Linear", "M45_final", box=None, spcc="S",
                            solve="platesolve 56.9,24.1", dark_background=True)
    j = "\n".join(c)
    assert "autostretch -linked -2.8 0.12" in j     # explicit dark target
    assert "ght -D=0.7" in j                          # GHT still lifts the cluster stars
