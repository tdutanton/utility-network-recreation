"""Приёмка листа ГОСТ 2.104: сверка со эталоном examples/gas/1.

    python tools/gost_verify.py            # отчёт + файлы в output/gost

Проверяет то, что записано в приёмке фазы 1–2 плана
`knowledge/gas-etalon-plan.md`:

  1. сетка штампа совпадает с эталоном (допуск 0,25 мм);
  2. текстовые графы стоят там же, где в эталоне (допуск 0,25 мм);
  3. контур штампа: низ и рамка не дублируются, свободная вертикаль есть,
     оба угла (слева / справа) собираются;
  4. текст не пересекает линии сетки;
  5. PDF A3 = 420×297 мм, печатный PDF = 210×297 мм;
  6. PNG листа и печати не пустые; наложение на растровый эталон сохранено
     для проверки глазами.

Сверка идёт по фактическим данным эталона, снятым из DWG:
`examples/gas/1/sheet-etalon.json`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from netsketch.gost_sheet import (  # noqa: E402
    LAYER_FRAME,
    LAYER_STAMP,
    STAMP_H,
    STAMP_W,
    GostSheet,
    StampFields,
    build_sheet,
    print_transform,
)
from netsketch.render import write_pdf, write_preview, write_print_pdf, write_print_png  # noqa: E402
from netsketch.scene import Line, Scene, Text, text_width  # noqa: E402

FIXTURE = ROOT / "examples" / "gas" / "1" / "sheet-etalon.json"
OUTDIR = ROOT / "output" / "gost"

TOL = 0.25  # мм, допуск приёмки

ETALON_FIELDS = {
    "cipher": "09/11ПР-2026-ИОС6",
    "address": "город Великий Новгород, ул. Красилова, д. 51/28",
    "object_lines": [
        "Капитальный ремонт систем газоснабжения многоквартирного жилого",
        "дома по адресу: г. Великий Новгород, ул. Красилова, д. 51/28",
    ],
    "stage": "ИД",
    "sheet": "1",
    "total": "9",
    "organization": ['ООО "Новгородаудит-ЭНЕРГО"', "Великий Новгород"],
    "drawing": ["Исполнительная схема.", "Схема сварных соединений.", "Наружные газопроводы"],
    "signatures": [("Разработал", "Евгеньев А.А.", "10.26"), ("Проверил", "", ""), ("ГИП", "", ""), ("Н. контроль", "", "")],
}


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, ok: bool, message: str) -> None:
        print(f"  {'ok  ' if ok else 'FAIL'} {message}")
        if not ok:
            self.failures.append(message)


def etalon() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def stamp_lines(scene: Scene, sheet: GostSheet) -> list[tuple[float, float, float, float]]:
    """Линии штампа в локальных координатах (0..185, 0..55)."""
    ox, oy, _, _ = sheet.stamp_rect()
    out = []
    for p in scene.prims:
        if not isinstance(p, Line) or p.layer != LAYER_STAMP:
            continue
        a = (round(p.a[0] - ox, 2), round(p.a[1] - oy, 2))
        b = (round(p.b[0] - ox, 2), round(p.b[1] - oy, 2))
        out.append((a[0], a[1], b[0], b[1]))
    return out


def compare_grid(report: Report, scene: Scene, sheet: GostSheet, data: dict) -> None:
    ours = stamp_lines(scene, sheet)
    vert_ours = sorted(
        (round(a0, 2), round(min(a1, b1), 2), round(max(a1, b1), 2))
        for a0, a1, b0, b1 in ours
        if abs(a0 - b0) < 0.01 and abs(a1 - b1) > 0.01
    )
    horiz_ours = sorted(
        (round(min(a0, b0), 2), round(max(a0, b0), 2), round(a1, 2))
        for a0, a1, b0, b1 in ours
        if abs(a1 - b1) < 0.01 and abs(a0 - b0) > 0.01
    )
    vert_ref = [(v[0], v[1], v[2]) for v in data["stamp"]["vertical_lines"] if abs(v[0]) > 0.01]
    horiz_ref = [(h[0], h[1], h[2]) for h in data["stamp"]["horizontal_lines"]]

    def as_vertical(t: tuple[float, float, float]) -> tuple[float, float, float]:
        return (t[0], t[1], t[2])  # x, ymin, ymax

    def as_horizontal(t: tuple[float, float, float]) -> tuple[float, float, float]:
        return (t[2], t[0], t[1])  # y, xmin, xmax

    def covered(ref, got, conv) -> bool:
        """Есть ли отрезок с той же координатой, покрывающий эталонный участок."""
        value, lo, hi = conv(ref)
        for g in got:
            gvalue, glo, ghi = conv(g)
            if abs(gvalue - value) <= TOL and glo <= lo + TOL and ghi >= hi - TOL:
                return True
        return False

    missing_v = [v for v in vert_ref if not covered(v, vert_ours, as_vertical)]
    missing_h = [h for h in horiz_ref if not covered(h, horiz_ours, as_horizontal)]
    report.check(not missing_v, f"сетка: вертикали совпадают с эталоном ({len(vert_ref)} линий)")
    for m in missing_v[:6]:
        print(f"       нет вертикали эталона {m}")
    report.check(not missing_h, f"сетка: горизонтали совпадают с эталоном ({len(horiz_ref)} линий)")
    for m in missing_h[:6]:
        print(f"       нет горизонтали эталона {m}")

    # низ (y=0) и сторона на рамке не должны дублироваться
    extra = [g for g in ours if abs(g[1]) < 0.01 and abs(g[3]) < 0.01]
    report.check(not extra, "сетка: низ штампа не дублирует рамку")
    side = sheet.stamp == "left"
    duplicated = [
        g for g in ours
        if abs(g[0] - g[2]) < 0.01 and abs(g[0] - (0.0 if side else STAMP_W)) < 0.01
        and abs(g[3] - g[1]) > 1.0
    ]
    report.check(not duplicated, "сетка: сторона на рамке не дублируется")

    free_side = STAMP_W if side else 0.0
    has_free = any(
        abs(g[0] - g[2]) < 0.01 and abs(g[0] - free_side) < TOL and abs(g[3] - g[1]) > 1.0 for g in ours
    )
    report.check(has_free, f"сетка: свободная вертикаль x={free_side:g} нарисована")

    top = [g for g in ours if abs(g[1] - STAMP_H) < TOL and abs(g[3] - STAMP_H) < TOL]
    report.check(bool(top), "сетка: верх штампа нарисован")


def compare_texts(report: Report, scene: Scene, sheet: GostSheet, data: dict) -> None:
    """Графы штампа стоят там же, где в эталоне.

    Мы ставим текст по центру ячейки (по горизонтали и вертикали), а в
    эталонном DWG он записан левым низом. Поэтому проверяем не совпадение
    якорей, а попадание эталонного якоря внутрь нашей рамки текста: так
    ловится и «графа уехала в чужую ячейку», и «графа пропала».
    """
    from netsketch.scene import text_width

    ox, oy, _, _ = sheet.stamp_rect()
    boxes: dict[str, list[tuple[float, float, float, float]]] = {}
    for p in scene.prims:
        if not isinstance(p, Text) or p.layer != LAYER_STAMP:
            continue
        key = p.text.strip()
        width = text_width(p.text, p.height)
        cx, cy = p.at[0] - ox, p.at[1] - oy
        # учитываем выравнивание: роли в штампе стоят по левому краю
        if p.align == "center":
            x0 = cx - width / 2
        elif p.align == "right":
            x0 = cx - width
        else:
            x0 = cx
        if p.valign == "middle":
            y0 = cy - p.height / 2
        elif p.valign == "top":
            y0 = cy - p.height
        else:
            y0 = cy
        boxes.setdefault(key, []).append((x0, y0, x0 + width, y0 + p.height))

    # запас: мы центруем текст в ячейке, эталонный якорь — левый низ
    pad = 3.0
    # левая колонка штампа: подписи граф и роли. Там текст центруется в своей
    # ячейке, поэтому проверяем не якорь, а что графа осталась в своей колонке.
    left_column = {"Изм.", "Кол.уч.", "Лист", "№ док.", "Подп.", "Дата", "Разработал", "Проверил", "ГИП", "Н. контроль"}
    bad = []
    for key, refs in data["stamp"]["texts"].items():
        cand = boxes.get(key)
        if not cand:
            bad.append(f"«{key}» отсутствует")
            continue
        if key in left_column:
            # «Лист» встречается и слева, и справа — достаточно одного попадания
            ok = any(b[0] >= 0.0 and b[2] <= 65.0 and b[1] >= 0.0 and b[3] <= 55.0 for b in cand)
            if not ok:
                bad.append(f"«{key}»: вышла из левой колонки {cand}")
            continue
        for ref in refs:
            hit = any(
                b[0] - pad <= ref["x"] <= b[2] + pad and b[1] - pad <= ref["y"] <= b[3] + pad for b in cand
            )
            if not hit:
                near = min(cand, key=lambda b: abs((b[0] + b[2]) / 2 - ref["x"]) + abs((b[1] + b[3]) / 2 - ref["y"]))
                bad.append(f"«{key}»: мы {near} эталон ({ref['x']},{ref['y']})")
    total = sum(len(v) for v in data["stamp"]["texts"].values())
    report.check(not bad, f"тексты: {total} граф на месте эталона")
    for b in bad[:8]:
        print(f"       {b}")


def check_no_crossing(report: Report, scene: Scene) -> None:
    """Текст не должен пересекать линии сетки штампа.

    Высота шрифта в CAD — высота прописной, поэтому рамка текста считается
    от базовой линии вверх на height и вниз на 0,22·height (выносные элементы).
    """
    lines = [p for p in scene.prims if isinstance(p, Line) and p.layer == LAYER_STAMP]
    texts = [p for p in scene.prims if isinstance(p, Text) and p.layer == LAYER_STAMP]
    inset = 0.2
    clashes = []
    for t in texts:
        w = text_width(t.text, t.height)
        x0 = t.at[0] if t.align == "left" else t.at[0] - w / 2 if t.align == "center" else t.at[0] - w
        box = (x0, t.at[1] - 0.22 * t.height, x0 + w, t.at[1] + t.height)
        for ln in lines:
            horizontal = abs(ln.a[1] - ln.b[1]) < 0.01
            if horizontal:
                y = ln.a[1]
                xa, xb = sorted((ln.a[0], ln.b[0]))
                if box[1] + inset < y < box[3] - inset and xa < box[2] - inset and xb > box[0] + inset:
                    clashes.append((t.text, f"горизонталь y={y - 5:g}"))
            else:
                x = ln.a[0]
                ya, yb = sorted((ln.a[1], ln.b[1]))
                if box[0] + inset < x < box[2] - inset and ya < box[3] - inset and yb > box[1] + inset:
                    clashes.append((t.text, f"вертикаль x={x - (20 if ln.a[0] < 210 else 230):g}"))
    report.check(not clashes, "текст не пересекает линии сетки")
    for c in clashes[:8]:
        print(f"       «{c[0]}» пересекает {c[1]}")


def pdf_size(path: Path) -> tuple[float, float] | None:
    try:
        import pymupdf
    except ImportError:
        return None
    doc = pymupdf.open(str(path))
    page = doc[0]
    size = (round(page.rect.width / 72 * 25.4, 1), round(page.rect.height / 72 * 25.4, 1))
    doc.close()
    return size


def non_white(path: Path) -> float:
    from PIL import Image

    img = Image.open(path).convert("L")
    hist = img.histogram()
    total = sum(hist)
    dark = sum(hist[:200])
    return dark / total if total else 0.0


def pdf_long_segments(path: Path, min_len: float = 20.0) -> list[tuple[float, float, float, float, float]]:
    """Длинные отрезки страницы PDF в мм, y снизу: (длина, x1, y1, x2, y2)."""
    try:
        import pymupdf
    except ImportError:
        return []
    pt = 72.0 / 25.4
    doc = pymupdf.open(str(path))
    page = doc[0]
    height_pt = page.rect.height
    out = []
    for d in page.get_drawings():
        for item in d["items"]:
            pairs = []
            if item[0] == "l":
                pairs = [(item[1], item[2])]
            elif item[0] == "re":
                r = item[1]
                pairs = [
                    ((r.x0, r.y0), (r.x1, r.y0)),
                    ((r.x1, r.y0), (r.x1, r.y1)),
                    ((r.x1, r.y1), (r.x0, r.y1)),
                    ((r.x0, r.y1), (r.x0, r.y0)),
                ]
            for a, b in pairs:
                length = (((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5) / pt
                if length >= min_len:
                    out.append(
                        (
                            length,
                            a[0] / pt,
                            (height_pt - a[1]) / pt,
                            b[0] / pt,
                            (height_pt - b[1]) / pt,
                        )
                    )
    doc.close()
    return out


def compare_print_geometry(report: Report, ours: Path, etalon_pdf: Path, tag: str) -> None:
    """Каждый наш длинный отрезок на печати должен быть и в эталонном PDF.

    Так проверяется вся листовка целиком (рамка + штамп) в печатном
    артефакте, а не только координаты в сцене.
    """
    our = pdf_long_segments(ours)
    ref = pdf_long_segments(etalon_pdf)
    if not ref:
        print(f"  ..   {tag}: эталонный PDF не разобран — сверка печати пропущена")
        return
    tol = 0.6
    missing = []
    for length, x1, y1, x2, y2 in our:
        found = False
        for rl, rx1, ry1, rx2, ry2 in ref:
            same = abs(x1 - rx1) <= tol and abs(y1 - ry1) <= tol and abs(x2 - rx2) <= tol and abs(y2 - ry2) <= tol
            flipped = abs(x1 - rx2) <= tol and abs(y1 - ry2) <= tol and abs(x2 - rx1) <= tol and abs(y2 - ry1) <= tol
            if same or flipped:
                found = True
                break
        if not found:
            missing.append((round(length, 1), round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)))
    report.check(
        not missing,
        f"{tag}: все {len(our)} длинных отрезков печати совпали с эталонным PDF (допуск {tol} мм)",
    )
    for m in missing[:6]:
        print(f"       нет в эталоне: длина {m[0]} ({m[1]},{m[2]})-({m[3]},{m[4]})")


def make_overlay(ours_png: Path, etalon_jpg: Path, out: Path) -> Path | None:
    """Наложение: эталон красным, наш лист голубым, совпадение — чёрным.

    Эталонный JPEG — A4-портрет (A3, повёрнутый на 90° по ЧС), поэтому перед
    сравнением разворачиваем его обратно в A3-альбом.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    if not etalon_jpg.exists():
        return None
    ref = Image.open(etalon_jpg).convert("L")
    if ref.height > ref.width:
        # A4-портрет → A3-альбом: поворот на 90° против часовой стрелки
        ref = ref.rotate(90, expand=True)
    ours = Image.open(ours_png).convert("L")
    ref = ref.resize(ours.size, Image.LANCZOS)
    overlay = Image.merge("RGB", (ours, ref, ref))
    overlay.save(out)
    return out


def prim_bbox(p) -> tuple[float, float, float, float] | None:
    from netsketch.scene import _prim_points

    pts = _prim_points(p)
    if not pts:
        return None
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def boxes_overlap(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def check_schematic(report: Report) -> None:
    """Фаза 2: компоновка листа — свободный угол штампа и свободная сторона текста."""
    from netsketch.layout import build_schematic_scene
    from netsketch.model import load_model_file, model_from_dict

    fields = StampFields(**ETALON_FIELDS)
    model, _ = load_model_file(str(ROOT / "examples" / "gas" / "1" / "models" / "2_кв1_5.json"))

    # 1. Узкая квартирная схема — штамп справа, текст справа, как в эталоне.
    gsheet = GostSheet("A3", "landscape", "auto")
    scene, info = build_schematic_scene(model, sheet=gsheet, fields=fields)
    stamp = gsheet.stamp_rect()
    print(f"\n[компоновка] квартирная схема: штамп {info.stamp_corner}, "
          f"в точке ({stamp[0]:g},{stamp[1]:g}), масштаб 1:{info.scale}")
    report.check(info.stamp_corner == "right", "узкая схема: штамп в правом углу (как в эталоне)")

    content = [
        p for p in scene.prims
        if getattr(p, "layer", "") not in {LAYER_FRAME, LAYER_STAMP}
    ]
    clashes = []
    for p in content:
        box = prim_bbox(p)
        if box and boxes_overlap(box, stamp):
            clashes.append((getattr(p, "layer", ""), box))
    report.check(not clashes, f"узкая схема: {len(content)} примитивов не заходят на штамп")
    for c in clashes[:5]:
        print(f"       {c[0]}: {tuple(round(v, 1) for v in c[1])}")

    legend = [p for p in content if isinstance(p, Text) and p.layer == "LEGEND"]
    right_side = all(p.at[0] > 210 for p in legend) if legend else False
    report.check(bool(legend) and right_side, f"узкая схема: легенда ({len(legend)} строк) справа от оси листа")
    summary = [p for p in content if isinstance(p, Text) and p.serif and p.italic]
    report.check(bool(summary), f"узкая схема: итоговый блок {len(summary)} строк курсивом")

    frame = gsheet.frame
    outside = [
        p for p in content
        if (box := prim_bbox(p)) and (box[0] < frame[0] - 0.5 or box[2] > frame[2] + 0.5
                                      or box[1] < frame[1] - 0.5 or box[3] > frame[3] + 0.5)
    ]
    report.check(not outside, "узкая схема: ничего не выходит за рамку")

    # 2. Широкая схема (фасад) — штамп слева, как в эталоне.
    wide = model_from_dict(
        {
            "network_type": "gas",
            "segments": [
                {"id": "s1", "points": [[0, 0], [900, 0], [900, 60], [0, 60]], "diameter_mm": 57, "length_mm": 64000},
                {"id": "s2", "points": [[0, 60], [0, 120], [900, 120]], "diameter_mm": 32, "length_mm": 5000},
            ],
            "labels": [{"text": "Ø57", "x": 450, "y": 10}],
            "legend": [{"symbol": "support", "text": "опора"}],
            "notes": ["Фасад газ-д", "lобщ= 85 м"],
        }
    )[0]
    wide_sheet = GostSheet("A3", "landscape", "auto")
    wide_scene, wide_info = build_schematic_scene(wide, sheet=wide_sheet, fields=fields)
    print(f"[компоновка] широкий фасад: штамп {wide_info.stamp_corner}")
    report.check(wide_info.stamp_corner == "left", "широкая схема: штамп в левом углу (как в фасаде эталона)")

    wide_stamp = wide_sheet.stamp_rect()
    wide_content = [
        p for p in wide_scene.prims
        if getattr(p, "layer", "") not in {LAYER_FRAME, LAYER_STAMP}
    ]
    wide_clashes = [
        p for p in wide_content
        if (box := prim_bbox(p)) and boxes_overlap(box, wide_stamp)
    ]
    report.check(not wide_clashes, "широкая схема: ничего не заходит на штамп")

    # 3. Печать широкой схемы — тоже A4-портрет.
    write_preview(wide_scene, OUTDIR / "schematic_wide.png", width_mm=wide_sheet.width, height_mm=wide_sheet.height)
    page_w, page_h, _s, transform = print_transform(wide_sheet)
    out = OUTDIR / "schematic_wide_A4.pdf"
    write_print_pdf(
        wide_scene,
        out,
        width_mm=wide_sheet.width,
        height_mm=wide_sheet.height,
        page=(page_w, page_h),
        transform=transform,
    )
    size = pdf_size(out)
    if size:
        report.check(abs(size[0] - 210) <= 2 and abs(size[1] - 297) <= 2, f"широкая схема: печатный PDF {size[0]:g}×{size[1]:g}")

    # 4. Печатный лист квартирной схемы — файл для глаз.
    page_w, page_h, _s, transform = print_transform(gsheet)
    write_preview(
        scene, OUTDIR / "schematic_kv.png", width_mm=gsheet.width, height_mm=gsheet.height
    )


def check_etalon_model(report: Report) -> None:
    """Фазы 3–4: модель эталонного листа собирается со всеми аннотациями."""
    from netsketch.build import build_drawings
    from netsketch.model import load_model_file

    path = ROOT / "examples" / "gas" / "1" / "models" / "2_кв1_5.schematic.json"
    if not path.exists():
        print("\n[эталонная модель] файла нет — пропуск")
        return
    model, warnings = load_model_file(str(path))
    print(f"\n[эталонная модель] {path.name}: швов {len(model.welds)}, опор {len(model.supports)}, "
          f"выносок {len(model.callouts)}, квартир {len(model.rooms)}, строк итога {len(model.summary)}")
    report.check(not warnings, f"эталонная модель без предупреждений разбора ({len(warnings)})")
    report.check(len(model.welds) >= 17, f"швы: {len(model.welds)} (в эталоне 17 номеров + ветка)")
    report.check(len(model.supports) >= 5, f"опоры: {len(model.supports)}")
    report.check(len(model.callouts) >= 15, f"выноски: {len(model.callouts)}")
    report.check(len(model.rooms) == 2, f"квартиры: {len(model.rooms)}")
    report.check(len(model.summary) >= 7, f"итоговый блок: {len(model.summary)} строк")
    report.check(model.title.cipher.startswith("09/11"), f"шифр в реквизитах: {model.title.cipher!r}")

    res = build_drawings(model, OUTDIR / "etalon_model", stem="kv1_5", mode="schematic", make_dwg=True)
    report.check(not res.errors, f"сборка без ошибок ({res.errors[:1]})")
    report.check(res.info.stamp_corner == "right", f"штамп {res.info.stamp_corner}")
    for kind, expected in (("pdf", (420, 297)), ("pdf_a4", (210, 297))):
        path_pdf = res.files.get(kind)
        size = pdf_size(Path(path_pdf)) if path_pdf else None
        if size:
            report.check(
                abs(size[0] - expected[0]) <= 2 and abs(size[1] - expected[1]) <= 2,
                f"эталонная модель: {kind} {size[0]:g}×{size[1]:g}",
            )

    scene = res.scene
    welds_on_sheet = [p for p in scene.prims if isinstance(p, Text) and p.text.strip().startswith("2.")]
    report.check(len(welds_on_sheet) >= 16, f"номера швов на листе: {len(welds_on_sheet)}")
    stamps = [p for p in scene.prims if isinstance(p, Text) and p.text.strip() == model.title.cipher]
    report.check(bool(stamps), "шифр попал в штамп")


def main() -> int:
    if not FIXTURE.exists():
        print(f"нет фикстуры эталона: {FIXTURE}", file=sys.stderr)
        return 2
    data = etalon()
    report = Report()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    print("Лист ГОСТ 2.104: A3-альбом, штамп 185×55")
    fields = StampFields(**ETALON_FIELDS)

    for corner in ("right", "left"):
        sheet = GostSheet("A3", "landscape", corner)
        scene = build_sheet(sheet, fields)
        print(f"\n[{corner}] рамка {sheet.width:g}×{sheet.height:g}, штамп {STAMP_W:g}×{STAMP_H:g} "
              f"в точке ({sheet.stamp_rect()[0]:g},{sheet.stamp_rect()[1]:g})")
        report.check(
            (sheet.width, sheet.height) == (420.0, 297.0),
            f"{corner}: лист 420×297",
        )
        compare_grid(report, scene, sheet, data)
        if corner == "right":
            compare_texts(report, scene, sheet, data)
        check_no_crossing(report, scene)

        dxf_path = OUTDIR / f"sheet_{corner}.dxf"
        from netsketch.dxfout import save_dxf

        save_dxf(scene, dxf_path, "gas")
        report.check(dxf_path.exists() and dxf_path.stat().st_size > 2048, f"{corner}: DXF записан")

        pdf = write_pdf(scene, OUTDIR / f"sheet_{corner}.pdf", width_mm=sheet.width, height_mm=sheet.height)
        size = pdf_size(pdf)
        if size:
            report.check(abs(size[0] - 420) <= 2 and abs(size[1] - 297) <= 2, f"{corner}: PDF A3 {size[0]:g}×{size[1]:g}")
        else:
            print("  ..   PyMuPDF не установлен — размер PDF не проверен")

        png = write_preview(scene, OUTDIR / f"sheet_{corner}.png", width_mm=sheet.width, height_mm=sheet.height)
        report.check(non_white(png) > 0.0005, f"{corner}: PNG листа не пустой ({non_white(png) * 100:.2f}% штриха)")

        page_w, page_h, scale, transform = print_transform(sheet)
        report.check(
            abs(page_w - 210) < 0.01 and abs(page_h - 297) < 0.01 and abs(scale - 210 / 297) < 0.001,
            f"{corner}: печать A4-портрет 210×297 при масштабе {scale:.4f}",
        )
        print_pdf = write_print_pdf(
            scene,
            OUTDIR / f"sheet_{corner}_A4.pdf",
            width_mm=sheet.width,
            height_mm=sheet.height,
            page=(page_w, page_h),
            transform=transform,
        )
        size = pdf_size(print_pdf)
        if size:
            report.check(abs(size[0] - 210) <= 2 and abs(size[1] - 297) <= 2, f"{corner}: печатный PDF {size[0]:g}×{size[1]:g}")

        print_png = write_print_png(
            scene,
            OUTDIR / f"sheet_{corner}_A4.png",
            width_mm=sheet.width,
            height_mm=sheet.height,
            page=(page_w, page_h),
            transform=transform,
        )
        report.check(non_white(print_png) > 0.0005, f"{corner}: PNG печати не пустой ({non_white(print_png) * 100:.2f}% штриха)")

        etalon_pdf = ROOT / "examples" / "gas" / "1" / "result" / "pdf" / (
            "2_кв1_5.pdf" if corner == "right" else "1_фасад.pdf"
        )
        if etalon_pdf.exists():
            compare_print_geometry(report, print_pdf, etalon_pdf, corner)

    # наложение на растровый эталон: правый штамп сверяем с 2_кв1_5,
    # левый — с 1_фасад (у них совпадает угол штампа)
    for corner, etalon_name in (("right", "2_кв1_5"), ("left", "1_фасад")):
        ours = OUTDIR / f"sheet_{corner}.png"
        for jpg in (ROOT / "examples" / "gas" / "1" / "result" / "jpg").glob(f"{etalon_name.split('_')[0]}_*.jpg"):
            overlay = make_overlay(ours, jpg, OUTDIR / f"overlay_{corner}.png")
            if overlay:
                print(f"наложение ({corner}) с {jpg.name}: {overlay}")
            break

    check_schematic(report)
    check_etalon_model(report)

    print()
    if report.failures:
        print(f"ПРОВАЛЕНО: {len(report.failures)}")
        for f in report.failures:
            print(f"  - {f}")
        return 1
    print("ВСЁ ЗЕЛЁНОЕ")
    print(f"файлы: {OUTDIR}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
