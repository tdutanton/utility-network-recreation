"""Раскладка: семантическая модель → сцена листа (мм).

Здесь решается всё, что делает чертёж «как у человека»:
  * пересчёт пикселей эскиза в миллиметры и выбор масштаба;
  * размещение плана в поле чертежа, чтобы ничего не наезжало на штамп;
  * легенда, примечания, спецификация — в правой колонке;
  * пометки ASSUMED на отдельном слое.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .model import ASSUMED, ELEMENT_TYPES, Model, Segment
from .scene import Circle, Line, Polyline, Prim, Scene, Solid, Text, text_width
from .sheets import Sheet
from .styles import layer_of
from .symbols import draw_symbol

SCALE_SERIES = [50, 100, 200, 250, 400, 500, 750, 1000, 1500, 2000, 2500, 5000]


@dataclass
class Transform:
    scale: int
    mm_per_px: float
    bbox: tuple[float, float, float, float]
    origin: tuple[float, float]

    def pt(self, p: tuple[float, float]) -> tuple[float, float]:
        x0, y0, _, y1 = self.bbox
        # пиксели → реальные мм → мм бумаги
        px_per_mm = self.mm_per_px / self.scale
        return (
            self.origin[0] + (p[0] - x0) * px_per_mm,
            self.origin[1] + (y1 - p[1]) * px_per_mm,
        )

    def length(self, px: float) -> float:
        return px * self.mm_per_px / self.scale

    def diameter_lw(self, mm: int | None) -> float:
        if not mm:
            return 0.35
        if mm <= 50:
            return 0.35
        if mm <= 150:
            return 0.5
        if mm <= 400:
            return 0.7
        return 0.9


@dataclass
class LayoutInfo:
    scale: int = 500
    mm_per_px: float = 1.0
    warnings: list[str] = field(default_factory=list)
    assumed: list[str] = field(default_factory=list)
    drawn_elements: int = 0
    plan_bounds: tuple[float, float, float, float] | None = None
    has_dimensions: bool = False


# ----------------------------------------------------------------------
def _estimate_mm_per_px(model: Model) -> tuple[float, bool]:
    """Оценка масштаба эскиза. Возвращает (мм/пиксель, домыслено ли)."""
    if model.mm_per_px:
        return float(model.mm_per_px), False

    bbox = model.bbox()
    if not bbox:
        return 1.0, True
    width_px = max(bbox[2] - bbox[0], 1.0)
    height_px = max(bbox[3] - bbox[1], 1.0)

    path_px = sum(s.length_px for s in model.segments)
    total_m = model.total_length_m()
    if total_m and path_px > 1:
        return total_m * 1000.0 / path_px, False

    # Нет ни калибровки, ни ведомости — считаем, что эскиз покрывает ~60 м.
    span = max(width_px, height_px)
    return 60000.0 / span, True


def _pick_scale(
    bbox: tuple[float, float, float, float], mm_per_px: float, avail_w: float, avail_h: float
) -> int:
    w_mm = (bbox[2] - bbox[0]) * mm_per_px
    h_mm = (bbox[3] - bbox[1]) * mm_per_px
    for scale in SCALE_SERIES:
        if w_mm / scale <= avail_w * 0.98 and h_mm / scale <= avail_h * 0.98:
            return scale
    return SCALE_SERIES[-1]


def _apply_transform(
    model: Model, sheet: Sheet, plan: tuple[float, float, float, float]
) -> tuple[Transform, LayoutInfo]:
    info = LayoutInfo()
    bbox = model.bbox()
    if not bbox:
        bbox = (0.0, 0.0, 100.0, 100.0)
    mm_per_px, assumed = _estimate_mm_per_px(model)
    info.mm_per_px = mm_per_px
    if assumed:
        msg = (
            "Масштаб эскиза не подтверждён: нет калибровочного размера. "
            "Принято, что эскиз покрывает ≈60 м, масштаб условный."
        )
        info.warnings.append(msg)
        info.assumed.append(msg)

    pad = 6.0
    avail_w = max(plan[2] - plan[0] - 2 * pad, 20.0)
    avail_h = max(plan[3] - plan[1] - 2 * pad, 20.0)
    scale = _pick_scale(bbox, mm_per_px, avail_w, avail_h)

    w = (bbox[2] - bbox[0]) * mm_per_px / scale
    h = (bbox[3] - bbox[1]) * mm_per_px / scale
    ox = plan[0] + pad + max((avail_w - w) / 2, 0)
    oy = plan[1] + pad + max((avail_h - h) / 2, 0)
    info.scale = scale
    info.plan_bounds = (ox, oy, ox + w, oy + h)
    return Transform(scale=scale, mm_per_px=mm_per_px, bbox=bbox, origin=(ox, oy)), info


# ----------------------------------------------------------------------
def _offset_polyline(points: list[tuple[float, float]], dist: float) -> list[tuple[float, float]]:
    """Смещение ломаной влево от направления движения (по сегментам)."""
    out: list[tuple[float, float]] = []
    for a, b in zip(points, points[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        out.append((a[0] + nx * dist, a[1] + ny * dist))
        out.append((b[0] + nx * dist, b[1] + ny * dist))
    # схлопываем дубли в стыках
    merged: list[tuple[float, float]] = []
    for p in out:
        if not merged or math.dist(merged[-1], p) > 0.01:
            merged.append(p)
    return merged


def _segment_direction(points: list[tuple[float, float]]) -> float:
    a, b = points[0], points[-1]
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _node_degrees(model: Model) -> dict[tuple[float, float], int]:
    deg: dict[tuple[float, float], int] = {}
    for s in model.segments:
        for p in (s.points[0], s.points[-1]):
            key = (round(p[0], 3), round(p[1], 3))
            deg[key] = deg.get(key, 0) + 1
    return deg


def _draw_pipe(
    scene: Scene,
    pts: list[tuple[float, float]],
    *,
    layer: str,
    lw: float,
    state: str,
) -> None:
    if len(pts) == 2:
        scene.add(Line(a=pts[0], b=pts[1], layer=layer, lw=lw, state=state))
    else:
        scene.add(Polyline(points=pts, layer=layer, lw=lw, state=state))


def _draw_ticks(scene: Scene, pts: list[tuple[float, float]], *, layer: str, lw: float, state: str, deg: dict) -> None:
    d = 2.0
    for end, p in (("start", pts[0]), ("end", pts[-1])):
        key = (round(p[0], 3), round(p[1], 3))
        if deg.get(key, 0) < 1:
            continue
        if end == "start":
            nxt = pts[1] if len(pts) > 1 else p
            dx, dy = nxt[0] - p[0], nxt[1] - p[1]
        else:
            prev = pts[-2] if len(pts) > 1 else p
            dx, dy = p[0] - prev[0], p[1] - prev[1]
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        scene.add(Line(a=(p[0] - nx * d, p[1] - ny * d), b=(p[0] + nx * d, p[1] + ny * d), layer=layer, lw=lw, state=state))


def _draw_dim_chain(scene: Scene, pts: list[tuple[float, float]], values_mm: list[int], centroid, lw=0.18) -> None:
    """Размерная цепь по точкам с засечками и подписями."""
    if len(pts) < 2:
        return
    # сторона смещения — от центра геометрии
    a, b = pts[0], pts[1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    sign = -1.0 if (mid[0] - centroid[0]) * nx + (mid[1] - centroid[1]) * ny > 0 else 1.0
    off = 10.0
    shifted = [(p[0] + nx * off * sign, p[1] + ny * off * sign) for p in pts]
    scene.add(Polyline(points=shifted, layer="DIM", lw=lw))

    for i, (p0, p1) in enumerate(zip(pts, shifted)):
        scene.add(Line(a=p0, b=p1, layer="DIM", lw=lw))
    # засечки
    for p in shifted:
        scene.add(Line(a=(p[0] - 1.0, p[1] - 1.0), b=(p[0] + 1.0, p[1] + 1.0), layer="DIM", lw=lw))

    for i, (p0, p1) in enumerate(zip(shifted, shifted[1:])):
        value = values_mm[i] if i < len(values_mm) else None
        if not value:
            continue
        cx, cy = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
        if ang > 90 or ang < -90:
            ang += 180
        scene.add(
            Text(
                text=fmt_mm(int(value)),
                at=(cx, cy + 1.6),
                height=2.0,
                rotation=ang,
                layer="DIM",
                align="center",
            )
        )


def fmt_mm(value: int | float) -> str:
    """24000 → «24 000» (как в рукописных эскизах)."""
    return f"{int(value):,}".replace(",", " ")


def _wrap(text: str, width_mm: float, height: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        probe = (current + " " + w).strip()
        if text_width(probe, height) <= width_mm or not current:
            current = probe
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines or [""]


# ----------------------------------------------------------------------
def build_scene(
    model: Model,
    *,
    sheet: Sheet | None = None,
    title: dict[str, str] | None = None,
    scale_override: int | None = None,
) -> tuple[Scene, LayoutInfo]:
    sheet = sheet or Sheet(model.sheet, model.orientation)
    scene = Scene()
    info = LayoutInfo()

    title = dict(title or {})
    title.setdefault("drawing_name", model.title.drawing_name or "Схема сети")
    title.setdefault("project", model.title.project)
    title.setdefault("address", model.title.address)
    title.setdefault("stage", model.title.stage or "Р")
    title.setdefault("sheet", model.title.sheet or "1")
    title.setdefault("total", model.title.total or "1")
    title.setdefault("organization", model.title.organization)
    title.setdefault("developer", model.title.developer)
    title.setdefault("checker", model.title.checker)

    # правая колонка под легенду и таблицы
    legend_width = 0.0
    if sheet.width >= 800:
        legend_width = 130.0
    elif sheet.width >= 560:
        legend_width = 118.0
    elif sheet.width >= 400:
        legend_width = 96.0
    elif sheet.width >= 280:
        legend_width = 72.0
    else:
        legend_width = 58.0

    plan = sheet.plan_area(legend_width=legend_width)

    transform, tinfo = _apply_transform(model, sheet, plan)
    info.warnings.extend(tinfo.warnings)
    info.assumed.extend(tinfo.assumed)
    if scale_override:
        transform.scale = scale_override
        info.scale = scale_override
    info.mm_per_px = transform.mm_per_px
    info.scale = transform.scale

    centroid_px = (
        (transform.bbox[0] + transform.bbox[2]) / 2,
        (transform.bbox[1] + transform.bbox[3]) / 2,
    )
    deg = _node_degrees(model)

    # ---------------- трубопроводы ----------------
    prev_seg = None
    for seg in model.segments:
        pts = [transform.pt(p) for p in seg.points]
        layer = layer_of(model.network_type, seg.kind)
        lw = transform.diameter_lw(seg.diameter_mm)
        state = seg.state
        if model.network_type == "heat" and model.is_two_pipe() and seg.kind in {"main", "supply"}:
            scene.add(Polyline(points=pts, layer=layer_of(model.network_type, "supply"), lw=lw, state=state))
            back_pts = _offset_polyline(pts, 2.2)
            scene.add(
                Polyline(points=back_pts, layer=layer_of(model.network_type, "return"), lw=lw, state=state)
            )
        else:
            _draw_pipe(scene, pts, layer=layer, lw=lw, state=state)
        _draw_ticks(scene, pts, layer=layer, lw=lw, state=state, deg=deg)

        # подпись диаметра — один раз на цепочку одинаковых диаметров,
        # и только если человек не подписал её сам
        continues = (
            prev_seg is not None
            and prev_seg.diameter_mm == seg.diameter_mm
            and _shares_endpoint(prev_seg, seg)
        )
        if seg.diameter_mm and not continues:
            mid = _midpoint(pts)
            label = f"Ø{seg.diameter_mm}"
            if model.network_type == "heat" and seg.length_mm:
                label += f" L={seg.length_mm / 1000:.1f} м"
            if not _has_manual_diameter_label(model, transform, label, mid):
                _place_along_text(
                    scene,
                    label,
                    mid,
                    _segment_direction(pts),
                    layer=layer_of(model.network_type, "label"),
                    state=state,
                    away_from=transform.pt(centroid_px),
                )
        prev_seg = seg

    # ---------------- узлы-соединения ----------------
    for key, count in deg.items():
        p = transform.pt(key)
        if count >= 3:
            scene.add(Circle(c=p, r=0.7, layer=layer_of(model.network_type, "equip"), lw=0.35))
            info.drawn_elements += 1

    # ---------------- арматура и оборудование ----------------
    for e in model.elements:
        p = transform.pt(e.xy)
        layer = layer_of(model.network_type, "equip")
        prims = draw_symbol(
            scene,
            e.type,
            p,
            size=4.4 * (e.size or 1.0),
            rotation=e.rotation,
            layer=layer_of(model.network_type, "equip") if e.state != ASSUMED else "ASSUMED",
            state=e.state,
        )
        info.drawn_elements += len(prims)
        if e.label:
            # у камер/колодцев подпись уходит вправо, чтобы не спорить с трассой
            if e.type in {"well", "pit", "gpsh", "meter"}:
                pos, align = (p[0] + 5.5, p[1] - 1.0), "left"
            else:
                pos, align = (p[0], p[1] - 6.2), "center"
            scene.add(
                Text(
                    text=e.label,
                    at=pos,
                    height=2.0,
                    layer=layer_of(model.network_type, "label"),
                    align=align,
                    state=e.state,
                )
            )

    # ---------------- размеры ----------------
    for d in model.dimensions:
        pts = [transform.pt(p) for p in d.points]
        values = d.values_mm or [
            int(round(math.dist(pts[i], pts[i + 1]) * transform.scale)) for i in range(len(pts) - 1)
        ]
        _draw_dim_chain(scene, pts, values, transform.pt(centroid_px))
        info.has_dimensions = True

    if info.has_dimensions:
        scene.add(
            Text(
                text="Размеры в миллиметрах",
                at=(plan[0] + 1, max(plan[1] + 1, 6)),
                height=2.2,
                layer="DIM",
            )
        )

    # ---------------- свободные подписи ----------------
    for lbl in model.labels:
        p = transform.pt((lbl.x, lbl.y))
        scene.add(
            Text(
                text=lbl.text,
                at=p,
                height=max(lbl.height, 2.0),
                rotation=lbl.rotation,
                layer=layer_of(model.network_type, "label") if lbl.state != ASSUMED else "ASSUMED",
                state=lbl.state,
            )
        )

    # ---------------- рамка и штамп ----------------
    scale_text = f"1:{transform.scale}"
    sheet.draw(
        scene,
        title=title,
        scale_text=scale_text,
        doc_code=title.get("doc_code", ""),
    )

    # ---------------- правая колонка ----------------
    if legend_width:
        _draw_right_column(
            scene,
            model,
            sheet,
            x0=plan[2] + 4,
            x1=sheet.frame[2] - 4,
            y_top=sheet.frame[3] - 4,
            y_bottom=sheet.title_block[3] + 4,
            info=info,
        )

    # ---------------- домысленные данные ----------------
    if info.assumed or model.assumptions:
        model.assumptions = list(dict.fromkeys(model.assumptions + info.assumed))

    return scene, info


def _shares_endpoint(a: Segment, b: Segment) -> bool:
    for p in (a.points[0], a.points[-1]):
        for q in (b.points[0], b.points[-1]):
            if math.dist(p, q) < 2.0:
                return True
    return False


def _has_manual_diameter_label(model: Model, transform: Transform, label: str, at) -> bool:
    """Есть ли уже подпись диаметра рядом (чтобы не дублировать)."""
    for lbl in model.labels:
        if lbl.role != "diameter":
            continue
        if "Ø" not in lbl.text and "D" not in lbl.text.upper():
            continue
        p = transform.pt((lbl.x, lbl.y))
        if math.dist(p, at) < 30.0:
            return True
    return False


def _midpoint(pts: list[tuple[float, float]]) -> tuple[float, float]:
    total = sum(math.dist(a, b) for a, b in zip(pts, pts[1:])) or 1.0
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        seg = math.dist(a, b)
        if acc + seg >= total / 2:
            t = (total / 2 - acc) / seg if seg else 0
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        acc += seg
    return pts[0]


def _place_along_text(
    scene: Scene,
    text: str,
    at: tuple[float, float],
    angle: float,
    *,
    layer: str,
    state: str,
    away_from: tuple[float, float] | None = None,
) -> None:
    """Подпись вдоль линии, смещённая в сторону от посторонней геометрии."""
    a = angle
    if a > 90 or a < -90:
        a += 180
    rad = math.radians(angle + 90)
    dx, dy = math.cos(rad), math.sin(rad)
    if away_from is not None:
        vx, vy = at[0] - away_from[0], at[1] - away_from[1]
        if dx * vx + dy * vy < 0:
            dx, dy = -dx, -dy
    offset = 3.2
    pos = (at[0] + dx * offset, at[1] + dy * offset)
    scene.add(Text(text=text, at=pos, height=2.2, rotation=a, layer=layer, align="center", state=state))


# ----------------------------------------------------------------------
def _draw_right_column(
    scene: Scene,
    model: Model,
    sheet: Sheet,
    *,
    x0: float,
    x1: float,
    y_top: float,
    y_bottom: float,
    info: LayoutInfo,
) -> None:
    width = x1 - x0
    y = y_top

    # 1. Легенда
    items = list(model.legend)
    used = model.used_element_types()
    if not items:
        for t in used:
            items.append(type("L", (), {"symbol": t, "text": ELEMENT_TYPES.get(t, t)})())
    if items:
        heading_h = 6.0
        scene.add(Text(text="Условные обозначения", at=(x0, y - 4.0), height=2.8, layer="LEGEND"))
        y -= heading_h
        scene.add(Line(a=(x0, y), b=(x1, y), layer="LEGEND", lw=0.35))
        y -= 0.5
        row_h = 7.0
        for item in items:
            if y - row_h < y_bottom:
                info.warnings.append("Легенда не поместилась полностью — сократите число позиций.")
                break
            sym_center = (x0 + 6.0, y - row_h / 2)
            draw_symbol(scene, item.symbol, sym_center, size=4.0, layer="LEGEND")
            lines = _wrap(item.text, width - 18.0, 2.2)
            ty = y - 3.0
            for ln in lines[:2]:
                scene.add(Text(text=ln, at=(x0 + 14.0, ty), height=2.2, layer="LEGEND"))
                ty -= 2.6
            y -= row_h
        y -= 2.0

    # 2. Спецификация
    spec = list(model.specification)
    if not spec and model.segments:
        agg: dict[int, float] = {}
        for s in model.segments:
            if s.diameter_mm:
                length_m = (s.length_mm / 1000.0) if s.length_mm else transform_length_m(s, info, model)
                agg[s.diameter_mm] = agg.get(s.diameter_mm, 0.0) + (length_m or 0.0)
        for d, length in sorted(agg.items()):
            spec.append(type("R", (), {"diameter_mm": d, "length_m": length, "count": None, "note": "", "name": ""})())
    if spec:
        rows = min(len(spec), 12)
        table_h = 8.0 + rows * 5.2
        if y - table_h > y_bottom:
            y = _draw_spec_table(scene, spec, x0, x1, y, rows)
            y -= 3.0

    # 3. Примечания
    notes = list(model.notes)
    if model.assumptions:
        notes.append("Данные, помеченные как ASSUMED, требуют подтверждения (слой ASSUMED).")
        notes.extend(model.assumptions[:4])
    if notes:
        scene.add(Text(text="Примечания:", at=(x0, y - 3.6), height=2.6, layer="TEXT"))
        y -= 7.0
        for i, note in enumerate(notes, 1):
            for j, ln in enumerate(_wrap(note, width - 6.0, 2.0)):
                if y - 3.2 < y_bottom:
                    info.warnings.append("Примечания не поместились на лист.")
                    return
                prefix = f"{i}. " if j == 0 else "   "
                scene.add(Text(text=prefix + ln, at=(x0, y - 2.4), height=2.0, layer="TEXT"))
                y -= 3.1
            y -= 0.8

    # 4. Пометка о неподтверждённых данных
    if model.assumptions and y - 6 > y_bottom:
        scene.add(
            Text(
                text="ASSUMED — требует подтверждения",
                at=(x0, y - 4),
                height=2.0,
                layer="ASSUMED",
            )
        )


def transform_length_m(seg: Segment, info: LayoutInfo, model: Model) -> float | None:
    if not seg.length_px:
        return None
    return seg.length_px * info.mm_per_px / 1000.0


def _fit_text(value: str, width_mm: float, height: float) -> str:
    """Обрезает строку под ширину колонки с многоточием."""
    if text_width(value, height) <= width_mm:
        return value
    probe = value
    while probe and text_width(probe + "…", height) > width_mm:
        probe = probe[:-1]
    return (probe.rstrip() + "…") if probe else ""


def _draw_spec_table(scene: Scene, spec, x0: float, x1: float, y_top: float, rows: int) -> float:
    width = x1 - x0
    cols = [0.0, 0.34, 0.72, 0.88, 1.0]
    pad = 1.0
    row_h = 5.2
    header_h = 9.0
    scene.add(Text(text="Спецификация трубопроводов", at=(x0, y_top - 3.6), height=2.6, layer="TABLE"))
    y = y_top - 7.0
    scene.add(Line(a=(x0, y), b=(x1, y), layer="TABLE", lw=0.5))
    headers = ["№", "Ø, мм", "Длина, м", "Кол."]
    for i, h in enumerate(headers):
        cell_w = width * (cols[i + 1] - cols[i]) - 2 * pad
        scene.add(
            Text(
                text=_fit_text(h, cell_w, 1.9),
                at=(x0 + width * cols[i] + pad, y - 2.2),
                height=1.9,
                layer="TABLE",
            )
        )
    y -= header_h - 3.0
    for i in range(1, 5):
        scene.add(Line(a=(x0 + width * cols[i], y_top - 7.0), b=(x0 + width * cols[i], y), layer="TABLE", lw=0.18))
    scene.add(Line(a=(x0, y), b=(x1, y), layer="TABLE", lw=0.35))

    for idx, row in enumerate(spec[:rows], 1):
        y -= row_h
        scene.add(Line(a=(x0, y), b=(x1, y), layer="TABLE", lw=0.18))
        vals = [
            str(idx),
            f"Ø{row.diameter_mm}" if row.diameter_mm else (row.name or "—"),
            f"{row.length_m:.1f}" if row.length_m else "—",
            str(row.count) if row.count else "—",
        ]
        for i, v in enumerate(vals):
            cell_w = width * (cols[i + 1] - cols[i]) - 2 * pad
            scene.add(
                Text(
                    text=_fit_text(v, cell_w, 2.1),
                    at=(x0 + width * cols[i] + pad, y + 1.4),
                    height=2.1,

                    layer="TABLE",
                )
            )
    for i in range(1, 5):
        scene.add(Line(a=(x0 + width * cols[i], y_top - 7.0), b=(x0 + width * cols[i], y), layer="TABLE", lw=0.18))
    return y

