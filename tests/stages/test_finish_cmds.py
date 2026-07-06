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
                            spcc='spcc "-oscsensor=Sony IMX662" -catalog=localgaia')
    j = "\n".join(c)
    assert "denoise -mod=0.5" in j
    assert "ght -D=0.7" in j and "-HP=0.9" in j
    assert "satu 0.6 0.1" in j and "starnet" not in j
