"""Смоук-тест: проверяет весь путь без браузера и без модели зрения.

    python tools/smoke_test.py

Проверяет:
  1. сборку синтетических схем (газ, тепло) → DWG/PDF/PNG/DXF;
  2. что DWG читается обратно Open CAD Studio;
  3. что PDF имеет размер листа, а PNG не пустой;
  4. полный путь задачи: эскиз → model.json → чертёж.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from netsketch.config import load_settings  # noqa: E402
from netsketch.dwg import dwg_to_dxf  # noqa: E402
from netsketch.jobs import Job, JobStore  # noqa: E402
from netsketch.pipeline import Pipeline  # noqa: E402
from netsketch.qa import _non_white_ratio  # noqa: E402


def check(condition: bool, message: str, failures: list[str]) -> None:
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        failures.append(message)


def check_artifacts(files: dict[str, str], sheet: tuple[float, float], failures: list[str], tag: str) -> None:
    for kind in ("dxf", "pdf", "png", "dwg"):
        path = files.get(kind)
        check(bool(path) and Path(path).exists(), f"{tag}: {kind} создан", failures)

    pdf = files.get("pdf")
    if pdf and Path(pdf).exists():
        import pymupdf

        doc = pymupdf.open(pdf)
        rect = doc[0].rect
        size = (round(rect.width / 72 * 25.4), round(rect.height / 72 * 25.4))
        check(doc.page_count == 1, f"{tag}: PDF — одна страница", failures)
        check(
            abs(size[0] - sheet[0]) <= 2 and abs(size[1] - sheet[1]) <= 2,
            f"{tag}: PDF {size[0]}×{size[1]} мм соответствует листу",
            failures,
        )
        doc.close()

    png = files.get("png")
    if png and Path(png).exists():
        ratio = _non_white_ratio(Path(png))
        check(ratio > 0.002, f"{tag}: PNG не пустой ({ratio * 100:.1f}% штриха)", failures)

    dwg = files.get("dwg")
    if dwg and Path(dwg).exists():
        try:
            import ezdxf

            dxf = dwg_to_dxf(dwg, Path(dwg).with_suffix(".check.dxf"))
            doc = ezdxf.readfile(str(dxf))
            count = len(list(doc.modelspace()))
            check(count > 50, f"{tag}: DWG читается, сущностей {count}", failures)
            dxf.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            check(False, f"{tag}: DWG читается обратно ({exc})", failures)


def main() -> int:
    failures: list[str] = []
    settings = load_settings()
    print("NetSketch smoke test")
    print(f"  OCS: {settings.ocs_exe or 'не найден'}")
    if not settings.ocs_exe:
        print("  ВНИМАНИЕ: без Open CAD Studio DWG не проверить")

    import make_demo

    work = ROOT / "data" / "smoke"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    try:
        run_checks(settings, work, failures)
    finally:
        print(f"\nрабочая папка: {work}")

    print("\nитог:", "всё хорошо" if not failures else f"провалов {len(failures)}")
    return 0 if not failures else 1


def run_checks(settings, work: Path, failures: list[str]) -> None:
    import make_demo
    from netsketch.build import build_drawings
    from netsketch.model import model_from_dict
    from netsketch.sheets import Sheet

    for name, data in (("gas", make_demo.gas_model()), ("heat", make_demo.heat_model())):
        print(f"\n[{name}] синтетическая схема")
        model, _ = model_from_dict(data)
        res = build_drawings(model, work / name, stem=f"demo_{name}", title=model.title.__dict__)
        check_artifacts(res.files, (res.sheet.width, res.sheet.height), failures, name)

    print("\n[сквозной путь] эскиз examples/gas/1 + models/2_кв1_5.json → чертёж")
    store = JobStore(work / "jobs")
    job = Job(id="smoke0001", network_type="gas", sheet="A3", project="Смоук-тест", address="г. Тест")
    store.create(job)
    source = ROOT / "examples" / "gas" / "1" / "input" / "02_кв1_5.jpg"
    if source.exists():
        (store.job_dir(job.id) / "input" / source.name).write_bytes(source.read_bytes())
        job.inputs = [source.name]
    model_src = ROOT / "examples" / "gas" / "1" / "models" / "2_кв1_5.json"
    (store.job_dir(job.id) / "model.json").write_text(model_src.read_text(encoding="utf-8-sig"), encoding="utf-8")
    store.save(job)

    pipeline = Pipeline(settings, store)
    pipeline.process(job.id)
    job = store.load(job.id)
    check(job.status == "done", f"задача завершена (статус {job.status}: {job.error})", failures)
    if job.files:
        check_artifacts(job.files, (210, 297), failures, "job")

    print("\n[листы] A4, A3, A2")
    model, _ = model_from_dict(make_demo.gas_model())
    for fmt in ("A4", "A3", "A2"):
        sheet = Sheet(fmt, "landscape")
        res = build_drawings(model, work / f"sheet_{fmt}", stem=f"s_{fmt}", sheet=sheet, make_dwg=False)
        check(Path(res.files["png"]).exists(), f"{fmt}: PNG построен", failures)
        check(
            abs(res.sheet.width - sheet.width) < 0.1 and abs(res.sheet.height - sheet.height) < 0.1,
            f"{fmt}: размер листа {res.sheet.width:.0f}×{res.sheet.height:.0f} мм",
            failures,
        )

    print("\n[схема] лист ГОСТ: A3-альбом, штамп 185×55, печать A4-портрет")
    model, _ = model_from_dict(make_demo.gas_model())
    res = build_drawings(model, work / "schematic", stem="schematic", mode="schematic")
    check(res.info.mode == "schematic", f"режим {res.info.mode}", failures)
    check(res.info.stamp_corner in {"left", "right"}, f"угол штампа выбран: {res.info.stamp_corner}", failures)
    check(
        abs(res.sheet.width - 420) < 0.1 and abs(res.sheet.height - 297) < 0.1,
        f"лист схемы {res.sheet.width:.0f}×{res.sheet.height:.0f} мм (A3-альбом)",
        failures,
    )
    check_artifacts(res.files, (420, 297), failures, "schematic")
    for kind in ("pdf_a4", "png_a4"):
        path = res.files.get(kind)
        check(bool(path) and Path(path).exists(), f"schematic: {kind} создан", failures)
    for kind, expected in (("pdf", (420, 297)), ("pdf_a4", (210, 297))):
        path = res.files.get(kind)
        if not path:
            continue
        import pymupdf

        doc = pymupdf.open(path)
        rect = doc[0].rect
        size = (round(rect.width / 72 * 25.4), round(rect.height / 72 * 25.4))
        check(
            abs(size[0] - expected[0]) <= 2 and abs(size[1] - expected[1]) <= 2,
            f"schematic: {kind} — {size[0]}×{size[1]} мм",
            failures,
        )
        doc.close()


if __name__ == "__main__":
    raise SystemExit(main())


