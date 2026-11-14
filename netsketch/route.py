"""Приведение трассы к «монтажному» виду: прямые участки и повороты 90°.

Рукописный эскиз всегда дрожит: линия чуть под наклоном, поворот сглажен.
Металлическая труба так не гнётся, поэтому перед черчением модель
нормализуется:

1. **Выравнивание листа** — если вся трасса повёрнута на пару градусов,
   модель поворачивается так, чтобы магистраль стала строго горизонтальной
   или вертикальной.
2. **Упрощение** — из ломаной убираются точки, не образующие угол
   (алгоритм Дугласа–Пекера).
3. **Привязка к осям** — почти горизонтальный участок становится строго
   горизонтальным, почти вертикальный — строго вертикальным.
4. **Слияние** — одинаково направленные соседние участки объединяются.
5. **Посадка арматуры** — символы проецируются на ось трубы, чтобы не
   висели рядом.

Диагональные участки сохраняются: прямая под 45° — это всё ещё прямая.
"""

from __future__ import annotations

import math
from dataclasses import replace

from .model import Model, Segment

Point = tuple[float, float]


# ----------------------------------------------------------------------
def _rdp(points: list[Point], eps: float) -> list[Point]:
    """Douglas–Peucker: оставляет только вершины углов."""
    if len(points) < 3:
        return list(points)
    a, b = points[0], points[-1]
    dmax, index = 0.0, 0
    for i in range(1, len(points) - 1):
        d = _point_line_distance(points[i], a, b)
        if d > dmax:
            dmax, index = d, i
    if dmax > eps:
        left = _rdp(points[: index + 1], eps)
        right = _rdp(points[index:], eps)
        return left[:-1] + right
    return [a, b]


def _point_line_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return math.dist(p, a)
    return abs(dy * (p[0] - a[0]) - dx * (p[1] - a[1])) / length


def _bbox(points: list[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


# ----------------------------------------------------------------------
def dominant_angle(model: Model) -> float:
    """Угол поворота листа (рад), сведённый к диапазону ±45°."""
    pts = [p for s in model.segments for p in s.points]
    if len(pts) < 2:
        return 0.0
    x0, y0, x1, y1 = _bbox(pts)
    diag = math.hypot(x1 - x0, y1 - y0)
    if diag < 1e-6:
        return 0.0

    sx = sy = 0.0
    for seg in model.segments:
        for a, b in zip(seg.points, seg.points[1:]):
            length = math.dist(a, b)
            if length < 0.08 * diag:
                continue
            angle = math.atan2(b[1] - a[1], b[0] - a[0])
            # период 90°: переводим в 4θ и усредняем векторно
            sx += length * math.cos(4 * angle)
            sy += length * math.sin(4 * angle)
    if abs(sx) < 1e-9 and abs(sy) < 1e-9:
        return 0.0
    angle = math.atan2(sy, sx) / 4.0
    # приводим к [-45°, 45°]
    while angle > math.pi / 4:
        angle -= math.pi / 2
    while angle < -math.pi / 4:
        angle += math.pi / 2
    return angle


def _rotate(p: Point, origin: Point, angle: float) -> Point:
    if not angle:
        return p
    ca, sa = math.cos(angle), math.sin(angle)
    dx, dy = p[0] - origin[0], p[1] - origin[1]
    return (origin[0] + dx * ca - dy * sa, origin[1] + dx * sa + dy * ca)


# ----------------------------------------------------------------------
def _snap_axis(points: list[Point], ratio: float = 0.10) -> list[Point]:
    """Почти горизонтальные/вертикальные участки делает строгими."""
    out = [points[0]]
    for a, b in zip(points, points[1:]):
        a = out[-1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 1e-9:
            continue
        if abs(dy) <= abs(dx) * ratio:
            b = (b[0], a[1])
        elif abs(dx) <= abs(dy) * ratio:
            b = (a[0], b[1])
        out.append(b)
    return out


def _merge_collinear(points: list[Point], tol: float = 1e-6) -> list[Point]:
    if len(points) < 3:
        return points
    out = [points[0]]
    for i in range(1, len(points) - 1):
        a, b, c = out[-1], points[i], points[i + 1]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        if abs(cross) > tol:
            out.append(b)
    out.append(points[-1])
    return out


def _manhattanize(points: list[Point]) -> list[Point]:
    """Ломаная → путь только из горизонталей и вертикалей (повороты 90°)."""
    if len(points) < 2:
        return list(points)
    out = [points[0]]
    for q in points[1:]:
        c = out[-1]
        dx, dy = q[0] - c[0], q[1] - c[1]
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            continue
        if abs(dx) >= abs(dy):
            mid = (q[0], c[1])
        else:
            mid = (c[0], q[1])
        if abs(mid[0] - c[0]) > 1e-6 or abs(mid[1] - c[1]) > 1e-6:
            out.append(mid)
        out.append(q)
    return out


def orthogonal_path(points: list[Point], eps: float, ratio: float = 0.10) -> list[Point]:
    if len(points) < 2:
        return list(points)
    simplified = _rdp(points, eps)
    path = _manhattanize(simplified)
    return _merge_collinear(path)


def _project_to_segment(p: Point, a: Point, b: Point) -> tuple[Point, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    if length2 < 1e-9:
        return a, math.dist(p, a)
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2
    t = max(0.0, min(1.0, t))
    q = (a[0] + dx * t, a[1] + dy * t)
    return q, math.dist(p, q)


# ----------------------------------------------------------------------
def _cluster(values: list[float], tol: float) -> dict[float, float]:
    """Сближает почти совпадающие координаты в общую ось трубы."""
    if not values:
        return {}
    uniq = sorted(set(values))
    groups: list[list[float]] = [[uniq[0]]]
    for v in uniq[1:]:
        if v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    mapping: dict[float, float] = {}
    for group in groups:
        center = sum(group) / len(group)
        for v in group:
            mapping[v] = center
    return mapping


def _snap_to_axes(paths: list[list[Point]], tol: float) -> list[list[Point]]:
    """Все вертикали/горизонтали ставит на общие оси, убирает мелкие ступеньки."""
    xs: list[float] = [p[0] for path in paths for p in path]
    ys: list[float] = [p[1] for path in paths for p in path]
    mx = _cluster(xs, tol)
    my = _cluster(ys, tol)

    snapped: list[list[Point]] = []
    for path in paths:
        out: list[Point] = []
        for x, y in path:
            nx = mx.get(x, x)
            ny = my.get(y, y)
            if out and abs(out[-1][0] - nx) < 1e-6 and abs(out[-1][1] - ny) < 1e-6:
                continue
            out.append((nx, ny))
        snapped.append(_merge_collinear(_drop_short(out, tol)))
    return snapped


def _drop_short(points: list[Point], min_len: float) -> list[Point]:
    """Убирает ступеньки короче min_len, сохраняя концы."""
    if len(points) < 3:
        return points
    out = [points[0]]
    for p in points[1:-1]:
        if math.dist(out[-1], p) >= min_len:
            out.append(p)
    last = points[-1]
    if math.dist(out[-1], last) < 1e-6 and len(out) > 1:
        out.pop()
    out.append(last)
    return out


def _axis_share(model: Model) -> float:
    """Доля длины трассы, идущей почти вдоль осей (±10°)."""
    total = near = 0.0
    for seg in model.segments:
        for a, b in zip(seg.points, seg.points[1:]):
            length = math.dist(a, b)
            if length < 1e-9:
                continue
            total += length
            ang = abs(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))) % 90
            if ang > 45:
                ang = 90 - ang
            if ang <= 10:
                near += length
    return near / total if total else 0.0


def _straighten_path(points: list[Point], eps: float, angle_tol: float = 15.0) -> list[Point]:
    """Упрощает ломаную, сохраняя прямые (диагонали не ломаем)."""
    simplified = _rdp(points, eps)
    return _merge_collinear(simplified)


ISO_AXES = [0.0, 30.0, -30.0, 90.0, 180.0, 150.0, -150.0, -90.0]


def _angle_diff(a: float, b: float) -> float:
    d = abs((a - b + 180.0) % 360.0 - 180.0)
    return d


def _iso_walk(points: list[Point], eps: float) -> list[Point]:
    """Аксонометрия: участки вдоль осей 0°, ±30°, 90°, длина сохраняется.

    Рукописная аксонометрия всегда «плывёт» на пару градусов; здесь каждый
    участок доворачивается до ближайшей изометрической оси, а вершины
    пересчитываются последовательно, чтобы линия оставалась непрерывной.
    """
    simplified = _rdp(points, eps)
    if len(simplified) < 2:
        return list(points)
    out = [simplified[0]]
    cur = simplified[0]
    for a, b in zip(simplified, simplified[1:]):
        length = math.dist(a, b)
        if length < 1e-9:
            continue
        angle = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        snapped = min(ISO_AXES, key=lambda t: _angle_diff(angle, t))
        rad = math.radians(snapped)
        cur = (cur[0] + length * math.cos(rad), cur[1] + length * math.sin(rad))
        out.append(cur)
    return _merge_collinear(out)


def fillet_path(
    points: list[Point], radius: float, *, min_angle_deg: float = 20.0
) -> list[tuple]:
    """Скруглить повороты ломаной радиусом `radius` (мм листа).

    Возвращает примитивы пути:
      ("line", a, b)            — прямой участок;
      ("arc", center, r, a0, a1) — скругление поворота.

    Для газовых схем поворот — это отвод/гнутая труба на 90°; радиус
    маленький (несколько мм на листе) и задаётся в мм листа, а не в
    координатах эскиза. Если участок короче радиуса, скругление
    ужимается, чтобы труба не «съела» сама себя.
    """
    pts = [p for p in points]
    if radius <= 0 or len(pts) < 3:
        return [("line", a, b) for a, b in zip(pts, pts[1:])]

    # точки, где начинается и заканчивается скругление на каждом угле
    trim_before: dict[int, Point] = {}
    trim_after: dict[int, Point] = {}
    arcs: dict[int, tuple] = {}

    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        l1, l2 = math.dist(a, b), math.dist(b, c)
        if l1 < 1e-9 or l2 < 1e-9:
            continue
        u1 = ((a[0] - b[0]) / l1, (a[1] - b[1]) / l1)
        u2 = ((c[0] - b[0]) / l2, (c[1] - b[1]) / l2)
        cosang = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
        angle = math.acos(cosang)
        # почти разворот (угол ~0) или «шип» (угол ~180) не скругляем:
        # труба так не гнётся, а дуга вышла бы почти полным кругом
        if math.degrees(angle) < min_angle_deg or math.degrees(angle) > 160.0:
            continue
        d = radius / math.tan(angle / 2.0) if math.tan(angle / 2.0) > 1e-9 else radius
        d = min(d, l1 * 0.49, l2 * 0.49)
        r_eff = d * math.tan(angle / 2.0)
        t1 = (b[0] + u1[0] * d, b[1] + u1[1] * d)
        t2 = (b[0] + u2[0] * d, b[1] + u2[1] * d)
        bx, by = u1[0] + u2[0], u1[1] + u2[1]
        blen = math.hypot(bx, by)
        if blen < 1e-9:
            continue
        dist_center = r_eff / math.sin(angle / 2.0) if math.sin(angle / 2.0) > 1e-9 else r_eff
        center = (b[0] + bx / blen * dist_center, b[1] + by / blen * dist_center)
        a0 = math.degrees(math.atan2(t1[1] - center[1], t1[0] - center[0]))
        a1 = math.degrees(math.atan2(t2[1] - center[1], t2[0] - center[0]))
        # DXF и matplotlib рисуют дугу против часовой от a0 к a1; если так
        # получается «длинный путь» (>180°), меняем концы местами
        if (a1 - a0) % 360 > 180:
            a0, a1 = a1, a0
        trim_before[i] = t1
        trim_after[i] = t2
        arcs[i] = (center, r_eff, a0, a1)

    out: list[tuple] = []
    cur = pts[0]
    for i in range(1, len(pts)):
        end = trim_before[i] if i in trim_before else pts[i]
        if math.dist(cur, end) > 1e-9:
            out.append(("line", cur, end))
        if i in arcs:
            center, r_eff, a0, a1 = arcs[i]
            out.append(("arc", center, r_eff, a0, a1))
            cur = trim_after[i]
        else:
            cur = pts[i]
    return out


def orthogonalize(model: Model, *, eps_ratio: float = 0.06, ratio: float = 0.10, deskew: bool = True) -> Model:
    """Возвращает копию модели с прямыми участками и углами 90°."""
    pts = [p for s in model.segments for p in s.points]
    if len(pts) < 2:
        return model

    x0, y0, x1, y1 = _bbox(pts)
    diag = math.hypot(x1 - x0, y1 - y0) or 1.0
    eps = max(diag * eps_ratio, 0.5)

    angle = dominant_angle(model) if deskew else 0.0
    # поворачиваем всё вокруг центра габарита
    center = ((x0 + x1) / 2, (y0 + y1) / 2)

    def rot(p: Point) -> Point:
        return _rotate(p, center, -angle)

    new = replace(model)
    new.nodes = [replace(n, x=rot(n.xy)[0], y=rot(n.xy)[1]) for n in model.nodes]
    new.labels = [replace(l, x=rot((l.x, l.y))[0], y=rot((l.x, l.y))[1]) for l in model.labels]
    new.dimensions = [
        replace(d, points=[rot(p) for p in d.points]) for d in model.dimensions
    ]

    mode = str(model.meta.get("ortho") or "").lower()
    if mode not in {"full", "iso", "straight", "none"}:
        # газовые схемы в ваших чертежах строго ортогональны,
        # тепловые — аксонометрические (оси 0°, ±30°, 90°)
        mode = "full" if model.network_type == "gas" else "iso"
    if mode == "none":
        return model

    if mode == "full":
        # трасса почти вся ортогональна — доводим до «монтажной» схемы
        paths = [orthogonal_path([rot(p) for p in seg.points], eps, ratio) for seg in model.segments]
        paths = _snap_to_axes(paths, tol=max(diag * 0.06, eps * 0.6))
    elif mode == "iso":
        paths = [_iso_walk([rot(p) for p in seg.points], eps) for seg in model.segments]
    else:
        # есть настоящие диагонали (тепловые трассы) — их не ломаем
        paths = [_straighten_path([rot(p) for p in seg.points], eps) for seg in model.segments]
    new_segments: list[Segment] = []
    merged: list[Point] = []
    for seg, path in zip(model.segments, paths):
        merged.extend(path)
        new_segments.append(replace(seg, points=path))
    new.segments = new_segments

    # посадка элементов на ось трубы
    if merged:
        bx0, by0, bx1, by1 = _bbox(merged)
        limit = 0.12 * math.hypot(bx1 - bx0, by1 - by0)
        placed = []
        for e in model.elements:
            p = rot(e.xy)
            best_q, best_d = p, limit
            for seg in new_segments:
                for a, b in zip(seg.points, seg.points[1:]):
                    q, d = _project_to_segment(p, a, b)
                    if d < best_d:
                        best_q, best_d = q, d
            placed.append(replace(e, x=best_q[0], y=best_q[1]))
        new.elements = placed
    else:
        new.elements = [replace(e, x=rot(e.xy)[0], y=rot(e.xy)[1]) for e in model.elements]

    new.meta = dict(model.meta)
    new.meta["orthogonalized"] = True
    new.meta["deskew_deg"] = round(math.degrees(angle), 2)
    return new

