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


def _label_box(label_at: Point, width: float, height: float, align: str) -> tuple[float, float, float, float]:
    """Габарит подписи: (x, y) — верхний угол, текст растёт вниз."""
    x0 = label_at[0] if align == "left" else label_at[0] - width
    return (x0, label_at[1] - height, x0 + width, label_at[1])


def _leader_start(
    label_at: Point, text: str, height: float, align: str, target: Point
) -> tuple[Point, str]:
    """Точка отрыва выноски — ближний к цели угол подписи и сторона полки."""
    width = text_width(text, height)
    box = _label_box(label_at, width, height, align)
    right = target[0] >= (box[0] + box[2]) / 2
    top = target[1] >= (box[1] + box[3]) / 2
    x = box[2] if right else box[0]
    y = box[3] if top else box[1]
    return (x, y), ("right" if right else "left")


def _callout_box(
    label_at: Point, text: str, height: float, align: str
) -> tuple[float, float, float, float]:
    """Габарит подписи выноски: (x0, y0, x1, y1), текст растёт вниз от `label_at`.

    `label_at` — верхний угол текста (insert MULTILEADER): левый при
    `align="left"`, правый при `align="right"`.
    """
    width = text_width(text, height)
    lines = max(1, str(text).count("\n") + 1)
    x0 = label_at[0] if align != "right" else label_at[0] - width
    return (x0, label_at[1] - height * lines, x0 + width, label_at[1])


def weld_mark(
    scene: Scene,
    at: Point,
    number: str,
    angle: float = 0.0,
    *,
    height: float = 2.2,
    stroke: float = WELD_STROKE,
    label_at: Point | None = None,
    label_align: str = "left",
    top_anchor: bool = False,
    rotate_text: bool = False,
    leader: bool = True,
) -> None:
    """Штрих шва поперёк трубы и номер рядом.

    `at` — середина штриха, `angle` — направление самого штриха (в эталоне
    он наклонён примерно на 45–50° к трубе). Если известно, где автор
    поставил номер (`label_at`), номер ставится туда; иначе — рядом
    со штрихом по нормали.

    В эталонных DWG номер — это MULTILEADER: стрелка у засечки и поводок
    к верхнему углу текста (`label_align` = left|right). Поэтому `label_at`
    трактуется как ВЕРХНИЙ угол подписи, а не как её левый низ.
    """
    rad = math.radians(angle)
    dx, dy = math.cos(rad) * stroke / 2, math.sin(rad) * stroke / 2
    scene.add(
        Line(a=(at[0] - dx, at[1] - dy), b=(at[0] + dx, at[1] + dy), layer=LAYER_WELD, lw=0.195)
    )

    align = "right" if str(label_align).lower() == "right" else "left"
    if label_at is not None:
        pos = label_at
    else:
        # смещение номера по нормали к штриху, предпочтительно вверх-влево
        nx, ny = -dy / (stroke / 2), dx / (stroke / 2)
        if ny < -1e-9 or (abs(ny) < 1e-9 and nx < 0):
            nx, ny = -nx, -ny
        gap = 1.3 + height * 0.5
        pos = (at[0] + nx * gap, at[1] + ny * gap)
        align = "center"

    if top_anchor and label_at is not None and leader and math.dist(pos, at) > max(1.5, height * 0.7):
        start, side = _leader_start(pos, str(number), height, align, at)
        # MLeader рисует текст от левого края: при выключке вправо сдвигаем
        text_at = pos if align != "right" else (pos[0] - text_width(str(number), height), pos[1])
        scene.add(
            MLeader(
                text=str(number),
                at=text_at,
                leaders=[[start, at]],
                height=height,
                side=side,
                arrow=True,
                valign="top" if top_anchor else "bottom",
                layer=LAYER_TEXT,
                lw=0.18,
            )
        )
        return

    rot = _norm_angle(angle) if rotate_text else 0.0
    scene.add(
        Text(
            text=str(number),
            at=pos,
            height=height,
            rotation=rot,
            layer=LAYER_TEXT,
            align=align,
            # номер из модели привязан к верхнему углу (insert MULTILEADER),
            # номер «по нормали» — по-старому от левого низа
            valign="top" if (label_at is not None and top_anchor) else "bottom",
        )
    )


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


def _callout_shelf_start(
    box: tuple[float, float, float, float], elbow: Point, at: Point, height: float
) -> Point:
    """Начало ветки у текста: дальний край полки или ближний край при поводке.

    Полка (длинная линия под текстом) есть только там, где излом лёг на
    нижнюю часть строки (`elbow.y` ниже середины). Если автор прицепил
    поводок сбоку текста (изо-схемы Валдая), полки нет: ветка начинается
    у ближнего края текста на высоте излома. Иначе линия прошла бы сквозь
    подпись — именно так «перечёркивались» выноски изометрии.
    """
    near_x = box[0] if abs(elbow[0] - box[0]) <= abs(elbow[0] - box[2]) else box[2]
    if elbow[1] <= at[1] - 0.55 * height:
        far_x = box[2] if near_x == box[0] else box[0]
        return (far_x, elbow[1])
    return (near_x, elbow[1])


def fixed_callout(
    scene: Scene,
    text: str,
    target: Point | Sequence[Point],
    at: Point,
    *,
    align: str = "left",
    height: float = 2.2,
    elbow: Point | None = None,
) -> None:
    """Выноска на месте автора: `at` — ВЕРХНИЙ угол текста (insert MULTILEADER).

    Если задан `elbow` (излом поводка из `last_leader_point` эталонного DWG),
    ветка строится как в авторском листе: острие → излом → полка/поводок.
    Когда излом лежит у нижней части строки, полка идёт до дальнего края
    текста (её длина равна ширине подписи) — как на печатном эталоне
    квартирных схем. Когда автор прицепил поводок к боку текста (изометрия
    Валдая), рисуется короткий поводок у края, без линии сквозь подпись.
    Без `elbow` — прежняя короткая выноска от ближнего угла текста.
    """
    targets = [target] if isinstance(target, tuple) else [t for t in target if t is not None]
    if not targets:
        return
    side_align = "right" if str(align).lower() == "right" else "left"
    text_at = at
    if side_align == "right":
        # MLeader рисует текст от левого края: сдвигаем на ширину строки
        text_at = (at[0] - text_width(text, height), at[1])

    if elbow is not None:
        box = _callout_box(at, text, height, side_align)
        start = _callout_shelf_start(box, elbow, at, height)
        leaders = [[start, elbow, end] for end in targets]
        scene.add(
            MLeader(
                text=text,
                at=text_at,
                leaders=leaders,
                height=height,
                side="right" if start[0] >= elbow[0] else "left",
                layer=LAYER_TEXT,
                lw=0.18,
                arrow=True,
                valign="top",
            )
        )
        return

    start, side = _leader_start(at, text, height, side_align, targets[0])
    leaders = [[start, end] for end in targets]
    scene.add(
        MLeader(
            text=text,
            at=text_at,
            leaders=leaders,
            height=height,
            side=side,
            layer=LAYER_TEXT,
            lw=0.18,
            arrow=True,
            valign="top",
        )
    )


def level_mark(scene: Scene, text: str, target: Point, *, side: str = "left", height: float = 2.2) -> None:
    """Отметка `Отм. -0.8` на полке у ввода/выпуска."""
    callout(scene, text, target, target, side=side, height=height)


def room_label(
    scene: Scene,
    text: str,
    at: Point,
    *,
    height: float = 3.8,
    align: str = "left",
    valign: str = "bottom",
    leader: Sequence[Point] | None = None,
    frame: bool = False,
) -> None:
    """Крупная подпись помещения: `КВ. 5`, `1 под.`.

    В изометрии эталона подпись соединена с опуском тонким поводком —
    он приходит из модели (`Room.leader`) в мм листа. `frame` обводит
    подпись рамкой (в части эталонов квартиры обведены).
    """
    points = list(leader or [])
    for a, b in zip(points, points[1:]):
        scene.add(Line(a=a, b=b, layer=LAYER_TEXT, lw=0.13))
    scene.add(
        Text(text=text, at=at, height=height, align=align, valign=valign, layer=LAYER_TEXT)
    )
    if frame:
        w = text_width(text, height) + 2.4
        hh = height * 1.5
        x0 = at[0] if align == "left" else at[0] - w
        y1 = at[1] if valign == "top" else at[1] + height * 1.25
        scene.add(
            Polyline(
                points=[(x0, y1 - hh), (x0 + w, y1 - hh), (x0 + w, y1), (x0, y1)],
                closed=True,
                layer=LAYER_TEXT,
                lw=0.13,
            )
        )


def defect_table(
    scene: Scene,
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    at: Point,
    *,
    col_widths: Sequence[float] = (9.0, 60.0, 10.0, 10.0, 10.0, 10.0, 12.0),
    title: str = "Ведомость дефектов",
    height: float = 2.3,
) -> float:
    """Таблица дефектов справа: строки — коды, столбцы — подъезды.

    `at` — правый верхний угол таблицы (мм листа). Последняя строка `rows`
    считается итоговой и рисуется полужирным. Возвращает нижнюю границу,
    чтобы компоновка знала, сколько места занято.
    """
    if len(header) != len(col_widths) or any(len(r) != len(col_widths) for r in rows):
        raise ValueError("defect_table: число столбцов не совпадает с col_widths")
    width_total = sum(col_widths)
    x_right, y_top = at
    x0 = x_right - width_total
    title_h = 4.6
    head_h = 4.6
    row_h = 4.4
    y_positions = [y_top, y_top - title_h, y_top - title_h - head_h]
    for _ in rows:
        y_positions.append(y_positions[-1] - row_h)
    y_bottom = y_positions[-1]

    xs = [x0]
    for w in col_widths:
        xs.append(xs[-1] + w)

    scene.add(
        Polyline(
            points=[(x0, y_bottom), (x0, y_top), (x_right, y_top), (x_right, y_bottom), (x0, y_bottom)],
            layer="TEXT",
            lw=0.3,
        )
    )
    for y in y_positions[1:-1]:
        scene.add(Line(a=(x0, y), b=(x_right, y), layer="TEXT", lw=0.18))
    for x in xs[1:-1]:
        # вертикали начинаются под строкой заголовка: она во всю ширину
        scene.add(Line(a=(x, y_bottom), b=(x, y_positions[1]), layer="TEXT", lw=0.18))

    # заголовок во всю ширину
    scene.add(
        Text(
            text=title,
            at=((x0 + x_right) / 2, y_top - title_h / 2),
            height=3.0,
            layer="TEXT",
            align="center",
            valign="middle",
            bold=True,
        )
    )

    def cell(row: int, col: int, text: str, *, bold: bool = False, left: bool = False) -> None:
        y = (y_positions[row] + y_positions[row + 1]) / 2
        if left:
            scene.add(
                Text(
                    text=text,
                    at=(xs[col] + 1.0, y),
                    height=height,
                    layer="TEXT",
                    align="left",
                    valign="middle",
                    bold=bold,
                )
            )
        else:
            scene.add(
                Text(
                    text=text,
                    at=((xs[col] + xs[col + 1]) / 2, y),
                    height=height,
                    layer="TEXT",
                    align="center",
                    valign="middle",
                    bold=bold,
                )
            )

    # после заголовка идёт строка header, затем данные
    head_index = 1
    for col, value in enumerate(header):
        cell(head_index, col, value, bold=True, left=col == 1)
    for r, row_values in enumerate(rows):
        is_total = r == len(rows) - 1
        for col, value in enumerate(row_values):
            cell(head_index + 1 + r, col, value, bold=is_total, left=col == 1)
    return y_bottom


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
    group_digits: bool = True,
    avoid: Sequence[tuple[float, float, float, float]] = (),
    text_at: Point | None = None,
) -> None:
    """Размерная цепь с текстом над линией; `СШ`/`ОП` — префикс в тексте.

    `group_digits` — разбивать тысячи пробелом (`3 370`); в части эталонов
    размеры пишут без разбивки (`3370`).
    `avoid` — прямоугольники подписей, которые текст не должен накрывать:
    если середина отрезка занята, текст сдвигается вдоль размерной линии.
    `text_at` — место подписи, заданное автором (DIMENSION text_midpoint):
    тогда текст ставится точно туда и `avoid` не применяется.
    """
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
        label = f"{prefix} {fmt_mm(value, group=group_digits)}".strip() if prefix else fmt_mm(value, group=group_digits)
        width = text_width(label, height)
        cos_a, sin_a = abs(math.cos(math.radians(ang))), abs(math.sin(math.radians(ang)))
        bw, bh = width * cos_a + height * sin_a, width * sin_a + height * cos_a
        # «вверх» в системе САМОГО текста: при rotation=ang это (-sin, cos).
        # Для участков, идущих справа налево, это направление противоположно
        # нормали линии (u = -n) — если брать n, текст ложится НА линию.
        rad = math.radians(ang)
        ux, uy = -math.sin(rad), math.cos(rad)

        def _taken(at_point: Point) -> bool:
            # подпись растёт вверх в своей системе: центр на height/2 выше базы
            cx0, cy0 = at_point[0] + ux * height * 0.5, at_point[1] + uy * height * 0.5
            x0, y0 = cx0 - bw / 2, cy0 - bh / 2
            pad = 0.6  # просвет до соседней подписи
            box = (x0 - pad, y0 - pad, x0 + bw + pad, y0 + bh + pad)
            for r in avoid:
                if not (box[2] <= r[0] or r[2] <= box[0] or box[3] <= r[1] or r[3] <= box[1]):
                    return True
            return False

        # место автора (text_midpoint) — приоритет, если оно свободно
        at = None
        if text_at is not None and not _taken(tuple(text_at)):
            at = (text_at[0], text_at[1])
        if at is None:
            # иначе середина отрезка; если и там чужая подпись — сдвиг по линии
            for t in (0.5, 0.68, 0.32, 0.84, 0.16, 0.95, 0.05):
                cx = p0[0] + (p1[0] - p0[0]) * t
                cy = p0[1] + (p1[1] - p0[1]) * t
                candidate = (cx + ux * 1.5, cy + uy * 1.5)
                if not _taken(candidate):
                    at = candidate
                    break
        if at is None:
            if text_at is not None:
                at = (text_at[0], text_at[1])
            else:
                cx, cy = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
                at = (cx + ux * 1.5, cy + uy * 1.5)

        # если подпись оказалась почти на самой линии (в эталонах так бывает —
        # автор поставил текст «в линию»), поднимаем её на стандартные 1,5 мм:
        # линия не должна резать цифры
        dxl, dyl = p1[0] - p0[0], p1[1] - p0[1]
        ll = dxl * dxl + dyl * dyl or 1.0
        t_proj = ((at[0] - p0[0]) * dxl + (at[1] - p0[1]) * dyl) / ll
        near = (p0[0] + dxl * t_proj, p0[1] + dyl * t_proj)
        across = (at[0] - near[0]) * ux + (at[1] - near[1]) * uy
        if across < 1.0:
            at = (near[0] + ux * 1.5, near[1] + uy * 1.5)

        # текст ставится над линией в её собственной системе: вдоль +n на 1,5 мм
        # (как DIMENSION эталона), поэтому линия никогда не режет цифры
        scene.add(
            Text(
                text=label,
                at=at,
                height=height,
                rotation=ang,
                layer=LAYER_DIM,
                align="center",
                valign="bottom",
            )
        )

        # подпись не влезла между выносными линиями — продлеваем размерную
        # линию под ней, иначе текст «висит» без полки (как в эталонных DWG)
        seg_len = math.hypot(dxl, dyl) or 1.0
        ux, uy = dxl / seg_len, dyl / seg_len
        t_center = (at[0] - p0[0]) * ux + (at[1] - p0[1]) * uy
        t_lo, t_hi = t_center - width / 2, t_center + width / 2
        overrun = 1.5
        if t_lo < -0.3:
            tail = (p0[0] + ux * (t_lo - overrun), p0[1] + uy * (t_lo - overrun))
            scene.add(Line(a=tuple(p0), b=tail, layer=LAYER_DIM, lw=0.18))
        if t_hi > seg_len + 0.3:
            tail = (p1[0] + ux * (t_hi - seg_len + overrun), p1[1] + uy * (t_hi - seg_len + overrun))
            scene.add(Line(a=tuple(p1), b=tail, layer=LAYER_DIM, lw=0.18))


def fmt_mm(value: int | float, group: bool = True) -> str:
    """1500 → «1 500» (как в эталонных цепях); `group=False` → «1500»."""
    if not group:
        return f"{int(round(value))}"
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

    def _text_rect(
        at: Point, text: str, height: float, align: str = "left", top: bool = False
    ) -> tuple[float, float, float, float]:
        width = text_width(text, height)
        x0 = at[0] if align == "left" else at[0] - width
        if top:
            return (x0, at[1] - height, x0 + width, at[1] + height * 0.25)
        return (x0, at[1] - height * 0.25, x0 + width, at[1] + height * 1.25)

    def _rect(at: Point, side: str, text: str, height: float) -> tuple[float, float, float, float]:
        width = text_width(text, height) + 2.0
        depth = height * max(1, text.count("\n") + 1)  # многострочная выноска выше
        if side in {"left", "right"}:
            x0 = at[0] if side == "right" else at[0] - width
            return (x0, at[1] - height * 0.25, x0 + width, at[1] + depth + height * 0.25)
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
        label_align = str(getattr(weld, "label_align", "") or "")
        weld_mark(
            scene,
            pt((weld.x, weld.y)),
            weld.id,
            weld.angle,
            label_at=label_at,
            label_align=label_align or "left",
            top_anchor=bool(label_align),
            height=height_weld,
            stroke=stroke,
        )
        if label_at is not None:
            placed.append(
                _text_rect(label_at, str(weld.id), height_weld, align=label_align or "left", top=bool(label_align))
            )

    for support_item in getattr(model, "supports", []):
        support_mark(scene, pt((support_item.x, support_item.y)), support_item.angle, size=support)

    for room in getattr(model, "rooms", []):
        at = pt((room.x, room.y))
        align = str(getattr(room, "label_align", "") or "")
        room_label(
            scene,
            room.text,
            at,
            height=room.height,
            align=align or "left",
            valign="top" if align else "bottom",
            leader=[pt(p) for p in (getattr(room, "leader", None) or [])],
            frame=bool(getattr(room, "frame", False)),
        )
        placed.append(_text_rect(at, room.text, room.height, align=align or "left", top=bool(align)))

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

        elbow_raw = getattr(callout_item, "elbow", None)
        if elbow_raw is not None:
            # авторская геометрия поводка: острие -> излом -> полка -> текст
            elbow = pt((elbow_raw[0], elbow_raw[1]))
            align = str(getattr(callout_item, "align", "") or "")
            if not align:
                if abs(elbow[0] - at[0]) < 0.2:
                    align = "left" if side != "left" else "right"
                else:
                    align = "left" if elbow[0] < at[0] else "right"
            placed_callouts.append(_callout_box(at, callout_item.text, height_callout, align))
            fixed_callout(
                scene,
                callout_item.text,
                targets,
                at,
                align=align,
                height=height_callout,
                elbow=elbow,
            )
            continue

        rect = _rect(at, side, callout_item.text, height_callout)
        if getattr(callout_item, "fixed", False):
            # место задал автор модели — авто-разводка не двигает
            align = str(getattr(callout_item, "align", "") or "")
            if align:
                # подпись привязана верхним углом (insert MULTILEADER эталона)
                width = text_width(callout_item.text, height_callout)
                x0 = at[0] if align == "left" else at[0] - width
                rect = (x0, at[1] - height_callout, x0 + width, at[1])
                placed_callouts.append(rect)
                fixed_callout(
                    scene,
                    callout_item.text,
                    targets,
                    at,
                    align=align,
                    height=height_callout,
                )
                continue
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

    group_digits = bool(meta.get("dim_group", True))
    # text_width для кириллицы завышен (~0,62·h на знак против ~0,5 у Arial),
    # поэтому для проверки пересечений берём габарит уже: иначе текст размера
    # «упирается» в соседнюю подпись, которой на листе фактически не касается
    avoid_rects = [
        (r[0], r[1], r[0] + (r[2] - r[0]) * 0.8, r[3]) for r in placed + placed_callouts
    ]
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
            group_digits=group_digits,
            avoid=avoid_rects,
            text_at=getattr(chain, "text_at", None),
        )
