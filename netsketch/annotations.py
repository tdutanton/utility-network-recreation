"""Аннотации исполнительной схемы: швы, опоры, цепи, выноски, отметки, итог.

Примитивы эталонных листов (`examples/gas/1`):

* **сварной шов** — короткий наклонный штрих поперёк трубы и номер рядом
  (`30`, `2.1`, `2.17`); суффикс `.1`, `.2` — ветки того же шва;
* **опора** — крестик `×` поперёк трубы (узел крепления к стене);
* **цепь** — размерная линия с текстом над ней: `СШ 1000`, `ОП 3000`
  или свободный размер;
* **выноска** — текст на полке, от полки линия к элементу
  (`Отвод Ø25`, `Переход Ø25/20`, `Кран Ø15`, `КИП Ø25`);
* **отметка** — `Отм. -0.8` на полке;
* **помещение** — крупно, без выноски: `КВ. 5`, `1 под.`;
* **итог** — крупный курсив (Times New Roman Italic): `Итого 9,2 м`.

Все размеры — в мм листа. Координаты, приходящие из модели, должны быть уже
пересчитаны раскладкой: модуль ничего не знает про пиксели эскиза.
Текст не ставится на линию: подписи смещаются в сторону от трубы.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

from .scene import Arc, Line, MLeader, Polyline, Scene, Text, text_width

Point = tuple[float, float]

LAYER_WELD = "SN"
LAYER_TEXT = "TEXT"
LAYER_DIM = "DIM"

# Наклон штриха шва к оси трубы (45° — так рисуют в эталоне) и его длина.
WELD_TILT_DEG = 45.0
WELD_STROKE = 4.0
SUPPORT_SIZE = 2.6

PREFIXES = {"weld": "СШ", "support": "ОП", "plain": ""}


# ----------------------------------------------------------------------
def _norm_angle(angle: float) -> float:
    while angle > 90:
        angle -= 180
    while angle < -90:
        angle += 180
    return angle


def weld_mark(
    scene: Scene,
    at: Point,
    number: str,
    angle: float = 0.0,
    *,
    height: float = 2.2,
    stroke: float = WELD_STROKE,
    label_at: Point | None = None,
    rotate_text: bool = False,
) -> None:
    """Штрих шва поперёк трубы и номер рядом.

    `at` — середина штриха, `angle` — направление самого штриха (в эталоне
    он наклонён примерно на 45–50° к трубе). Если известно, где автор
    поставил номер (`label_at`), номер ставится туда; иначе — рядом
    со штрихом по нормали.
    """
    rad = math.radians(angle)
    dx, dy = math.cos(rad) * stroke / 2, math.sin(rad) * stroke / 2
    scene.add(
        Line(a=(at[0] - dx, at[1] - dy), b=(at[0] + dx, at[1] + dy), layer=LAYER_WELD, lw=0.195)
    )

    if label_at is not None:
        pos = label_at
        align = "left"
    else:
        # смещение номера по нормали к штриху, предпочтительно вверх-влево
        nx, ny = -dy / (stroke / 2), dx / (stroke / 2)
        if ny < -1e-9 or (abs(ny) < 1e-9 and nx < 0):
            nx, ny = -nx, -ny
        gap = 1.3 + height * 0.5
        pos = (at[0] + nx * gap, at[1] + ny * gap)
        align = "center"

    rot = _norm_angle(angle) if rotate_text else 0.0
    scene.add(Text(text=str(number), at=pos, height=height, rotation=rot, layer=LAYER_TEXT, align=align))


def support_mark(
    scene: Scene,
    at: Point,
    angle: float = 0.0,
    *,
    size: float = SUPPORT_SIZE,
) -> None:
    """Опора: `×` поперёк трубы (перекладина повёрнута на 45° к оси)."""
    tilt = math.radians(angle + 45.0)
    dx, dy = math.cos(tilt) * size / 2, math.sin(tilt) * size / 2
    scene.add(Line(a=(at[0] - dx, at[1] - dy), b=(at[0] + dx, at[1] + dy), layer=LAYER_WELD, lw=0.19))
    scene.add(Line(a=(at[0] - dy, at[1] + dx), b=(at[0] + dy, at[1] - dx), layer=LAYER_WELD, lw=0.19))


def callout(
    scene: Scene,
    text: str,
    target: Point | Sequence[Point],
    at: Point,
    *,
    side: str = "right",
    height: float = 2.2,
    lead: float = 1.2,
    arrow: bool = True,
) -> None:
    """Выноска — полноценный MULTILEADER: полка, текст и стрелки одним объектом.

    `target` — точка или несколько точек. Если точек несколько, ветки
    сходятся в общем узле и раздваиваются (например «Кран Ø15» на оба крана).
    `at` — точка крепления полки, `side` — куда уходит текст.
    """
    targets = [target] if isinstance(target, tuple) else [t for t in target if t is not None]
    if not targets:
        return
    width = text_width(text, height)
    shelf = max(width + 2.0, 6.0)

    if side in {"right", "left"}:
        x0 = at[0] if side == "right" else at[0] - shelf
        shelf_start = (x0, at[1])
        text_at = (x0 + 1.0, at[1] + 0.9)
    else:
        sign = 1.0 if side == "up" else -1.0
        shelf_start = (at[0], at[1] + sign * shelf)
        text_at = (at[0] - height * 0.5, min(at[1], shelf_start[1]) + 1.0)

    node = None
    if len(targets) > 1:
        node = (
            sum(t[0] for t in targets) / len(targets),
            sum(t[1] for t in targets) / len(targets),
        )

    leaders: list[list[Point]] = []
    for end in targets:
        if math.dist(at, end) <= lead:
            continue
        path = [shelf_start, at]
        if node is not None and math.dist(at, node) > lead:
            path.append(node)
        path.append(end)
        leaders.append(path)

    scene.add(
        MLeader(
            text=text,
            at=text_at,
            leaders=leaders or [[shelf_start, at]],
            height=height,
            side=side,
            layer=LAYER_TEXT,
            lw=0.18,
            arrow=arrow,
        )
    )


def level_mark(scene: Scene, text: str, target: Point, *, side: str = "left", height: float = 2.2) -> None:
    """Отметка `Отм. -0.8` на полке у ввода/выпуска."""
    callout(scene, text, target, target, side=side, height=height)


def room_label(scene: Scene, text: str, at: Point, *, height: float = 3.8) -> None:
    """Крупная подпись помещения: `КВ. 5`, `1 под.`."""
    scene.add(Text(text=text, at=at, height=height, layer=LAYER_TEXT))


def summary_block(
    scene: Scene,
    lines: Sequence[str],
    at: Point,
    *,
    height: float = 3.2,
    row: float = 5.0,
    serif: bool = True,
    italic: bool = True,
) -> float:
    """Итоговый блок крупным курсивом. Возвращает нижнюю границу."""
    y = at[1]
    for line in lines:
        if not line.strip():
            y -= row * 0.6
            continue
        scene.add(
            Text(
                text=line,
                at=(at[0], y),
                height=height,
                layer=LAYER_TEXT,
                serif=serif,
                italic=italic,
            )
        )
        y -= row
    return y


def dimension_chain(
    scene: Scene,
    points: Sequence[Point],
    values_mm: Sequence[int],
    *,
    prefix: str = "",
    offset: float = 8.0,
    height: float = 2.5,
    side: str = "auto",
    centroid: Point | None = None,
) -> None:
    """Размерная цепь с текстом над линией; `СШ`/`ОП` — префикс в тексте."""
    pts = list(points)
    if len(pts) < 2:
        return

    # сторона смещения — от центра чертежа, если не задана
    a, b = pts[0], pts[1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    if side == "auto":
        sign = 1.0
        if centroid is not None:
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if (mid[0] - centroid[0]) * nx + (mid[1] - centroid[1]) * ny > 0:
                sign = -1.0
        else:
            sign = 1.0 if ny >= 0 else -1.0
    else:
        sign = -1.0 if side in {"left", "down", "minus"} else 1.0

    shifted = [(p[0] + nx * offset * sign, p[1] + ny * offset * sign) for p in pts]
    scene.add(Polyline(points=shifted, layer=LAYER_DIM, lw=0.18))

    # выносные линии от трубы до размерной
    for p, q in zip(pts, shifted):
        scene.add(Line(a=p, b=q, layer=LAYER_DIM, lw=0.13))

    # засечки
    for p in shifted:
        scene.add(Line(a=(p[0] - 1.0, p[1] - 1.0), b=(p[0] + 1.0, p[1] + 1.0), layer=LAYER_DIM, lw=0.18))

    for i, (p0, p1) in enumerate(zip(shifted, shifted[1:])):
        value = values_mm[i] if i < len(values_mm) else None
        if not value:
            continue
        ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
        ang = _norm_angle(ang)
        label = f"{prefix} {fmt_mm(value)}".strip() if prefix else fmt_mm(value)
        cx, cy = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        # текст над линией, сдвиг по нормали в ту же сторону
        scene.add(
            Text(
                text=label,
                at=(cx + nx * sign * 1.0, cy + ny * sign * 1.0),
                height=height,
                rotation=ang,
                layer=LAYER_DIM,
                align="center",
                valign="bottom",
            )
        )


def fmt_mm(value: int | float) -> str:
    """1500 → «1 500» (как в эталонных цепях)."""
    return f"{int(round(value)):,}".replace(",", " ")


# ----------------------------------------------------------------------
def draw_model_annotations(
    scene: Scene,
    model,
    transform,
    *,
    legend_rect: tuple[float, float, float, float] | None = None,
) -> None:
    """Все аннотации модели в мм листа (вызывается раскладкой schematic).

    Кегли и размеры штрихов берутся из `model.meta`: в эталонных DWG текст
    нарисован с аннотативным масштабом, поэтому на печати он крупнее, чем
    высота TEXT в DXF (`weld_height`, `callout_height`).
    """
    pt = transform.pt
    meta = getattr(model, "meta", {}) or {}
    height_weld = float(meta.get("weld_height") or 2.2)
    height_callout = float(meta.get("callout_height") or 2.2)
    stroke = float(meta.get("weld_stroke") or WELD_STROKE)
    support = float(meta.get("support_size") or SUPPORT_SIZE)

    placed: list[tuple[float, float, float, float]] = []

    def _text_rect(at: Point, text: str, height: float, align: str = "left") -> tuple[float, float, float, float]:
        width = text_width(text, height)
        x0 = at[0] if align == "left" else at[0] - width
        return (x0, at[1] - height * 0.25, x0 + width, at[1] + height * 1.25)

    def _rect(at: Point, side: str, text: str, height: float) -> tuple[float, float, float, float]:
        width = text_width(text, height) + 2.0
        if side in {"left", "right"}:
            x0 = at[0] if side == "right" else at[0] - width
            return (x0, at[1] - height * 0.25, x0 + width, at[1] + height * 1.25)
        depth = max(width, 6.0)
        y0 = at[1] if side == "up" else at[1] - depth
        return (at[0] - height * 0.25, y0, at[0] + height * 1.25, y0 + depth)

    def _overlaps(a, b) -> bool:
        return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])

    def _line_rect(a: Point, b: Point, pad: float) -> tuple[float, float, float, float]:
        return (
            min(a[0], b[0]) - pad,
            min(a[1], b[1]) - pad,
            max(a[0], b[0]) + pad,
            max(a[1], b[1]) + pad,
        )

    # трубы: подписи не должны ложиться на них
    pipes: list[tuple[float, float, float, float]] = []
    for seg in getattr(model, "segments", []):
        pts = [pt(p) for p in seg.points]
        for a, b in zip(pts, pts[1:]):
            pipes.append(_line_rect(a, b, 1.4))

    for weld in getattr(model, "welds", []):
        label_at = None
        if getattr(weld, "label_x", None) is not None and getattr(weld, "label_y", None) is not None:
            label_at = pt((weld.label_x, weld.label_y))
        weld_mark(
            scene,
            pt((weld.x, weld.y)),
            weld.id,
            weld.angle,
            label_at=label_at,
            height=height_weld,
            stroke=stroke,
        )
        if label_at is not None:
            placed.append(_text_rect(label_at, str(weld.id), height_weld, align="left"))

    for support_item in getattr(model, "supports", []):
        support_mark(scene, pt((support_item.x, support_item.y)), support_item.angle, size=support)

    for room in getattr(model, "rooms", []):
        at = pt((room.x, room.y))
        room_label(scene, room.text, at, height=room.height)
        placed.append(_text_rect(at, room.text, room.height))

    placed_callouts: list[tuple[float, float, float, float]] = []

    for callout_item in getattr(model, "callouts", []):
        targets = [pt(t) for t in (getattr(callout_item, "targets", None) or [])]
        if not targets and callout_item.tx is not None:
            targets = [pt((callout_item.tx, callout_item.ty))]
        at = pt((callout_item.x, callout_item.y)) if callout_item.x is not None else None
        if not targets or at is None:
            continue
        side = callout_item.side
        step = height_callout * 1.6
        # кандидаты сдвига: сначала по вертикали, потом в сторону от трубы
        offsets = []
        for k in range(1, 5):
            offsets += [(0.0, step * k), (0.0, -step * k)]
        for k in range(1, 4):
            offsets += [(-step * 1.6 * k, 0.0), (step * 1.6 * k, 0.0)]

        rect = _rect(at, side, callout_item.text, height_callout)
        if getattr(callout_item, "fixed", False):
            # место задал автор модели — авто-разводка не двигает
            placed_callouts.append(rect)
            callout(scene, callout_item.text, targets, at, side=side, height=height_callout)
            continue
        for dx, dy in offsets:
            if not any(_overlaps(rect, r) for r in placed + placed_callouts + pipes):
                break
            candidate = (at[0] + dx, at[1] + dy)
            rect = _rect(candidate, side, callout_item.text, height_callout)
            if not any(_overlaps(rect, r) for r in placed + placed_callouts + pipes):
                at = candidate
                break
        placed_callouts.append(rect)
        callout(scene, callout_item.text, targets, at, side=side, height=height_callout)

    for chain in getattr(model, "chains", []):
        points = [pt(p) for p in chain.points]
        values = chain.values_mm or [
            int(round(math.dist(points[i], points[i + 1]) * getattr(transform, "scale", 1.0)))
            for i in range(len(points) - 1)
        ]
        dimension_chain(
            scene,
            points,
            values,
            prefix=PREFIXES.get(chain.kind, ""),
            offset=chain.offset_mm or 8.0,
            side=chain.side,
        )
