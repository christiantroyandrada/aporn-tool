"""Build and run SIRIL headless scripts (.ssf) via siril-cli."""
import subprocess
from dataclasses import dataclass
from pathlib import Path


def _g(v) -> str:
    # Format a number for a SIRIL command: integer-valued floats render without ".0" (3.0 -> "3",
    # keeping `rej 3 3` / `-B=3` byte-identical) while 0.85 stays "0.85".
    return f"{v:g}"


def build_ssf(commands, *, requires: str = "1.3.6", cd: str | None = None) -> str:
    # Every SIRIL script must declare a version floor first; then an optional working dir,
    # then the commands, one per line.
    lines = [f"requires {requires}"]
    if cd is not None:
        lines.append(f'cd "{cd}"')   # quote so paths with spaces survive
    lines.extend(commands)
    return "\n".join(lines) + "\n"


def write_ssf(text: str, path) -> Path:
    # Persist the script (we keep every generated .ssf in logs/ for reproducibility, FR-12).
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@dataclass
class SirilResult:
    returncode: int
    stdout: str
    stderr: str


def run_siril(script_path, *, workdir, siril_exe, runner=subprocess.run, log_path=None) -> SirilResult:
    # siril-cli's default CWD is elsewhere, so we pass -d <workdir> and an ABSOLUTE script path.
    script_path = Path(script_path).resolve()
    cmd = [str(siril_exe), "-d", str(workdir), "-s", str(script_path)]
    # `runner` is injectable so tests never launch a real SIRIL.
    proc = runner(cmd, capture_output=True, text=True)
    result = SirilResult(proc.returncode, proc.stdout or "", proc.stderr or "")
    if log_path is not None:
        # Keep the console output next to the script for debugging a failed stage.
        Path(log_path).write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    return result


def gaia_catalog_cmds(astro_path: str, photo_path: str) -> list:
    # siril-cli does NOT auto-read the local Gaia catalogs — set both paths in-script or it
    # falls back to the dead online server. _astro is a FILE, _photo is a FOLDER.
    return [
        f"set core.catalogue_gaia_astro={astro_path}",
        f"set core.catalogue_gaia_photo={photo_path}",
    ]


def platesolve_cmd(*, coords=None, focal=None, pixel=None, catalog="localgaia") -> str:
    # With coords we seed the solve (mosaic stack); blind (no coords) re-solves a framed image.
    parts = ["platesolve"]
    if coords:
        parts.append(coords)
    if focal is not None:
        parts.append(f"-focal={focal:g}")
    if pixel is not None:
        parts.append(f"-pixelsize={pixel:g}")
    parts.append(f"-catalog={catalog}")
    return " ".join(parts)


def spcc_cmd(*, sensor="Sony IMX662", osc_filter="UV/IR Block",
             whiteref="Average Spiral Galaxy", catalog="localgaia") -> str:
    # Quote the WHOLE token, flag name included ("-oscsensor=Sony IMX662") — the other form
    # ("-oscsensor=...") makes siril-cli error "Invalid argument". (gotcha #3)
    return (f'spcc "-oscsensor={sensor}" "-oscfilter={osc_filter}" '
            f'"-whiteref={whiteref}" -catalog={catalog}')
