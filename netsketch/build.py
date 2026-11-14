"""Сборка комплекта: модель → DXF, DWG, PDF, PNG.

Два режима:
  * `plan` (по умолчанию) — план/схема в масштабе на своём листе, правая
    колонка «легенда / спецификация / примечания»;
  * `schematic` — исполнительная схема на листе ГОСТ 2.104: A3-альбом,
    штамп 185×55 в свободном углу, печатный A4-портрет (поворот 90°).

Режим берётся из аргумента, иначе из `model.meta["mode"]`, иначе `plan`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import dwg as dwgmod
from .dxfout import save_dxf
from .gost_sheet import GostSheet, print_transform
from .layout import LayoutInfo, build_scene, build_schematic_scene
from .model import Model
from .render import write_pdf, write_preview, write_print_pdf, write_print_png
from .route import orthogonalize
from .sheets import Sheet

log = logging.getLogger(__name__)


@dataclass
class BuildResult:
    model: Model
    scene: object
    sheet: object
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


def resolve_mode(model: Model, mode: str = "") -> str:
    """Режим листа: `schematic` (ГОСТ-схема) или `plan` (план в масштабе)."""
    value = (mode or str(model.meta.get("mode") or "") or "plan").lower()
    return "schematic" if value.startswith("schem") else "plan"


def as_gost_sheet(sheet: Sheet | GostSheet | None, model: Model, mode: str) -> GostSheet:
    """Привести запрошенный лист к листу ГОСТ; для схемы по умолчанию A3-альбом."""
    if isinstance(sheet, GostSheet):
        return sheet
    if isinstance(sheet, Sheet):
        return GostSheet(sheet.format, "landscape" if mode == "schematic" else sheet.orientation, sheet.stamp)
    if mode == "schematic":
        return GostSheet("A3", "landscape", "auto")
    return GostSheet(model.sheet or "A4", model.orientation or "portrait", model.meta.get("stamp", "right"))


def build_drawings(
    model: Model,
    outdir: str | Path,
    *,
    stem: str = "drawing",
    title: dict[str, str] | None = None,
    sheet: Sheet | GostSheet | None = None,
    scale: int | None = None,
    mode: str = "",
    ocs_exe: str = "",
    dwg_version: str = "2018",
    make_dwg: bool = True,
    make_print: bool = True,
    orthogonalize_route: bool = True,
) -> BuildResult:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = safe_stem(stem)
    mode = resolve_mode(model, mode)

    # Схема приходит уже готовой (эталон или распознанная схема): не
    # ортогонализуем — иначе элементы «прилипают» к ближайшей трубе и
    # разъезжаются (символы перехода, гильзы, вилка).
    if orthogonalize_route and mode != "schematic" and not model.meta.get("no_orthogonalize"):
        model = orthogonalize(model)

    if mode == "schematic":
        gsheet = as_gost_sheet(sheet, model, mode)
        scene, info = build_schematic_scene(model, sheet=gsheet, title=title, scale_override=scale)
        sh: object = gsheet
    else:
        sh = sheet if isinstance(sheet, Sheet) else Sheet(model.sheet, model.orientation)
        scene, info = build_scene(model, sheet=sh, title=title, scale_override=scale)

    width, height = sh.width, sh.height
    result = BuildResult(model=model, scene=scene, sheet=sh, info=info)

    dxf_path = outdir / f"{stem}.dxf"
    save_dxf(scene, dxf_path, model.network_type, dim_scale=info.scale)
    result.files["dxf"] = str(dxf_path)

    pdf_path = outdir / f"{stem}.pdf"
    write_pdf(scene, pdf_path, width_mm=width, height_mm=height)
    result.files["pdf"] = str(pdf_path)

    png_path = outdir / f"{stem}.png"
    write_preview(scene, png_path, width_mm=width, height_mm=height, dpi=200)
    result.files["png"] = str(png_path)

    # печатный лист: A3-альбом → A4-портрет (только для схемы)
    if mode == "schematic" and make_print:
        page_w, page_h, _scale, transform = print_transform(gsheet)
        print_pdf = outdir / f"{stem}_A4.pdf"
        write_print_pdf(
            scene, print_pdf, width_mm=width, height_mm=height, page=(page_w, page_h), transform=transform
        )
        result.files["pdf_a4"] = str(print_pdf)

        print_png = outdir / f"{stem}_A4.png"
        write_print_png(
            scene, print_png, width_mm=width, height_mm=height, page=(page_w, page_h), transform=transform
        )
        result.files["png_a4"] = str(print_png)

    if make_dwg:
        dwg_path = outdir / f"{stem}.dwg"
        try:
            dwgmod.dxf_to_dwg(dxf_path, dwg_path, exe=ocs_exe, version=dwg_version)
            result.files["dwg"] = str(dwg_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("DWG не создан: %s", exc)
            result.errors.append(f"DWG не создан: {exc}")

    return result
