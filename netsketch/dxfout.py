"""Сцена → DXF (ezdxf). Единицы — миллиметры листа, 1:1."""

from __future__ import annotations

import math
from pathlib import Path

import ezdxf
from ezdxf import units
from ezdxf.enums import TextEntityAlignment

class DxfExportError(RuntimeError):
    """Не удалось вывести сцену в DXF."""


from .scene import (
    Arc,
    Circle,
    DimLinear,
    Hatch,
    Insert,
    Line,
    MLeader,
    Polyline,
    Prim,
    Scene,
    Solid,
    Text,
)
from .styles import DIM_STYLE, MLEADER_STYLE, TEXT_STYLE, apply_to_dxf

_ALIGN = {
    ("left", "bottom"): TextEntityAlignment.LEFT,
    ("center", "bottom"): TextEntityAlignment.CENTER,
    ("right", "bottom"): TextEntityAlignment.RIGHT,
    ("left", "middle"): TextEntityAlignment.MIDDLE_LEFT,
    ("center", "middle"): TextEntityAlignment.MIDDLE_CENTER,
    ("right", "middle"): TextEntityAlignment.MIDDLE_RIGHT,
    ("left", "top"): TextEntityAlignment.TOP_LEFT,
    ("center", "top"): TextEntityAlignment.TOP_CENTER,
    ("right", "top"): TextEntityAlignment.TOP_RIGHT,
}


def _attribs(p: Prim) -> dict:
    attribs: dict = {"layer": p.layer}
    if p.color is not None:
        attribs["color"] = int(p.color)
    if p.lw is not None:
        # 1/100 мм, только стандартные значения
        from .styles import snap_lw

        attribs["lineweight"] = snap_lw(p.lw)
    return attribs


def scene_to_dxf(scene: Scene, network_type: str, *, dxf_version: str = "R2018", dim_scale: int = 500):
    doc = ezdxf.new(dxf_version, setup=True)
    doc.units = units.MM
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = 1.0
    doc.header["$PSLTSCALE"] = 0

    if DIM_STYLE not in doc.dimstyles:
        ds = doc.dimstyles.add(DIM_STYLE)
    else:
        ds = doc.dimstyles.get(DIM_STYLE)
    ds.dxf.dimtxt = 2.5
    ds.dxf.dimasz = 2.0
    ds.dxf.dimexe = 1.5
    ds.dxf.dimexo = 1.0
    ds.dxf.dimgap = 1.0
    ds.dxf.dimlfac = float(dim_scale)
    ds.dxf.dimdec = 0
    ds.dxf.dimtad = 1
    ds.dxf.dimtih = 0
    ds.dxf.dimtoh = 0

    apply_to_dxf(doc, network_type)
    msp = doc.modelspace()

    failed: list[str] = []
    for prim in scene.prims:
        try:
            _add_prim(msp, prim)
        except Exception as exc:  # собираем, но не теряем молча
            failed.append(f"{type(prim).__name__}: {type(exc).__name__}: {exc}")

    if failed:
        # битый примитив значит неполный чертёж — это ошибка, а не «мелочь»
        raise DxfExportError(
            f"не удалось вывести примитивов: {len(failed)}; первый: {failed[0]}"
        )

    return doc


def _add_mleader(msp, p: "MLeader", at: dict) -> None:
    """Настоящий MULTILEADER: в CAD правится одним объектом (полка+текст+стрелки).

    Вершины ветки в DXF — это остриё и (для излома) точка излома; последняя
    точка поводка и вектор полки хранятся отдельно в `last_leader_point` /
    `dogleg_vector`. Если отдать builder'у всю ломаную, он допишет свою
    «собачью ножку» от острия к тексту — в DWG появляется лишняя линия
    через весь лист. Поэтому после build подменяем last_leader_point и
    dogleg на наши (полка под текстом / короткий поводок).
    """
    from ezdxf.math import Vec2, Vec3
    from ezdxf.render.mleader import ConnectionSide

    builder = msp.add_multileader_mtext(MLEADER_STYLE, dxfattribs=at)
    builder.set_content(p.text, char_height=max(p.height, 0.5))
    side = ConnectionSide.right if p.side == "right" else ConnectionSide.left
    groups: dict[object, tuple[Vec2, Vec2]] = {}
    for leader in p.leaders:
        if len(leader) < 2:
            continue
        tip = Vec2(*leader[-1])
        if len(leader) >= 3:
            elbow = Vec2(*leader[-2])
            far = Vec2(*leader[0])
        else:
            # прямая выноска: полки нет, last_leader_point = начало у текста
            elbow = Vec2(*leader[0])
            far = elbow
        builder.add_leader_line(side, [tip, elbow])
        groups[side] = (elbow, far)
    builder.build(insert=Vec2(*p.at))

    for leader_data, (elbow, far) in zip(builder.multileader.context.leaders, groups.values()):
        leader_data.last_leader_point = Vec3(elbow.x, elbow.y, 0)
        vec = Vec3(far.x - elbow.x, far.y - elbow.y, 0)
        length = vec.magnitude
        leader_data.dogleg_length = length
        if length > 1e-9:
            leader_data.dogleg_vector = vec.normalize()
            leader_data.has_dogleg_vector = 1
        else:
            leader_data.dogleg_vector = Vec3(1, 0, 0)
            leader_data.has_dogleg_vector = 0
    builder.multileader.update_proxy_graphic()


def _add_prim(msp, p: Prim) -> None:
    at = _attribs(p)
    if isinstance(p, Line):
        msp.add_line(p.a, p.b, dxfattribs=at)
    elif isinstance(p, Polyline):
        if len(p.points) < 2:
            return
        msp.add_lwpolyline(p.points, close=p.closed, dxfattribs=at)
    elif isinstance(p, Circle):
        msp.add_circle(p.c, p.r, dxfattribs=at)
    elif isinstance(p, Arc):
        msp.add_arc(p.c, p.r, p.a0, p.a1, dxfattribs=at)
    elif isinstance(p, Solid):
        pts = p.points
        if len(pts) == 3:
            msp.add_solid(pts, dxfattribs=at)
        elif len(pts) == 4:
            # порядок обхода DXF SOLID: 1-2-4-3
            msp.add_solid([pts[0], pts[1], pts[3], pts[2]], dxfattribs=at)
    elif isinstance(p, Hatch):
        if len(p.boundary) < 3:
            return
        hatch = msp.add_hatch(dxfattribs=at)
        if p.pattern.upper() == "SOLID":
            hatch.set_solid_fill(color=p.color or 7)
        else:
            hatch.set_pattern_fill(p.pattern, scale=1.0)
        hatch.paths.add_polyline_path(p.boundary, is_closed=True)
    elif isinstance(p, Text):
        attribs = dict(at)
        from .styles import text_style_for

        attribs["style"] = text_style_for(bold=p.bold, serif=p.serif, italic=p.italic)
        attribs["rotation"] = p.rotation
        attribs["width"] = p.width_factor
        height = max(p.height, 0.5)
        entity = msp.add_text(p.text, height=height, dxfattribs=attribs)
        align = _ALIGN.get((p.align, p.valign), TextEntityAlignment.LEFT)
        entity.set_placement(p.at, align=align)
    elif isinstance(p, Insert):
        msp.add_blockref(p.name, p.at, dxfattribs={**at, "rotation": p.rotation, "xscale": p.scale, "yscale": p.scale})
    elif isinstance(p, MLeader):
        _add_mleader(msp, p, at)
    elif isinstance(p, DimLinear):
        dim = msp.add_linear_dim(
            base=p.base or ((p.p1[0] + p.p2[0]) / 2, (p.p1[1] + p.p2[1]) / 2 - 8),
            p1=p.p1,
            p2=p.p2,
            angle=p.angle,
            dimstyle=DIM_STYLE,
            dxfattribs=at,
        )
        if p.text:
            dim.dimension.dxf.text = p.text
        dim.render()


def save_dxf(scene: Scene, path: str | Path, network_type: str = "gas", *, dim_scale: int = 500) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = scene_to_dxf(scene, network_type, dim_scale=dim_scale)
    doc.saveas(str(path))
    return path
