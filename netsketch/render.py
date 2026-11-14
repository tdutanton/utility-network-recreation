"""Сцена → PDF/PNG (matplotlib). Тот же лист, что и в DXF, 1:1 в миллиметрах."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Callable

# matplotlib любит писать кэш в %LOCALAPPDATA%; в песочнице это может быть
# закрыто, поэтому уводим кэш в папку проекта.
_CACHE = Path(__file__).resolve().parent.parent / ".cache" / "matplotlib"
_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_CACHE))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Arc as MplArc  # noqa: E402
from matplotlib.patches import Circle as MplCircle  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402

from .scene import (  # noqa: E402
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
from .styles import render_dashes  # noqa: E402

MM_TO_PT = 72.0 / 25.4

ACI_RGB = {
    1: "#c00000",
    2: "#b09000",
    3: "#007a3d",
    4: "#00708c",
    5: "#1f4fa8",
    6: "#a0208f",
    7: "#111111",
    8: "#7a7a7a",
    9: "#b0b0b0",
    250: "#444444",
}

# Толщины по слоям — ОДИН источник (styles), иначе DXF и PDF разойдутся.
from .styles import LAYER_LW  # noqa: E402

DEFAULT_LW = LAYER_LW


def _color(prim: Prim) -> str:
    if prim.color:
        return ACI_RGB.get(int(prim.color), "#111111")
    if prim.layer == "ASSUMED":
        return ACI_RGB[6]
    if prim.layer == "AXIS":
        return ACI_RGB[8]
    return "#111111"


def _lw(prim: Prim) -> float:
    width = prim.lw if prim.lw is not None else DEFAULT_LW.get(prim.layer, 0.25)
    return max(width * MM_TO_PT, 0.35)


# Шрифты эталона: Arial для штампов и подписей, Times New Roman Italic —
# итоговый блок. Берём первый установленный, иначе DejaVu (есть с matplotlib).
_FONT_FAMILIES = {
    False: ("Arial", "Liberation Sans", "DejaVu Sans"),
    True: ("Times New Roman", "Liberation Serif", "DejaVu Serif"),
}
_FONT_CACHE: dict[bool, str] = {}


def _font_family(serif: bool) -> str:
    if serif not in _FONT_CACHE:
        import logging

        from matplotlib import font_manager

        logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
        chosen = _FONT_FAMILIES[serif][-1]
        for name in _FONT_FAMILIES[serif]:
            try:
                font_manager.findfont(font_manager.FontProperties(family=name), fallback_to_default=False)
                chosen = name
                break
            except Exception:
                continue
        _FONT_CACHE[serif] = chosen
    return _FONT_CACHE[serif]


Transform = Callable[[tuple[float, float]], tuple[float, float]]


def _mpl_arrow(ax, start, end, color, lw: float, size: float = 1.8) -> None:
    """Стрелка на конце выноски (как в MULTILEADER эталона)."""
    ang = math.atan2(end[1] - start[1], end[0] - start[0])
    for sign in (+1, -1):
        a2 = ang + math.pi + sign * math.radians(16)
        ax.plot(
            [end[0], end[0] + size * math.cos(a2)],
            [end[1], end[1] + size * math.sin(a2)],
            color=color,
            linewidth=lw,
            solid_capstyle="round",
        )


def render_scene(
    scene: Scene,
    path: str | Path,
    *,
    width_mm: float,
    height_mm: float,
    fmt: str | None = None,
    dpi: int = 220,
    page: tuple[float, float] | None = None,
    transform: Transform | None = None,
    rotation_delta: float = 0.0,
) -> Path:
    """Рендер сцены в PDF или PNG.

    `width_mm × height_mm` — размер листа в мм (то, что в сцене).
    `page` и `transform` — печать: страница другого размера и отображение
    точек листа на страницу (например, A3 → A4 с поворотом на 90°).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = (fmt or path.suffix.lstrip(".")).lower()

    page_w, page_h = page or (width_mm, height_mm)
    fig = plt.figure(figsize=(page_w / 25.4, page_h / 25.4), dpi=dpi)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.set_aspect("equal")
    ax.axis("off")

    def P(p: tuple[float, float]) -> tuple[float, float]:
        return transform(p) if transform else p

    # масштаб печати: во сколько раз страница меньше/больше листа
    o = P((0.0, 0.0))
    u = P((1.0, 0.0))
    k = math.hypot(u[0] - o[0], u[1] - o[1]) or 1.0

    for prim in scene.prims:
        try:
            _draw(ax, prim, P, k, rotation_delta)
        except Exception:
            continue

    if fmt == "png":
        fig.savefig(path, dpi=dpi, facecolor="white")
    else:
        fig.savefig(path, format="pdf", facecolor="white")
    plt.close(fig)
    return path


def _draw(ax, p: Prim, P: Transform | None = None, k: float = 1.0, rotation_delta: float = 0.0) -> None:
    """Один примитив. P — отображение мм листа на мм страницы (печать)."""
    if P is None:

        def P(pt: tuple[float, float]) -> tuple[float, float]:  # noqa: E306
            return pt

    color = _color(p)
    lw = _lw(p) * k

    if isinstance(p, Line):
        a, b = P(p.a), P(p.b)
        ax.plot([a[0], b[0]], [a[1], b[1]], color=color, linewidth=lw,
                solid_capstyle="round", linestyle=render_dashes(p.layer) or "-")

    elif isinstance(p, Polyline):
        if len(p.points) < 2:
            return
        pts = [P(q) for q in p.points]
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        if p.closed:
            xs.append(pts[0][0])
            ys.append(pts[0][1])
        ax.plot(xs, ys, color=color, linewidth=lw, solid_capstyle="round", solid_joinstyle="miter",
                linestyle=render_dashes(p.layer) or "-")

    elif isinstance(p, Circle):
        ax.add_patch(MplCircle(P(p.c), p.r * k, fill=False, edgecolor=color, linewidth=lw))

    elif isinstance(p, Arc):
        ax.add_patch(MplArc(P(p.c), 2 * p.r * k, 2 * p.r * k, angle=rotation_delta,
                            theta1=p.a0, theta2=p.a1, edgecolor=color, linewidth=lw))

    elif isinstance(p, Solid):
        if len(p.points) < 3:
            return
        ax.add_patch(MplPolygon([P(q) for q in p.points], closed=True, facecolor=color,
                                edgecolor=color, linewidth=lw))

    elif isinstance(p, Hatch):
        ax.add_patch(
            MplPolygon([P(q) for q in p.boundary], closed=True,
                       facecolor=color if p.pattern.upper() == "SOLID" else "none",
                       edgecolor=color, linewidth=lw, hatch=None if p.pattern.upper() == "SOLID" else "///")
        )

    elif isinstance(p, Text):
        ha = {"left": "left", "center": "center", "right": "right"}.get(p.align, "left")
        va = {"bottom": "bottom", "middle": "center", "top": "top"}.get(p.valign, "bottom")
        at = P(p.at)
        ax.text(
            at[0],
            at[1],
            p.text,
            fontsize=max(p.height * MM_TO_PT * k, 0.8),
            color=color,
            ha=ha,
            va=va,
            rotation=p.rotation + rotation_delta,
            rotation_mode="anchor",
            family=_font_family(p.serif),
            fontstyle="italic" if p.italic else "normal",
            fontweight="bold" if p.bold else "normal",
        )

    elif isinstance(p, MLeader):
        # выноска MULTILEADER: полка + ветки (в PDF рисуем те же линии и текст)
        for leader in p.leaders:
            if len(leader) < 2:
                continue
            pts = [P(q) for q in leader]
            xs = [q[0] for q in pts]
            ys = [q[1] for q in pts]
            ax.plot(xs, ys, color=color, linewidth=lw, solid_capstyle="round",
                    solid_joinstyle="miter", linestyle=render_dashes(p.layer) or "-")
            if p.arrow:
                _mpl_arrow(ax, pts[-2], pts[-1], color, lw)
        at = P(p.at)
        ax.text(
            at[0],
            at[1],
            p.text,
            fontsize=max(p.height * MM_TO_PT * k, 0.8),
            color=color,
            ha="left",
            va="bottom",
            rotation=rotation_delta,
            rotation_mode="anchor",
            family=_font_family(False),
        )

    elif isinstance(p, Insert):
        # блоки в сцене не используются — символы рисуются примитивами
        return

    elif isinstance(p, DimLinear):
        a, b = P(p.p1), P(p.p2)
        ax.plot([a[0], b[0]], [a[1], b[1]], color=color, linewidth=lw, linestyle=(0, (4, 2)))
        if p.text:
            mx = (a[0] + b[0]) / 2
            my = (a[1] + b[1]) / 2
            ax.text(mx, my + 1.5 * k, p.text, fontsize=max(2.4 * MM_TO_PT * k, 0.8),
                    ha="center", va="bottom", color=color, family=_font_family(False))


def write_preview(scene: Scene, path: str | Path, *, width_mm: float, height_mm: float, dpi: int = 200) -> Path:
    return render_scene(scene, path, width_mm=width_mm, height_mm=height_mm, fmt="png", dpi=dpi)


def write_pdf(scene: Scene, path: str | Path, *, width_mm: float, height_mm: float) -> Path:
    return render_scene(scene, path, width_mm=width_mm, height_mm=height_mm, fmt="pdf")


def write_print_pdf(
    scene: Scene,
    path: str | Path,
    *,
    width_mm: float,
    height_mm: float,
    page: tuple[float, float],
    transform: Transform,
    dpi: int = 220,
) -> Path:
    """Печатный PDF: тот же лист, повёрнутый и вписанный в другую страницу."""
    return render_scene(
        scene,
        path,
        width_mm=width_mm,
        height_mm=height_mm,
        fmt="pdf",
        page=page,
        transform=transform,
        rotation_delta=-90.0,
        dpi=dpi,
    )


def write_print_png(
    scene: Scene,
    path: str | Path,
    *,
    width_mm: float,
    height_mm: float,
    page: tuple[float, float],
    transform: Transform,
    dpi: int = 200,
) -> Path:
    return render_scene(
        scene,
        path,
        width_mm=width_mm,
        height_mm=height_mm,
        fmt="png",
        page=page,
        transform=transform,
        rotation_delta=-90.0,
        dpi=dpi,
    )
