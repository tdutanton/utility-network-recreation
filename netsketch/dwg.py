"""Конвертация DXF → DWG через Open CAD Studio.

Open CAD Studio умеет `--export IN OUT` только для CAD-форматов
(dwg/dxf/dwt), поэтому PDF/PNG делаются своим рендером, а DWG — здесь.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class ConversionError(RuntimeError):
    pass


def find_ocs(explicit: str = "") -> str:
    if explicit and Path(explicit).exists():
        return explicit
    for candidate in (
        os.environ.get("NS_OCS_EXE", ""),
        shutil.which("OpenCADStudio") or "",
        r"C:\Program Files\Open CAD Studio\OpenCADStudio.exe",
        r"C:\Program Files (x86)\Open CAD Studio\OpenCADStudio.exe",
        "/Applications/OpenCADStudio.app/Contents/MacOS/OpenCADStudio",
        "/usr/bin/opencadstudio",
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def _run(exe: str, args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.setdefault("RUST_LOG", "error")
    return subprocess.run(
        [exe, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )


def dxf_to_dwg(
    dxf_path: str | Path,
    dwg_path: str | Path,
    *,
    exe: str = "",
    version: str = "2018",
    allow_lossy: bool = True,
    timeout: int = 180,
) -> Path:
    dxf_path = Path(dxf_path)
    dwg_path = Path(dwg_path)
    if not dxf_path.exists():
        raise ConversionError(f"нет DXF: {dxf_path}")

    ocs = find_ocs(exe)
    if not ocs:
        raise ConversionError(
            "Open CAD Studio не найден. Укажите путь в NS_OCS_EXE или установите редактор."
        )

    if dwg_path.exists():
        dwg_path.unlink()

    args = ["--export", str(dxf_path), str(dwg_path), "--target-version", version, "--log", "error"]
    if allow_lossy:
        args.append("--allow-lossy")
    proc = _run(ocs, args, timeout=timeout)
    if not dwg_path.exists():
        raise ConversionError(
            "Open CAD Studio не создал DWG.\n"
            f"код {proc.returncode}\nstdout: {proc.stdout[-800:]}\nstderr: {proc.stderr[-800:]}"
        )
    if dwg_path.stat().st_size < 512:
        raise ConversionError(f"DWG подозрительно мал: {dwg_path.stat().st_size} байт")
    return dwg_path


def dwg_to_dxf(
    dwg_path: str | Path,
    dxf_path: str | Path | None = None,
    *,
    exe: str = "",
    version: str = "2018",
    timeout: int = 180,
) -> Path:
    """Обратная конвертация — нужна индексатору примеров и QA."""
    dwg_path = Path(dwg_path)
    if dxf_path is None:
        dxf_path = Path(tempfile.mkdtemp(prefix="ns_dwg_")) / (dwg_path.stem + ".dxf")
    dxf_path = Path(dxf_path)
    ocs = find_ocs(exe)
    if not ocs:
        raise ConversionError("Open CAD Studio не найден")
    if dxf_path.exists():
        dxf_path.unlink()
    proc = _run(
        ocs,
        ["--export", str(dwg_path), str(dxf_path), "--target-version", version, "--log", "error"],
        timeout=timeout,
    )
    if not dxf_path.exists():
        raise ConversionError(
            "не удалось прочитать DWG.\n"
            f"код {proc.returncode}\nstdout: {proc.stdout[-800:]}\nstderr: {proc.stderr[-800:]}"
        )
    return dxf_path
