"""Форматы листов, рамка и основная надпись (ГОСТ 2.104, форма 1 и 2).

Форма 1 — штамп 185×55 в правом нижнем углу (альбомные листы).
Форма 2 — тот же штамп, повёрнутый на 90° и прижатый к левому краю:
так оформлены чертежи в examples/ (A4/A3 портрет, штамп слева).
"""

from __future__ import annotations

from dataclasses import dataclass

from .scene import Line, Scene, Text, rotate_point

# ГОСТ 2.301: размеры в мм (портрет: ширина × высота).
FORMATS: dict[str, tuple[int, int]] = {
    "A4": (210, 297),
    "A3": (297, 420),
    "A2": (420, 594),
    "A1": (594, 841),
    "A0": (841, 1189),
}

FORMAT_ALIASES = {
    "А4": "A4",
    "А3": "A3",
    "А2": "A2",
    "А1": "A1",
    "А0": "A0",
    "A4X3": "A3",
}

MARGIN_LEFT = 20.0
MARGIN_OTHER = 5.0
TITLE_W = 185.0
TITLE_H = 55.0


@dataclass
class Sheet:
    format: str = "A4"
    orientation: str = "portrait"
    stamp: str = "horizontal"  # horizontal (форма 1) | vertical (форма 2)

    def __post_init__(self) -> None:
        fmt = FORMAT_ALIASES.get(self.format.upper(), self.format.upper())
        if fmt not in FORMATS:
            fmt = "A4"
        self.format = fmt
        self.orientation = "landscape" if self.orientation.lower().startswith("l") else "portrait"
        self.stamp = "vertical" if str(self.stamp).lower().startswith("v") else "horizontal"

    @property
    def size(self) -> tuple[float, float]:
        w, h = FORMATS[self.format]
        return (h, w) if self.orientation == "landscape" else (w, h)

    @property
    def width(self) -> float:
        return float(self.size[0])

    @property
    def height(self) -> float:
        return float(self.size[1])

    @property
    def frame(self) -> tuple[float, float, float, float]:
        """Внутренняя рамка: x0, y0, x1, y1."""
        return (MARGIN_LEFT, MARGIN_OTHER, self.width - MARGIN_OTHER, self.height - MARGIN_OTHER)

    @property
    def title_block(self) -> tuple[float, float, float, float]:
        """Габарит штампа на листе (для расчёта свободного поля)."""
        x0, y0, x1, y1 = self.frame
        if self.stamp == "horizontal":
            return (x1 - TITLE_W, y0, x1, y0 + TITLE_H)
        return (x0, y0, x0 + TITLE_H, y0 + TITLE_W)

    @property
    def stamp_strip(self) -> float:
        """Ширина полосы, занятой вертикальным штампом."""
        return TITLE_H + 4 if self.stamp == "vertical" else 0.0

    # ------------------------------------------------------------------
    def draw(self, scene: Scene, *, title: dict[str, str], scale_text: str, doc_code: str = "") -> None:
        """Рамка + основная надпись."""
        x0, y0, x1, y1 = self.frame
        scene.add(Line(a=(x0, y0), b=(x1, y0), layer="FRAME", lw=0.6))
        scene.add(Line(a=(x1, y0), b=(x1, y1), layer="FRAME", lw=0.6))
        scene.add(Line(a=(x1, y1), b=(x0, y1), layer="FRAME", lw=0.6))
        scene.add(Line(a=(x0, y1), b=(x0, y0), layer="FRAME", lw=0.6))
        self._draw_stamp(scene, title, scale_text, doc_code)

    def _draw_stamp(self, scene: Scene, title: dict[str, str], scale_text: str, doc_code: str) -> None:
        # штамп рисуется в локальных координатах (0..185, 0..55), затем
        # ставится на лист: как есть (форма 1) или повёрнутым (форма 2)
        tmp = Scene()
        _draw_title_block(tmp, (0.0, 0.0, TITLE_W, TITLE_H), title, scale_text, doc_code)

        if self.stamp == "horizontal":
            x0, y0, _, _ = self.title_block
            for prim in tmp.prims:
                _translate_prim(prim, x0, y0)
                scene.add(prim)
            return

        x0, y0, _, _ = self.frame
        for prim in tmp.prims:
            rotated = _rotate_prim(prim, 90.0)
            _translate_prim(rotated, x0 + TITLE_H, y0)
            scene.add(rotated)

    def plan_area(self, *, legend_width: float = 0.0) -> tuple[float, float, float, float]:
        """Область для плана: рамка минус штамп и колонка легенды справа."""
        x0, y0, x1, y1 = self.frame
        left = x0 + self.stamp_strip
        plan_x1 = x1 - legend_width - 4 if legend_width else x1 - 4
        if self.stamp == "horizontal":
            _, _, _, ty1 = self.title_block
            plan_y0 = ty1 + 4 if plan_x1 > self.title_block[0] else y0 + 4
        else:
            plan_y0 = y0 + 4
        return (left + 4, plan_y0, plan_x1, y1 - 4)


# ----------------------------------------------------------------------
def _translate_prim(prim, dx: float, dy: float) -> None:
    if isinstance(prim, Line):
        prim.a = (prim.a[0] + dx, prim.a[1] + dy)
        prim.b = (prim.b[0] + dx, prim.b[1] + dy)
    elif isinstance(prim, Text):
        prim.at = (prim.at[0] + dx, prim.at[1] + dy)
    else:
        for attr in ("points", "boundary"):
            pts = getattr(prim, attr, None)
            if pts:
                setattr(prim, attr, [(p[0] + dx, p[1] + dy) for p in pts])
        if hasattr(prim, "c"):
            prim.c = (prim.c[0] + dx, prim.c[1] + dy)


def _rotate_prim(prim, angle: float):
    if isinstance(prim, Line):
        prim.a = rotate_point(prim.a, (0.0, 0.0), angle)
        prim.b = rotate_point(prim.b, (0.0, 0.0), angle)
    elif isinstance(prim, Text):
        prim.at = rotate_point(prim.at, (0.0, 0.0), angle)
        prim.rotation = (prim.rotation + angle) % 360
    else:
        for attr in ("points", "boundary"):
            pts = getattr(prim, attr, None)
            if pts:
                setattr(prim, attr, [rotate_point(p, (0.0, 0.0), angle) for p in pts])
        if hasattr(prim, "c"):
            prim.c = rotate_point(prim.c, (0.0, 0.0), angle)
    return prim


# ----------------------------------------------------------------------
def _draw_title_block(
    scene: Scene,
    rect: tuple[float, float, float, float],
    title: dict[str, str],
    scale_text: str,
    doc_code: str = "",
) -> None:
    x0, y0, x1, y1 = rect
    W = x1 - x0

    def line(a, b, lw=0.35):
        scene.add(Line(a=a, b=b, layer="TITLE", lw=lw))

    def text(value, x, y, h=2.2, align="left", bold=False):
        if not value:
            return
        scene.add(Text(text=value, at=(x, y), height=h, layer="TITLE", align=align, bold=bold))

    # внешний контур
    line((x0, y0), (x1, y0), 0.6)
    line((x1, y0), (x1, y1), 0.6)
    line((x1, y1), (x0, y1), 0.6)
    line((x0, y1), (x0, y0), 0.6)

    # левая часть — таблица изменений
    col_w = [8, 12, 22, 13, 10]
    cx = x0
    for w in col_w[:-1]:
        cx += w
        line((cx, y0), (cx, y1), 0.25)
    row_h = (y1 - y0) / 5
    headers = ["Изм.", "Лист", "№ докум.", "Подп.", "Дата"]
    cx = x0
    for w, htext in zip(col_w, headers):
        text(htext, cx + w / 2, y1 - 3.2, 1.9, align="center")
        cx += w
    for i in range(1, 5):
        y = y0 + row_h * i
        line((x0, y), (x0 + sum(col_w), y), 0.25)
    line((x0 + sum(col_w), y0), (x0 + sum(col_w), y1), 0.6)

    # правая часть снизу вверх: организация → стадия/лист/масштаб →
    # наименование объекта → подписи
    rx0 = x0 + sum(col_w)
    rx1 = x1
    rw = rx1 - rx0

    y_org = y0 + 9
    line((rx0, y_org), (rx1, y_org), 0.25)
    text("Организация", rx0 + 1.5, y0 + 6.0, 1.6)
    text(title.get("organization", ""), rx0 + rw / 2, y0 + 1.7, 2.2, align="center")

    y_stage = y0 + 19
    line((rx0, y_stage), (rx1, y_stage), 0.25)
    seg = [("Стадия", 28), ("Лист", 22), ("Листов", 25), ("Масштаб", 45)]
    cx = rx0
    for i, (label, w) in enumerate(seg):
        if i:
            line((cx, y_org), (cx, y_stage), 0.25)
        text(label, cx + 1.5, y_stage - 3.0, 1.6)
        val = {
            "Стадия": title.get("stage", ""),
            "Лист": title.get("sheet", ""),
            "Листов": title.get("total", ""),
            "Масштаб": scale_text,
        }[label]
        text(val, cx + w / 2, y_org + 1.9, 2.3, align="center")
        cx += w

    # наименование: название чертежа, проект, адрес — между стадией и подписями
    y_name = y0 + 36
    line((rx0, y_name), (rx1, y_name), 0.25)
    name = title.get("drawing_name", "")
    project = title.get("project", "")
    address = title.get("address", "")
    text(name, rx0 + rw / 2, y_name - 7.4, 3.2, align="center", bold=True)
    text(project, rx0 + rw / 2, y_name - 11.4, 2.1, align="center")
    if address:
        text(address, rx0 + rw / 2, y_name - 14.6, 1.9, align="center")

    # подписи — верхняя часть правого блока
    rows = [("Разраб.", title.get("developer", "")), ("Пров.", title.get("checker", ""))]
    hrow = (y1 - y_name) / len(rows)
    for i, (label, value) in enumerate(rows):
        top = y1 - i * hrow
        if i:
            line((rx0, top), (rx1, top), 0.25)
        text(label, rx0 + 1.5, top - hrow + 3.0, 1.7)
        text(value, rx0 + 16, top - hrow + 3.2, 2.0)
    line((rx0 + 14, y_name), (rx0 + 14, y1), 0.25)
    line((rx0, y_name), (rx1, y_name), 0.25)

    if doc_code:
        text(doc_code, x0 + 1.5, y0 + 1.2, 1.7)

