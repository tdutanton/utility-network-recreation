"""Сборка комплекта: модель → DXF, DWG, PDF, PNG."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import dwg as dwgmod
from .dxfout import save_dxf
from .layout import LayoutInfo, build_scene
from .model import Model
from .render import write_pdf, write_preview
from .route import orthogonalize
from .sheets import Sheet

log = logging.getLogger(__name__)


@dataclass
class BuildResult:
    model: Model
    scene: object
    sheet: Sheet
    info: LayoutInfo
    files: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and "dwg" in self.files


def safe_stem(text: str, fallback: str = "drawing") -> str:
    text = (text or "").strip()
    text = re.sub(r"[^\w\-. ]+", "", text, flags=re.UNICODE).strip()
    text = re.sub(r"\s+", "_", text)
    return text[:80] or fallback


def build_drawings(
    model: Model,
    outdir: str | Path,
    *,
    stem: str = "drawing",
    title: dict[str, str] | None = None,
    sheet: Sheet | None = None,
    scale: int | None = None,
    ocs_exe: str = "",
    dwg_version: str = "2018",
    make_dwg: bool = True,
    orthogonalize_route: bool = True,
) -> BuildResult:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = safe_stem(stem)

    if orthogonalize_route and not model.meta.get("no_orthogonalize"):
        model = orthogonalize(model)

    sh = sheet or Sheet(model.sheet, model.orientation)
    scene, info = build_scene(model, sheet=sh, title=title, scale_override=scale)

    dxf_path = outdir / f"{stem}.dxf"
    save_dxf(scene, dxf_path, model.network_type, dim_scale=info.scale)

    result = BuildResult(model=model, scene=scene, sheet=sh, info=info)
    result.files["dxf"] = str(dxf_path)

    pdf_path = outdir / f"{stem}.pdf"
    write_pdf(scene, pdf_path, width_mm=sh.width, height_mm=sh.height)
    result.files["pdf"] = str(pdf_path)

    png_path = outdir / f"{stem}.png"
    write_preview(scene, png_path, width_mm=sh.width, height_mm=sh.height, dpi=200)
    result.files["png"] = str(png_path)

    if make_dwg:
        dwg_path = outdir / f"{stem}.dwg"
        try:
            dwgmod.dxf_to_dwg(dxf_path, dwg_path, exe=ocs_exe, version=dwg_version)
            result.files["dwg"] = str(dwg_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("DWG не создан: %s", exc)
            result.errors.append(f"DWG не создан: {exc}")

    return result
