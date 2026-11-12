"""Сцена → PDF/PNG (matplotlib). Тот же лист, что и в DXF, 1:1 в миллиметрах."""

from __future__ import annotations

import math
import os
from pathlib import Path

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

from .scene import Arc, Circle, DimLinear, Hatch, Insert, Line, Polyline, Prim, Scene, Solid, Text  # noqa: E402
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

DEFAULT_LW = {
    "FRAME": 0.6,
    "TITLE": 0.35,
    "DIM": 0.18,
    "TEXT": 0.18,
}


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


def render_scene(
    scene: Scene,
    path: str | Path,
    *,
    width_mm: float,
    height_mm: float,
    fmt: str | None = None,
    dpi: int = 220,
) -> Path:
    """Рендер сцены в PDF или PNG с точными размерами листа."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = (fmt or path.suffix.lstrip(".")).lower()

    fig = plt.figure(figsize=(width_mm / 25.4, height_mm / 25.4), dpi=dpi)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, width_mm)
    ax.set_ylim(0, height_mm)
    ax.set_aspect("equal")
    ax.axis("off")

    for prim in scene.prims:
        try:
            _draw(ax, prim)
        except Exception:
            continue

    if fmt == "png":
        fig.savefig(path, dpi=dpi, facecolor="white")
    else:
        fig.savefig(path, format="pdf", facecolor="white")
    plt.close(fig)
    return path


def _draw(ax, p: Prim) -> None:
    color = _color(p)
    lw = _lw(p)

    if isinstance(p, Line):
        ax.plot([p.a[0], p.b[0]], [p.a[1], p.b[1]], color=color, linewidth=lw,
                solid_capstyle="round", linestyle=render_dashes(p.layer) or "-")

    elif isinstance(p, Polyline):
        if len(p.points) < 2:
            return
        xs = [q[0] for q in p.points]
        ys = [q[1] for q in p.points]
        if p.closed:
            xs.append(p.points[0][0])
            ys.append(p.points[0][1])
        ax.plot(xs, ys, color=color, linewidth=lw, solid_capstyle="round", solid_joinstyle="miter",
                linestyle=render_dashes(p.layer) or "-")

    elif isinstance(p, Circle):
        ax.add_patch(MplCircle(p.c, p.r, fill=False, edgecolor=color, linewidth=lw))

    elif isinstance(p, Arc):
        ax.add_patch(MplArc(p.c, 2 * p.r, 2 * p.r, angle=0, theta1=p.a0, theta2=p.a1, edgecolor=color, linewidth=lw))

    elif isinstance(p, Solid):
        if len(p.points) < 3:
            return
        ax.add_patch(MplPolygon(p.points, closed=True, facecolor=color, edgecolor=color, linewidth=lw))

    elif isinstance(p, Hatch):
        ax.add_patch(
            MplPolygon(p.boundary, closed=True, facecolor=color if p.pattern.upper() == "SOLID" else "none",
                       edgecolor=color, linewidth=lw, hatch=None if p.pattern.upper() == "SOLID" else "///")
        )

    elif isinstance(p, Text):
        ha = {"left": "left", "center": "center", "right": "right"}.get(p.align, "left")
        va = {"bottom": "bottom", "middle": "center", "top": "top"}.get(p.valign, "bottom")
        ax.text(
            p.at[0],
            p.at[1],
            p.text,
            fontsize=max(p.height * MM_TO_PT, 1.0),
            color=color,
            ha=ha,
            va=va,
            rotation=p.rotation,
            rotation_mode="anchor",
            family="DejaVu Sans",
            fontweight="bold" if p.bold else "normal",
        )

    elif isinstance(p, Insert):
        # блоки в сцене не используются — символы рисуются примитивами
        return

    elif isinstance(p, DimLinear):
        ax.plot([p.p1[0], p.p2[0]], [p.p1[1], p.p2[1]], color=color, linewidth=lw, linestyle=(0, (4, 2)))
        if p.text:
            mx = (p.p1[0] + p.p2[0]) / 2
            my = (p.p1[1] + p.p2[1]) / 2
            ax.text(mx, my + 1.5, p.text, fontsize=2.4 * MM_TO_PT, ha="center", va="bottom", color=color)


def write_preview(scene: Scene, path: str | Path, *, width_mm: float, height_mm: float, dpi: int = 200) -> Path:
    return render_scene(scene, path, width_mm=width_mm, height_mm=height_mm, fmt="png", dpi=dpi)


def write_pdf(scene: Scene, path: str | Path, *, width_mm: float, height_mm: float) -> Path:
    return render_scene(scene, path, width_mm=width_mm, height_mm=height_mm, fmt="pdf")
