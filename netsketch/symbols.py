"""Библиотека условных обозначений.

Символы рисуются в масштабе листа: базовый размер `size` мм (по умолчанию 4).
Функция возвращает примитивы, добавленные в сцену, — их можно подсветить
или посчитать в QA.
"""

from __future__ import annotations

import math

from .scene import Arc, Circle, Hatch, Line, Polyline, Prim, Scene, Solid, Text, rotate_poly


def _tri(a, b, c, **kw) -> Solid:
    return Solid(points=[a, b, c], **kw)


def draw_symbol(
    scene: Scene,
    etype: str,
    at: tuple[float, float],
    *,
    size: float = 4.0,
    rotation: float = 0.0,
    layer: str = "NET_EQUIP",
    state: str = "CONFIRMED",
    angle_along: float = 0.0,
) -> list[Prim]:
    """Рисует условное обозначение. `angle_along` — направление трубы (для ориентации)."""
    x, y = at
    s = size
    h = s / 2
    prims: list[Prim] = []
    kw = {"layer": layer, "state": state}

    def add(p: Prim) -> None:
        scene.add(p)
        prims.append(p)

    def rot(pts):
        return rotate_poly(pts, (x, y), rotation)

    if etype in {"valve", "gate_valve"}:
        # два сходящихся треугольника (задвижка). При rotation=0 «бабочка»
        # лежит ВДОЛЬ оси X: основания вертикальные на x±0,91h, ширина ±0,52h.
        add(_tri(*rot([(x - h * 0.91, y + h * 0.52), (x - h * 0.91, y - h * 0.52), (x, y)]), **kw))
        add(_tri(*rot([(x + h * 0.91, y + h * 0.52), (x + h * 0.91, y - h * 0.52), (x, y)]), **kw))
        add(Line(a=rot([(x, y - h * 0.9)])[0], b=rot([(x, y + h * 0.9)])[0], **kw))

    elif etype == "valve_ball":
        # кран: «бабочка» из двух сходящихся треугольников вдоль трубы
        # (в эталонных схемах кран рисуют так же, как задвижку, без кружка)
        add(_tri(*rot([(x - h * 0.91, y + h * 0.52), (x - h * 0.91, y - h * 0.52), (x, y)]), **kw))
        add(_tri(*rot([(x + h * 0.91, y + h * 0.52), (x + h * 0.91, y - h * 0.52), (x, y)]), **kw))

    elif etype == "filter":
        add(Polyline(points=rot([(x - h, y), (x, y + h), (x + h, y), (x, y - h)]), closed=True, **kw))
        add(Line(a=(x - h * 0.4, y), b=(x + h * 0.4, y), **kw))

    elif etype == "flowmeter":
        add(Circle(c=(x, y), r=h * 0.7, **kw))
        add(Line(a=(x - h * 0.45, y - h * 0.45), b=(x + h * 0.45, y + h * 0.45), **kw))
        add(Text(text="Р", at=(x, y - h * 0.55), height=h * 0.7, layer=layer, align="center", state=state))

    elif etype == "compensator":
        # П-образный компенсатор
        add(
            Polyline(
                points=rot(
                    [
                        (x - h, y),
                        (x - h * 0.6, y),
                        (x - h * 0.6, y + h * 0.9),
                        (x + h * 0.6, y + h * 0.9),
                        (x + h * 0.6, y),
                        (x + h, y),
                    ]
                ),
                **kw,
            )
        )

    elif etype == "support":
        add(Line(a=(x - h, y - h * 0.5), b=(x + h, y - h * 0.5), **kw))
        add(Line(a=(x - h, y - h * 0.5), b=(x - h * 0.5, y - h * 1.2), **kw))
        for i in range(4):
            xx = x - h + (i + 0.5) * (2 * h / 4)
            add(Line(a=(xx, y - h * 0.5), b=(xx - h * 0.25, y - h * 1.1), **kw))

    elif etype == "well":
        add(Polyline(points=rot([(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)]), closed=True, **kw))

    elif etype == "gpsh":
        add(Polyline(points=rot([(x - h * 1.2, y - h), (x + h * 1.2, y - h), (x + h * 1.2, y + h), (x - h * 1.2, y + h)]), closed=True, **kw))
        add(Line(a=(x - h * 1.2, y + h * 0.3), b=(x + h * 1.2, y + h * 0.3), **kw))

    elif etype == "hydrolock":
        add(
            Polyline(
                points=rot(
                    [
                        (x - h, y - h * 0.8),
                        (x - h, y + h * 0.5),
                        (x - h * 0.2, y + h * 0.5),
                        (x - h * 0.2, y - h * 0.8),
                        (x + h, y - h * 0.8),
                        (x + h, y + h * 0.5),
                    ]
                ),
                **kw,
            )
        )

    elif etype in {"tee", "cross", "riser"}:
        add(Circle(c=(x, y), r=h * 0.35, **kw))
        if etype == "cross":
            add(Line(a=(x - h * 0.6, y), b=(x + h * 0.6, y), **kw))
            add(Line(a=(x, y - h * 0.6), b=(x, y + h * 0.6), **kw))

    elif etype in {"kgz", "kem"}:
        # КЭМ — небольшой квадрат 2×2 мм на трубе;
        # КТЗ/КГЗ — такой же квадрат + треугольник-указатель слева
        add(
            Polyline(
                points=rot([(x - h * 0.45, y - h * 0.45), (x + h * 0.45, y - h * 0.45),
                            (x + h * 0.45, y + h * 0.45), (x - h * 0.45, y + h * 0.45)]),
                closed=True,
                **kw,
            )
        )
        if etype == "kgz":
            add(
                _tri(
                    *rot([(x - h * 1.36, y - h * 0.48), (x - h * 1.36, y + h * 0.48), (x - h * 0.45, y)]),
                    **kw,
                )
            )

    elif etype == "reducer":
        # переход: треугольник на трубе, сужается в сторону меньшего диаметра
        # (вершина показывает направление на меньший проход)
        add(
            Polyline(
                points=rot([(x - h, y - h * 0.85), (x + h, y), (x - h, y + h * 0.85)]),
                closed=True,
                **kw,
            )
        )

    elif etype == "sleeve":
        # проход через стену (гильза/футляр): прямоугольник вокруг трубы,
        # длинной стороной вдоль неё (8,6 мм) и толщиной 3 мм
        add(
            Polyline(
                points=rot([(x - h * 2.1, y - h * 0.75), (x + h * 2.1, y - h * 0.75),
                            (x + h * 2.1, y + h * 0.75), (x - h * 2.1, y + h * 0.75)]),
                closed=True,
                **kw,
            )
        )

    elif etype == "fork":
        # вилка: труба делится на две — полукруг над местом разделения,
        # ветки расходятся на ±size
        add(Arc(c=(x, y), r=s, a0=rotation, a1=rotation + 180.0, **kw))

    elif etype == "facade_link":
        # пунктир: фасадный газопровод показан двумя длинными штрихами
        # с разрывом — чтобы сопоставить лист фасада с этим узлом
        add(Line(a=rot([(x - s * 1.15, y)])[0], b=rot([(x - s * 0.15, y)])[0], **kw))
        add(Line(a=rot([(x + s * 0.15, y)])[0], b=rot([(x + s * 1.15, y)])[0], **kw))

    elif etype == "coupling":
        # муфта: две черты поперёк трубы
        add(Line(a=(x - h * 0.5, y - h), b=(x - h * 0.5, y + h), **kw))
        add(Line(a=(x + h * 0.5, y - h), b=(x + h * 0.5, y + h), **kw))

    elif etype == "flange":
        add(Line(a=(x - h * 0.25, y - h), b=(x - h * 0.25, y + h), **kw))
        add(Line(a=(x + h * 0.25, y - h), b=(x + h * 0.25, y + h), **kw))

    elif etype == "insulation_end":
        add(Line(a=(x - h, y - h * 0.7), b=(x + h, y + h * 0.7), **kw))
        add(Line(a=(x - h, y + h * 0.7), b=(x + h, y - h * 0.7), **kw))

    elif etype == "manometer":
        add(Circle(c=(x, y), r=h * 0.6, **kw))
        add(Line(a=(x, y - h * 0.6), b=(x - h * 0.3, y + h * 0.2), **kw))
        add(Line(a=(x, y), b=(x, y - h * 1.4), **kw))

    elif etype == "regulator":
        add(_tri((x - h, y + h * 0.7), (x - h, y - h * 0.7), (x, y), **kw))
        add(_tri((x + h, y - h * 0.7), (x + h, y + h * 0.7), (x, y), **kw))
        add(Line(a=(x, y - h * 0.7), b=(x, y - h * 1.3), **kw))

    elif etype == "meter":
        add(Polyline(points=rot([(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)]), closed=True, **kw))
        add(Text(text="УУ", at=(x, y - h * 0.55), height=h * 0.8, layer=layer, align="center", state=state))

    elif etype in {"inlet", "outlet"}:
        dx = -1 if etype == "inlet" else 1
        add(Line(a=(x - dx * h * 1.4, y), b=(x + dx * h * 0.6, y), **kw))
        add(_tri((x + dx * h * 1.4, y), (x + dx * h * 0.5, y + h * 0.55), (x + dx * h * 0.5, y - h * 0.55), **kw))

    elif etype == "pit":
        add(Polyline(points=rot([(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)]), closed=True, **kw))
        add(Line(a=(x - h, y - h), b=(x + h, y + h), **kw))

    else:  # unknown
        add(Circle(c=(x, y), r=h * 0.8, **kw))
        add(Text(text="?", at=(x, y - h * 0.5), height=h, layer=layer, align="center", state=state))

    return prims


def draw_arrow(scene: Scene, at: tuple[float, float], angle: float, size: float = 3.0, layer: str = "TEXT") -> None:
    x, y = at
    a = math.radians(angle)
    p1 = (x, y)
    p2 = (x - size * math.cos(a - 0.35), y - size * math.sin(a - 0.35))
    p3 = (x - size * math.cos(a + 0.35), y - size * math.sin(a + 0.35))
    scene.add(Solid(points=[p1, p2, p3], layer=layer))
