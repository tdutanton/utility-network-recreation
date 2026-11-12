"""Сцена: примитивы в миллиметрах листа (1 единица = 1 мм бумаги).

Одна сцена — два бэкенда: DXF (netsketch/dxfout.py) и растр/PDF
(netsketch/render.py). Это гарантирует, что DWG и PDF совпадают.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

Point = tuple[float, float]


@dataclass
class Prim:
    layer: str = "0"
    color: int | None = None  # ACI; None — «по слою»
    lw: float | None = None  # толщина, мм
    state: str = "CONFIRMED"


@dataclass
class Line(Prim):
    a: Point = (0.0, 0.0)
    b: Point = (0.0, 0.0)


@dataclass
class Polyline(Prim):
    points: list[Point] = field(default_factory=list)
    closed: bool = False


@dataclass
class Circle(Prim):
    c: Point = (0.0, 0.0)
    r: float = 1.0


@dataclass
class Arc(Prim):
    c: Point = (0.0, 0.0)
    r: float = 1.0
    a0: float = 0.0
    a1: float = 180.0


@dataclass
class Solid(Prim):
    """Заливка (треугольник/квад). Точки — по порядку обхода."""

    points: list[Point] = field(default_factory=list)


@dataclass
class Hatch(Prim):
    boundary: list[Point] = field(default_factory=list)
    pattern: str = "SOLID"


@dataclass
class Text(Prim):
    text: str = ""
    at: Point = (0.0, 0.0)  # левый низ (или центр — см. align)
    height: float = 2.5
    rotation: float = 0.0
    width_factor: float = 1.0
    align: str = "left"  # left | center | right
    valign: str = "bottom"  # bottom | middle | top
    bold: bool = False


@dataclass
class Insert(Prim):
    name: str = ""
    at: Point = (0.0, 0.0)
    rotation: float = 0.0
    scale: float = 1.0


@dataclass
class DimLinear(Prim):
    """Линейный размер. p1/p2 — измеряемые точки, base — линия размера."""

    p1: Point = (0.0, 0.0)
    p2: Point = (0.0, 0.0)
    base: Point | None = None
    text: str | None = None
    angle: float = 0.0


@dataclass
class Scene:
    prims: list[Prim] = field(default_factory=list)
    blocks: dict[str, list[Prim]] = field(default_factory=dict)

    def add(self, prim: Prim) -> Prim:
        self.prims.append(prim)
        return prim

    def extend(self, prims: Sequence[Prim]) -> None:
        self.prims.extend(prims)

    def bbox(self) -> tuple[float, float, float, float] | None:
        xs: list[float] = []
        ys: list[float] = []
        for p in self.prims:
            for x, y in _prim_points(p):
                xs.append(x)
                ys.append(y)
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    def count(self) -> int:
        return len(self.prims)


def _prim_points(p: Prim) -> list[Point]:
    if isinstance(p, Line):
        return [p.a, p.b]
    if isinstance(p, Polyline):
        return list(p.points)
    if isinstance(p, Circle):
        return [(p.c[0] - p.r, p.c[1] - p.r), (p.c[0] + p.r, p.c[1] + p.r)]
    if isinstance(p, Arc):
        return [(p.c[0] - p.r, p.c[1] - p.r), (p.c[0] + p.r, p.c[1] + p.r)]
    if isinstance(p, Solid):
        return list(p.points)
    if isinstance(p, Hatch):
        return list(p.boundary)
    if isinstance(p, Text):
        w = text_width(p.text, p.height, p.width_factor)
        x, y = p.at
        if p.align == "center":
            x -= w / 2
        elif p.align == "right":
            x -= w
        if p.valign == "middle":
            y -= p.height / 2
        elif p.valign == "top":
            y -= p.height
        return [(x, y), (x + w, y + p.height)]
    if isinstance(p, Insert):
        return [p.at]
    if isinstance(p, DimLinear):
        return [p.p1, p.p2] + ([p.base] if p.base else [])
    return []


def text_width(text: str, height: float, width_factor: float = 1.0) -> float:
    """Оценка ширины строки. Для кириллицы ~0.62·h на символ."""
    if not text:
        return 0.0
    widest = 0.0
    for line in text.split("\n"):
        width = 0.0
        for ch in line:
            if ch in " .,:;'`|!":
                width += 0.30
            elif ch in "iljI1":
                width += 0.34
            elif ch.isupper() or ch in "ЖШЩЮМФЫ":
                width += 0.72
            elif ch in "mwMWШЩЮ":
                width += 0.78
            else:
                width += 0.58
        widest = max(widest, width)
    return widest * height * width_factor


def rotate_point(p: Point, origin: Point, angle_deg: float) -> Point:
    if not angle_deg:
        return p
    a = math.radians(angle_deg)
    dx, dy = p[0] - origin[0], p[1] - origin[1]
    return (
        origin[0] + dx * math.cos(a) - dy * math.sin(a),
        origin[1] + dx * math.sin(a) + dy * math.cos(a),
    )


def rotate_poly(points: Sequence[Point], origin: Point, angle_deg: float) -> list[Point]:
    return [rotate_point(p, origin, angle_deg) for p in points]
