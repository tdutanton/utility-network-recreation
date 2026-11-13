#!/usr/bin/env python
"""ГОСТ 2.104-2006: рамка и основная надпись (форма 1 и форма 2).

Скрипт рисует лист в миллиметрах бумаги и умеет отдавать:
  * DXF — для Open CAD Studio / AutoCAD;
  * PDF и PNG — для проверки глазами;
  * A4-портрет PDF — как печатают листы в examples/gas/1
    (A3-альбом повёрнут на 90° по часовой стрелке и вписан в A4).

Координаты штампа повторяют фактический шаблон из examples/gas/1:
185×55, левая часть 65 мм — таблица изменений и подписи,
правая 120 мм — шифр, адрес, объект, стадия/лист/листов, организация.

Примеры:
    python gost_sheet.py --demo --out sheet
    python gost_sheet.py --demo --out sheet --print-a4
    python gost_sheet.py --fields fields.json --stamp left --out sheet
    python gost_sheet.py --format A4 --stamp vertical --out a4

Требования: ezdxf, matplotlib (есть в .pydeps проекта).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

# ---------------------------------------------------------------------------
# Геометрия листа, мм
# ---------------------------------------------------------------------------

FORMATS: dict[str, tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A2": (420.0, 594.0),
    "A1": (594.0, 841.0),
    "A0": (841.0, 1189.0),
}

MARGIN_LEFT = 20.0
MARGIN_OTHER = 5.0
STAMP_W = 185.0
STAMP_H = 55.0

# Высоты текста, мм (фактические для эталонных листов)
H_LABEL = 2.5
H_VALUE = 3.5
H_SMALL = 1.9
H_OBJECT = 1.43
H_ADDRESS = 2.86
H_CIPHER = 3.5
H_ORG = 2.86
H_CITY = 3.5


# ---------------------------------------------------------------------------
# Сцена
# ---------------------------------------------------------------------------

@dataclass
class Line:
    a: tuple[float, float]
    b: tuple[float, float]
    width: float = 0.25


@dataclass
class Text:
    value: str
    x: float
    y: float
    height: float
    align: str = "left"       # left | center | right
    rotation: float = 0.0
    bold: bool = False
    italic: bool = False
    serif: bool = False


@dataclass
class Scene:
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)

    def line(self, a, b, width=0.25):
        self.lines.append(Line(tuple(a), tuple(b), width))

    def rect(self, x0, y0, x1, y1, width=0.25):
        self.line((x0, y0), (x1, y0), width)
        self.line((x1, y0), (x1, y1), width)
        self.line((x1, y1), (x0, y1), width)
        self.line((x0, y1), (x0, y0), width)

    def text(self, value, x, y, height, **kwargs):
        if value:
            self.texts.append(Text(str(value), float(x), float(y), float(height), **kwargs))


# ---------------------------------------------------------------------------
# Поля штампа
# ---------------------------------------------------------------------------

DEFAULT_FIELDS: dict[str, object] = {
    "cipher": "09/11ПР-2026-ИОС6",
    "address": "город Великий Новгород, ул. Красилова, д. 51/28",
    "object": [
        "Капитальный ремонт систем газоснабжения многоквартирного жилого",
        "дома по адресу: г. Великий Новгород, ул. Красилова, д. 51/28",
    ],
    "stage": "ИД",
    "sheet": "1",
    "total": "9",
    "organization": ['ООО "Новгородаудит-ЭНЕРГО"', "Великий Новгород"],
    "developer": "Евгеньев А.А.",
    "checker": "",
    "gip": "",
    "ncontrol": "",
    "date": "10.26",
    "drawing": [
        "Исполнительная схема.",
        "Схема сварных соединений.",
        "Наружные газопроводы",
    ],
}


def _field(fields: dict, key: str, default=""):
    value = fields.get(key, default)
    return value


def _as_lines(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value if str(v).strip()]


def text_width(value: str, height: float) -> float:
    """Грубая ширина строки Arial: 0,62·h на знак."""
    return 0.62 * height * len(value)


def fit_height(value: str, height: float, max_width: float, minimum: float = 1.2) -> float:
    if not value:
        return height
    width = text_width(value, height)
    if width <= max_width:
        return height
    return max(minimum, height * max_width / width)


def wrap(value: str, height: float, max_width: float) -> list[str]:
    words = value.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        probe = current + " " + word
        if text_width(probe, height) <= max_width:
            current = probe
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# Штамп 185×55
# ---------------------------------------------------------------------------

def _stamp_grid(scene: Scene, ox: float, oy: float, rot: float) -> None:
    """Сетка штампа в локальных координатах (0..185, 0..55)."""

    def L(x1, y1, x2, y2, w=0.25):
        scene.line(_tf(ox, oy, rot, (x1, y1)), _tf(ox, oy, rot, (x2, y2)), w)

    outer = 0.6
    # внешний контур
    L(0, 0, 185, 0, outer)
    L(185, 0, 185, 55, outer)
    L(185, 55, 0, 55, outer)
    L(0, 55, 0, 0, outer)

    # левая часть: таблица изменений и подписи
    L(10, 30, 10, 55, 0.18)
    L(20, 0, 20, 55, 0.18)
    L(30, 30, 30, 55, 0.18)
    L(40, 0, 40, 55, 0.18)
    L(55, 0, 55, 55, 0.18)
    L(65, 0, 65, 55, 0.35)
    for y in range(5, 55, 5):
        L(0, y, 65, y, 0.18)

    # правая часть
    L(65, 45, 185, 45, 0.18)   # низ шифра / верх адреса
    L(65, 30, 185, 30, 0.18)   # верх объекта и стадии
    L(65, 15, 185, 15, 0.18)   # низ объекта / верх названия
    L(135, 0, 135, 30, 0.18)   # левая граница стадии и организации
    L(150, 15, 150, 30, 0.18)
    L(165, 15, 165, 30, 0.18)
    L(135, 25, 185, 25, 0.18)  # шапка стадия/лист/листов


def _tf(ox: float, oy: float, rot: float, p: tuple[float, float]) -> tuple[float, float]:
    """Локальные координаты штампа -> лист."""
    x, y = p
    if rot == 0:
        return (ox + x, oy + y)
    if rot == 90:  # форма 2: штамп вертикально, текст читается снизу вверх
        return (ox + (STAMP_H - y), oy + x)
    if rot == -90:
        return (ox + y, oy + (STAMP_W - x))
    raise ValueError("rot must be 0, 90 or -90")


def _stamp_text(scene: Scene, ox, oy, rot, value, x, y, height, **kwargs):
    if not value:
        return
    px, py = _tf(ox, oy, rot, (x, y))
    scene.text(
        value,
        px,
        py,
        height,
        rotation=(kwargs.pop("rotation", 0.0) + rot),
        **kwargs,
    )


def draw_stamp(scene: Scene, ox: float, oy: float, fields: dict, rot: float = 0) -> None:
    """Основная надпись 185×55 в точке (ox, oy) — левый нижний угол."""

    f = fields
    _stamp_grid(scene, ox, oy, rot)

    def T(value, x, y, h=H_LABEL, **kw):
        _stamp_text(scene, ox, oy, rot, value, x, y, h, **kw)

    # --- левая часть: шапка таблицы изменений ---
    T("Изм.", 2.15, 31.32)
    T("Кол.уч.", 10.66, 31.35)
    T("Лист", 21.63, 31.32)
    T("№ док.", 30.76, 31.32)
    T("Подп.", 44.19, 31.32)
    T("Дата", 56.77, 31.37)

    # --- левая часть: подписи ---
    T("Разработал", 1.05, 26.32)
    T("Проверил", 1.05, 21.32)
    T("ГИП", 1.05, 16.32)
    T("Н. контроль", 1.05, 6.32)
    T(_field(f, "developer"), 21.05, 26.32)
    T(_field(f, "checker"), 21.05, 21.32)
    T(_field(f, "gip"), 21.05, 16.32)
    T(_field(f, "ncontrol"), 21.05, 6.32)
    T(_field(f, "date"), 56.05, 26.32)

    # --- шифр ---
    cipher = str(_field(f, "cipher"))
    T(cipher, 125.0, 47.7, fit_height(cipher, H_CIPHER, 112.0), align="center")

    # --- адрес ---
    address = str(_field(f, "address"))
    T(address, 78.5, 40.0, fit_height(address, H_ADDRESS, 102.0))

    # --- объект: две строки мелким шрифтом ---
    obj_lines = _as_lines(_field(f, "object"))[:2]
    for i, line in enumerate(obj_lines):
        T(line, 66.2, 26.4 - i * 2.2, fit_height(line, H_OBJECT, 66.0))

    # --- стадия / лист / листов ---
    T("Стадия", 137.15, 26.32)
    T("Лист", 153.53, 26.32)
    T("Листов", 170.20, 26.39)
    T(str(_field(f, "stage")), 140.5, 18.39, H_VALUE, align="center")
    T(str(_field(f, "sheet")), 155.5, 18.39, H_VALUE, align="center")
    T(str(_field(f, "total")), 170.5, 18.39, H_VALUE, align="center")

    # --- название чертежа (3 строки) ---
    drawing = _as_lines(_field(f, "drawing"))[:3]
    for i, line in enumerate(drawing):
        T(line, 100.0, 13.28 - i * 2.55, fit_height(line, H_SMALL, 66.0), align="center")

    # --- организация и город ---
    org = _as_lines(_field(f, "organization"))[:2]
    if org:
        T(org[0], 160.0, 7.91, fit_height(org[0], H_ORG, 47.0), align="center")
    if len(org) > 1:
        T(org[1], 160.0, 2.35, fit_height(org[1], H_CITY, 47.0), align="center")


def draw_sheet(scene: Scene, fields: dict, *, stamp: str = "right") -> None:
    """Рамка A3/A4 + штамп. stamp: left | right | vertical."""
    w, h = scene.width, scene.height
    scene.rect(0, 0, w, h, 0.7)
    scene.rect(MARGIN_LEFT, MARGIN_OTHER, w - MARGIN_OTHER, h - MARGIN_OTHER, 0.6)

    if stamp == "vertical":
        # форма 2: 185 мм по вертикали, 55 мм по горизонтали, слева
        draw_stamp(scene, MARGIN_LEFT, MARGIN_OTHER, fields, rot=90)
    elif stamp == "left":
        draw_stamp(scene, MARGIN_LEFT, MARGIN_OTHER, fields, rot=0)
    elif stamp == "right":
        draw_stamp(scene, w - MARGIN_OTHER - STAMP_W, MARGIN_OTHER, fields, rot=0)
    else:
        raise ValueError("stamp must be left, right or vertical")


# ---------------------------------------------------------------------------
# Экспорт DXF
# ---------------------------------------------------------------------------

def save_dxf(scene: Scene, path: Path) -> None:
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4  # mm
    doc.header["$MEASUREMENT"] = 1
    for name, color, lw in (
        ("FRAME", 7, 0.7),
        ("STAMP", 7, 0.6),
        ("TEXT", 7, 0.25),
    ):
        if name not in doc.layers:
            doc.layers.add(name, color=color)
    if "GOST" not in doc.styles:
        doc.styles.add("GOST", font="arial.ttf")
    msp = doc.modelspace()
    for line in scene.lines:
        layer = "FRAME" if line.width >= 0.5 else "STAMP"
        msp.add_line(
            line.a,
            line.b,
            dxfattribs={"layer": layer, "lineweight": int(round(line.width * 100))},
        )
    for text in scene.texts:
        attribs = {
            "layer": "TEXT",
            "style": "GOST",
            "height": text.height,
            "rotation": text.rotation,
        }
        entity = msp.add_text(text.value, dxfattribs=attribs)
        if text.align == "center":
            entity.set_placement((text.x, text.y), align=TextEntityAlignment.CENTER)
        elif text.align == "right":
            entity.set_placement((text.x, text.y), align=TextEntityAlignment.RIGHT)
        else:
            entity.set_placement((text.x, text.y), align=TextEntityAlignment.LEFT)
    doc.saveas(path)


# ---------------------------------------------------------------------------
# Экспорт PDF / PNG
# ---------------------------------------------------------------------------

def _font_families(serif: bool) -> list[str]:
    if serif:
        return ["Times New Roman", "Liberation Serif", "DejaVu Serif"]
    return ["Arial", "Liberation Sans", "DejaVu Sans"]


_FONT_CACHE: dict[bool, str] = {}


def _pick_font(serif: bool) -> str:
    """Первый реально установленный шрифт из списка (без спама findfont)."""
    if serif in _FONT_CACHE:
        return _FONT_CACHE[serif]
    import logging

    from matplotlib import font_manager

    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    chosen = "DejaVu Serif" if serif else "DejaVu Sans"
    for name in _font_families(serif):
        try:
            font_manager.findfont(font_manager.FontProperties(family=name), fallback_to_default=False)
            chosen = name
            break
        except Exception:
            continue
    _FONT_CACHE[serif] = chosen
    return chosen


def render_raster(
    scene: Scene,
    path: Path,
    *,
    page: tuple[float, float] | None = None,
    transform=None,
    rotation_delta: float = 0.0,
    dpi: int = 200,
    fmt: str | None = None,
) -> None:
    """Рисует сцену в PDF/PNG. transform(point)->point; page=(w,h) в мм."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    page_w, page_h = page or (scene.width, scene.height)
    fig = plt.figure(figsize=(page_w / 25.4, page_h / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.set_aspect("equal")
    ax.axis("off")

    def P(p):
        return transform(p) if transform else p

    for line in scene.lines:
        a = P(line.a)
        b = P(line.b)
        ax.plot(
            [a[0], b[0]],
            [a[1], b[1]],
            color="black",
            linewidth=line.width * 72.0 / 25.4,
            solid_capstyle="butt",
        )
    for text in scene.texts:
        x, y = P((text.x, text.y))
        ax.text(
            x,
            y,
            text.value,
            fontsize=text.height * 72.0 / 25.4,
            ha={"left": "left", "center": "center", "right": "right"}[text.align],
            va="baseline",
            rotation=text.rotation + rotation_delta,
            rotation_mode="anchor",
            family=_pick_font(text.serif),
            fontstyle="italic" if text.italic else "normal",
            fontweight="bold" if text.bold else "normal",
            color="black",
        )
    fig.savefig(path, dpi=dpi, facecolor="white", format=fmt)
    plt.close(fig)


def render_a4_portrait(scene: Scene, path: Path) -> None:
    """A3-альбом -> A4-портрет: поворот на 90° по часовой стрелке, масштаб 0,707."""
    if scene.width < scene.height:
        raise ValueError("--print-a4: исходный лист должен быть альбомным")
    w, h = scene.width, scene.height
    scale = min(210.0 / h, 297.0 / w)

    def tr(p):
        x, y = p
        return (y * scale, (w - x) * scale)

    render_raster(
        scene,
        path,
        page=(210.0, 297.0),
        transform=tr,
        rotation_delta=-90.0,
        dpi=220,
        fmt="pdf",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Рамка и основная надпись ГОСТ 2.104-2006")
    p.add_argument("--format", default="A3", choices=sorted(FORMATS))
    p.add_argument("--orientation", default="landscape", choices=["landscape", "portrait"])
    p.add_argument("--stamp", default="right", choices=["left", "right", "vertical"])
    p.add_argument("--fields", help="JSON с полями штампа (utf-8-sig)")
    p.add_argument("--out", default="gost_sheet", help="базовое имя выходных файлов")
    p.add_argument("--dxf", action="store_true", help="писать DXF")
    p.add_argument("--pdf", action="store_true", help="писать PDF")
    p.add_argument("--png", action="store_true", help="писать PNG")
    p.add_argument("--print-a4", action="store_true", help="дополнительно A4-портрет PDF")
    p.add_argument("--demo", action="store_true", help="заполнить поля примером")
    p.add_argument("--no-view", action="store_true", help="не печатать итоговые пути")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    base_w, base_h = FORMATS[args.format]
    if args.orientation == "landscape":
        w, h = base_h, base_w
    else:
        w, h = base_w, base_h

    if args.stamp == "vertical" and args.orientation != "portrait":
        print("вертикальный штамп — только для портретной ориентации", file=sys.stderr)
        return 2

    fields = dict(DEFAULT_FIELDS)
    if args.fields:
        with open(args.fields, "r", encoding="utf-8-sig") as fh:
            fields.update(json.load(fh))

    scene = Scene(w, h)
    draw_sheet(scene, fields, stamp=args.stamp)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    if args.dxf:
        path = out.with_suffix(".dxf")
        save_dxf(scene, path)
        written.append(path)
    if args.pdf:
        path = out.with_suffix(".pdf")
        render_raster(scene, path, fmt="pdf")
        written.append(path)
    if args.png:
        path = out.with_suffix(".png")
        render_raster(scene, path, fmt="png")
        written.append(path)
    if args.print_a4:
        path = out.with_name(out.name + "_A4_portrait.pdf")
        render_a4_portrait(scene, path)
        written.append(path)

    if not written:
        # по умолчанию — всё, что имеет смысл
        for path, func in (
            (out.with_suffix(".dxf"), lambda p: save_dxf(scene, p)),
            (out.with_suffix(".pdf"), lambda p: render_raster(scene, p, fmt="pdf")),
            (out.with_suffix(".png"), lambda p: render_raster(scene, p, fmt="png")),
        ):
            func(path)
            written.append(path)

    if not args.no_view:
        for path in written:
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
