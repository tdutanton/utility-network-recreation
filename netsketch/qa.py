"""Проверка результата: файлы на месте, PDF не пустой, элементы не потеряны."""

from __future__ import annotations

from pathlib import Path

from .model import Model


def _non_white_ratio(png_path: Path) -> float:
    from PIL import Image

    with Image.open(png_path) as img:
        img = img.convert("L")
        img.thumbnail((700, 700))
        pixels = list(img.getdata())
    dark = sum(1 for p in pixels if p < 245)
    return dark / max(len(pixels), 1)


def check_build(model: Model, files: dict[str, str], info, sheet) -> tuple[list[str], list[str]]:
    """Возвращает (ошибки, предупреждения)."""
    errors: list[str] = []
    warnings: list[str] = list(getattr(info, "warnings", []))

    for key in ("dxf", "pdf", "png", "dwg"):
        path = files.get(key)
        if not path:
            if key == "dwg":
                warnings.append("DWG не создан (см. ошибку конвертации)")
            else:
                errors.append(f"не создан файл: {key}")
            continue
        p = Path(path)
        if not p.exists():
            errors.append(f"файл {key} отсутствует на диске")
        elif p.stat().st_size < 400:
            errors.append(f"файл {key} подозрительно мал ({p.stat().st_size} байт)")

    png = files.get("png")
    if png and Path(png).exists():
        try:
            ratio = _non_white_ratio(Path(png))
            if ratio < 0.002:
                errors.append("предпросмотр почти пустой — план не нарисован")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"не удалось проверить PNG: {exc}")

    pdf = files.get("pdf")
    if pdf and Path(pdf).exists():
        try:
            import pymupdf

            doc = pymupdf.open(pdf)
            if doc.page_count != 1:
                warnings.append(f"PDF содержит {doc.page_count} страниц вместо 1")
            rect = doc[0].rect
            got = (round(rect.width / 72 * 25.4), round(rect.height / 72 * 25.4))
            want = (round(sheet.width), round(sheet.height))
            if abs(got[0] - want[0]) > 2 or abs(got[1] - want[1]) > 2:
                warnings.append(f"размер PDF {got[0]}×{got[1]} мм не совпадает с листом {want[0]}×{want[1]} мм")
            doc.close()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"не удалось проверить PDF: {exc}")

    if model.elements and getattr(info, "drawn_elements", 0) < len(model.elements):
        warnings.append("часть элементов не отрисована — проверьте предпросмотр")

    for note in model.warnings:
        warnings.append(f"распознавание: {note}")

    return errors, warnings
