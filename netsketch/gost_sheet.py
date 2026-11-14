"""Лист по ГОСТ 2.104-2006 для исполнительных схем: A3-альбом и штамп 185×55.

Геометрия снята с эталона `examples/gas/1` (9 DWG → DXF, блок `shtamp_b28`
и фактические линии слоя `ГП_Таbлицы`), поэтому сетка и текстовые графы
совпадают с эталоном в пределах 0,2 мм:

    python tools/gost_verify.py        # сверка с эталоном и отчёт

Ключевые факты эталона:

* лист A3-альбом 420×297, внешний контур по краю, рамка 20/5;
* штамп 185×55 прижат к нижней линии рамки: `(20,5)` слева или `(230,5)` справа;
* стороны штампа, совпадающие с рамкой (низ и одна вертикаль), не рисуются —
  их даёт сама рамка; противоположная вертикаль и верх рисуются;
* печать — A4-портрет: весь A3 повёрнут на 90° по часовой и вписан (0,7071).

Модуль не рисует «отдельный A4»: A4 — это тот же лист после поворота,
поэтому DWG и PDF не расходятся (инвариант один источник геометрии).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .scene import Line, Scene, Text, text_width

# ---------------------------------------------------------------------------
# Лист
# ---------------------------------------------------------------------------

# ГОСТ 2.301: размеры в мм, портретная ориентация (ширина × высота).
FORMAT_SIZES: dict[str, tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A2": (420.0, 594.0),
}

FORMAT_ALIASES = {"А4": "A4", "А3": "A3", "А2": "A2"}

MARGIN_LEFT = 20.0
MARGIN_OTHER = 5.0

STAMP_W = 185.0
STAMP_H = 55.0

# Слои эталона (совместимость с исходными DWG).
LAYER_FRAME = "анп Рамка жирная"
LAYER_STAMP = "ГП_Таbлицы"
LAYER_PIPE = "Трубы"

# Высоты текста эталона, мм. Это высоты в DWG; на печати авторы ставили
# аннотативный масштаб ~1,4 (проверено по печатному PDF: объект 1,43 → 2,0;
# название 1,9 → 2,66; адрес 2,86 → 4,0). Печатаем как в эталоне.
STAMP_TEXT_SCALE = 1.4

H_LABEL = 2.50  # узкие графы: 10 мм ячейка, масштаб не применяется
H_VALUE = 3.50 * STAMP_TEXT_SCALE
H_CIPHER = 3.50 * STAMP_TEXT_SCALE
H_ADDRESS = 2.86 * STAMP_TEXT_SCALE
H_OBJECT = 1.43 * STAMP_TEXT_SCALE
H_DRAWING = 1.90 * 1.34  # строки названия идут через 2,55 мм — чуть меньше, чтобы не липли
H_ORG = 2.86 * STAMP_TEXT_SCALE
H_CITY = 3.50 * STAMP_TEXT_SCALE


@dataclass
class GostSheet:
    """Лист ГОСТ 2.104: формат, ориентация, угол штампа."""

    format: str = "A3"
    orientation: str = "landscape"
    stamp: str = "right"  # left | right | auto

    def __post_init__(self) -> None:
        fmt = FORMAT_ALIASES.get(self.format.upper(), self.format.upper())
        if fmt not in FORMAT_SIZES:
            fmt = "A3"
        self.format = fmt
        self.orientation = "landscape" if str(self.orientation).lower().startswith("l") else "portrait"
        corner = str(self.stamp).lower()
        self.stamp = corner if corner in {"left", "right", "auto"} else "right"

    @property
    def size(self) -> tuple[float, float]:
        w, h = FORMAT_SIZES[self.format]
        return (h, w) if self.orientation == "landscape" else (w, h)

    @property
    def width(self) -> float:
        return float(self.size[0])

    @property
    def height(self) -> float:
        return float(self.size[1])

    @property
    def frame(self) -> tuple[float, float, float, float]:
        """Внутренняя рамка (x0, y0, x1, y1)."""
        return (MARGIN_LEFT, MARGIN_OTHER, self.width - MARGIN_OTHER, self.height - MARGIN_OTHER)

    def stamp_rect(self) -> tuple[float, float, float, float]:
        """Габарит штампа на листе. `auto` на этом уровне = правый угол."""
        x0, y0, x1, _ = self.frame
        if self.stamp == "left":
            return (x0, y0, x0 + STAMP_W, y0 + STAMP_H)
        return (x1 - STAMP_W, y0, x1, y0 + STAMP_H)

    @property
    def is_landscape(self) -> bool:
        return self.width > self.height


# ---------------------------------------------------------------------------
# Поля штампа
# ---------------------------------------------------------------------------

@dataclass
class StampFields:
    cipher: str = ""
    address: str = ""
    object_lines: list[str] = field(default_factory=list)
    stage: str = "ИД"
    sheet: str = "1"
    total: str = "1"
    organization: list[str] = field(default_factory=list)
    drawing: list[str] = field(default_factory=list)
    # (подпись, фамилия, дата) для строк «Разработал / Проверил / ГИП / Н. контроль»
    signatures: list[tuple[str, str, str]] = field(
        default_factory=lambda: [("Разработал", "", ""), ("Проверил", "", ""), ("ГИП", "", ""), ("Н. контроль", "", "")]
    )

    @classmethod
    def from_title(cls, title: dict | None) -> "StampFields":
        """Поля из `model.title` / словаря title (обратная совместимость)."""
        t = dict(title or {})

        def as_list(value, limit: int) -> list[str]:
            if not value:
                return []
            if isinstance(value, str):
                return [value.strip()] if value.strip() else []
            return [str(v).strip() for v in value if str(v).strip()][:limit]

        signatures = []
        for label, key in (
            ("Разработал", "developer"),
            ("Проверил", "checker"),
            ("ГИП", "gip"),
            ("Н. контроль", "ncontrol"),
        ):
            signatures.append((label, str(t.get(key) or ""), str(t.get("date") or "") if key == "developer" else ""))

        object_lines = as_list(t.get("object"), 3) or as_list(t.get("object_lines"), 3)
        if not object_lines:
            object_lines = [v for v in (str(t.get("project") or ""), str(t.get("address") or "")) if v][:3]

        organization = [org for org in (str(t.get("organization") or "").strip(),) if org]
        city = str(t.get("city") or "").strip()
        if city:
            organization.append(city)
        if not organization:
            organization = as_list(t.get("organization"), 2)

        drawing = as_list(t.get("drawing"), 3) or as_list(t.get("drawing_name"), 3)

        return cls(
            cipher=str(t.get("cipher") or t.get("doc_code") or ""),
            address=str(t.get("address") or ""),
            object_lines=object_lines,
            stage=str(t.get("stage") or "ИД"),
            sheet=str(t.get("sheet") or "1"),
            total=str(t.get("total") or "1"),
            organization=organization,
            drawing=drawing,
            signatures=signatures,
        )


# ---------------------------------------------------------------------------
# Сетка штампа (снята с эталона, локальные координаты 0..185 × 0..55)
# ---------------------------------------------------------------------------

# (x, y0, y1)
STAMP_VERTICALS: tuple[tuple[float, float, float], ...] = (
    (10.0, 30.0, 55.0),
    (20.0, 0.0, 55.0),
    (30.0, 30.0, 55.0),
    (40.0, 0.0, 55.0),
    (55.0, 0.0, 55.0),
    (65.0, 0.0, 55.0),
    (135.0, 0.0, 30.0),
    (150.0, 15.0, 30.0),
    (165.0, 15.0, 30.0),
)

# (x0, x1, y)
STAMP_HORIZONTALS: tuple[tuple[float, float, float], ...] = (
    (0.0, 65.0, 5.0),
    (0.0, 65.0, 10.0),
    (0.0, 65.0, 15.0),
    (0.0, 65.0, 20.0),
    (0.0, 65.0, 25.0),
    (0.0, 65.0, 35.0),
    (0.0, 65.0, 40.0),
    (0.0, 65.0, 50.0),
    (65.0, 185.0, 15.0),
    (135.0, 185.0, 25.0),
    (0.0, 185.0, 30.0),
    # в эталоне линия y=45 нарисована двумя отрезками со стыком по x=65
    (0.0, 65.0, 45.0),
    (65.0, 185.0, 45.0),
    (0.0, 185.0, 55.0),
)

# Шапка таблицы изменений и подписи: (текст, x, y, высота, выравнивание)
STAMP_LABELS: tuple[tuple[str, float, float, float, str], ...] = (
    ("Изм.", 2.15, 31.32, H_LABEL, "left"),
    ("Кол.уч.", 10.66, 31.35, H_LABEL, "left"),
    ("Лист", 21.63, 31.32, H_LABEL, "left"),
    ("№ док.", 30.76, 31.32, H_LABEL, "left"),
    ("Подп.", 44.19, 31.32, H_LABEL, "left"),
    ("Дата", 56.77, 31.37, H_LABEL, "left"),
    ("Стадия", 137.15, 26.32, H_LABEL, "left"),
    ("Лист", 153.53, 26.32, H_LABEL, "left"),
    ("Листов", 170.20, 26.39, H_LABEL, "left"),
)

# Строки подписей: базовая линия для подписи, фамилии и даты.
# В эталоне заняты 1-я, 2-я, 3-я и 5-я строки; 4-я остаётся пустой.
STAMP_SIGNATURE_ROWS: tuple[float, ...] = (26.32, 21.32, 16.32, 6.32)
LABEL_X = 1.05
VALUE_X = 21.05
DATE_X = 56.05


def _fit(text: str, height: float, max_width: float, minimum: float = 1.1) -> float:
    """Уменьшает кегль, если строка шире графы (как в эталоне: не выходить за поля)."""
    if not text:
        return height
    width = text_width(text, height)
    if width <= max_width or width <= 0:
        return height
    return max(minimum, height * max_width / width)


def _wrap_lines(lines: list[str], height: float, max_width: float, limit: int) -> list[str]:
    """Разбивает длинные строки по графе, сохраняя исходные переводы строк."""
    out: list[str] = []
    for line in lines:
        if text_width(line, height) <= max_width:
            out.append(line)
            continue
        words = line.split()
        current = ""
        for word in words:
            probe = f"{current} {word}".strip()
            if current and text_width(probe, height) > max_width:
                out.append(current)
                current = word
            else:
                current = probe
        if current:
            out.append(current)
    if len(out) > limit:
        out = out[: limit - 1] + [" ".join(out[limit - 1 :])]
    return out


# ---------------------------------------------------------------------------
# Рисование
# ---------------------------------------------------------------------------

def draw_sheet(scene: Scene, sheet: GostSheet, fields: StampFields, *, outer: bool = True) -> None:
    """Рамка листа + основная надпись. Геометрия — в мм листа."""
    w, h = sheet.width, sheet.height
    if outer:
        # у эталона внешний контур листа толще внутренней рамки (0,72 / 0,42)
        scene.add(Line(a=(0.0, 0.0), b=(w, 0.0), layer=LAYER_FRAME, lw=0.7))
        scene.add(Line(a=(w, 0.0), b=(w, h), layer=LAYER_FRAME, lw=0.7))
        scene.add(Line(a=(w, h), b=(0.0, h), layer=LAYER_FRAME, lw=0.7))
        scene.add(Line(a=(0.0, h), b=(0.0, 0.0), layer=LAYER_FRAME, lw=0.7))

    x0, y0, x1, y1 = sheet.frame
    scene.add(Line(a=(x0, y0), b=(x1, y0), layer=LAYER_FRAME, lw=0.42))
    scene.add(Line(a=(x1, y0), b=(x1, y1), layer=LAYER_FRAME, lw=0.42))
    scene.add(Line(a=(x1, y1), b=(x0, y1), layer=LAYER_FRAME, lw=0.42))
    scene.add(Line(a=(x0, y1), b=(x0, y0), layer=LAYER_FRAME, lw=0.42))

    draw_stamp(scene, sheet, fields)


def draw_stamp(scene: Scene, sheet: GostSheet, fields: StampFields) -> None:
    """Основная надпись 185×55 в выбранном углу рамки."""
    ox, oy, _, _ = sheet.stamp_rect()
    corner = "left" if sheet.stamp == "left" else "right"

    def L(a, b, lw=0.19):
        scene.add(Line(a=(ox + a[0], oy + a[1]), b=(ox + b[0], oy + b[1]), layer=LAYER_STAMP, lw=lw))

    def T(value: str, x: float, y: float, height: float, align: str = "center", valign: str = "middle") -> None:
        """Текст графы. По умолчанию — по центру ячейки и по горизонтали, и по вертикали."""
        if not value:
            return
        scene.add(
            Text(text=value, at=(ox + x, oy + y), height=height, layer=LAYER_STAMP, align=align, valign=valign)
        )

    def T_block(lines: list[str], x0: float, x1: float, y0: float, y1: float, height: float, step: float) -> None:
        """Многострочный блок: строки по центру колонки, блок — по центру своей области."""
        lines = [line for line in lines if line.strip()]
        if not lines:
            return
        cx = (x0 + x1) / 2
        total = (len(lines) - 1) * step
        cy = (y0 + y1) / 2 + total / 2
        for i, line in enumerate(lines):
            T(line, cx, cy - i * step, height)

    # --- сетка ---
    for x, ya, yb in STAMP_VERTICALS:
        L((x, ya), (x, yb), 0.18)
    for xa, xb, y in STAMP_HORIZONTALS:
        lw = 0.7 if y == 55.0 else 0.18
        L((xa, y), (xb, y), lw)

    # Контур: верх и «свободная» вертикаль. Низ и вторая вертикаль совпадают
    # с рамкой листа — их не дублируем (так в эталоне).
    L((0.0, 55.0), (185.0, 55.0), 0.7)
    if corner == "left":
        L((185.0, 0.0), (185.0, 55.0), 0.7)
    else:
        L((0.0, 0.0), (0.0, 55.0), 0.7)

    # --- шапка: подписи граф по центрам ячеек (строка 30…35) ---
    header_y = 32.5
    for text, cx in (("Изм.", 5.0), ("Кол.уч.", 15.0), ("Лист", 25.0), ("№ док.", 35.0), ("Подп.", 47.5), ("Дата", 60.0)):
        T(text, cx, header_y, H_LABEL)

    # --- стадия / лист / листов: шапки в строке 25…30, значения в 15…25 ---
    for text, cx in (("Стадия", 142.5), ("Лист", 157.5), ("Листов", 175.0)):
        T(text, cx, 27.5, H_LABEL)
    T(fields.stage, 142.5, 20.0, H_VALUE)
    T(fields.sheet, 157.5, 20.0, H_VALUE)
    T(fields.total, 175.0, 20.0, H_VALUE)

    # --- подписи (Разработал / Проверил / ГИП / Н. контроль) ---
    sig_centers = (27.5, 22.5, 17.5, 7.5)
    for i, (label, name, date) in enumerate(fields.signatures[: len(sig_centers)]):
        cy = sig_centers[i]
        T(label, 1.05, cy, H_LABEL, align="left")  # роли — по левому краю колонки
        T(name, 30.0, cy, H_LABEL)  # ячейка 20…40
        if i == 0:
            T(date, 60.0, cy, H_LABEL)

    # --- шифр ---
    cipher = fields.cipher.strip()
    if cipher:
        T(cipher, 125.0, 50.0, _fit(cipher, H_CIPHER, 110.0))

    # --- адрес: 1–3 строки по центру ячейки 30…45 ---
    address = fields.address.strip()
    if address:
        T_block(_wrap_lines([address], H_ADDRESS, 112.0, 3), 65.0, 185.0, 30.0, 45.0, H_ADDRESS, 4.0)

    # --- объект: до 3 строк в ячейке 25…30 слева от стадии ---
    T_block(_wrap_lines(list(fields.object_lines), H_OBJECT, 66.0, 3), 65.0, 135.0, 20.0, 30.0, H_OBJECT, 2.2)

    # --- название чертежа: до 3 строк в ячейке 0…15 ---
    T_block(_wrap_lines(list(fields.drawing), H_DRAWING, 66.0, 3), 65.0, 135.0, 0.0, 15.0, H_DRAWING, 2.7)

    # --- организация и город: две строки справа-снизу ---
    org = [v for v in fields.organization if v][:2]
    if org:
        T(org[0], 160.0, 10.5, _fit(org[0], H_ORG, 48.0))
    if len(org) > 1:
        T(org[1], 160.0, 4.0, _fit(org[1], H_CITY, 48.0))


def build_sheet(sheet: GostSheet, fields: StampFields, *, outer: bool = True) -> Scene:
    """Только рамка и штамп — для проверки шаблона и наложения на эталон."""
    scene = Scene()
    draw_sheet(scene, sheet, fields, outer=outer)
    return scene


# ---------------------------------------------------------------------------
# Печать: A3-альбом → A4-портрет (поворот 90° по часовой, вписать)
# ---------------------------------------------------------------------------

A4_WIDTH = 210.0
A4_HEIGHT = 297.0


def print_transform(sheet: GostSheet) -> tuple[float, float, float, Callable[[tuple[float, float]], tuple[float, float]]]:
    """Преобразование мм листа → мм страницы печати.

    Возвращает (ширина страницы, высота страницы, масштаб, функция).
    Для A3-альбома: s = 210/297 ≈ 0,7071, страница 210×297.
    """
    w, h = sheet.width, sheet.height
    scale = min(A4_WIDTH / h, A4_HEIGHT / w)

    def transform(p: tuple[float, float]) -> tuple[float, float]:
        x, y = p
        return (y * scale, (w - x) * scale)

    return (A4_WIDTH, A4_HEIGHT, scale, transform)
