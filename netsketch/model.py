"""Семантическая модель эскиза и её валидация.

Модель — единственный контракт между «пониманием» картинки и черчением.
Её заполняет либо модель зрения (LLM), либо человек/агент вручную.
Координаты задаются в пикселях исходного изображения (ось Y вниз),
перевод в миллиметры листа делает раскладка (netsketch/layout.py).

Три категории достоверности (как в ТЗ):
  CONFIRMED — прочитано с эскиза однозначно;
  DERIVED   — получено расчётом/из пары «эскиз ↔ готовый DWG»;
  ASSUMED   — домыслено, выносится на отдельный слой и в примечания.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

SCHEMA_VERSION = "1.0"

CONFIRMED = "CONFIRMED"
DERIVED = "DERIVED"
ASSUMED = "ASSUMED"
_STATES = {CONFIRMED, DERIVED, ASSUMED}


# Канонические типы элементов и их русские подписи.
ELEMENT_TYPES: dict[str, str] = {
    "valve": "Задвижка",
    "valve_ball": "Кран шаровой",
    "gate_valve": "Задвижка",
    "kgz": "КГЗ (клапан термозапорный)",
    "kem": "КЭМ (клапан электромагнитный)",
    "filter": "Фильтр",
    "flowmeter": "Расходомер",
    "compensator": "Компенсатор",
    "support": "Опора",
    "well": "Колодец",
    "gpsh": "ГРПШ",
    "sleeve": "Футляр",
    "hydrolock": "Гидрозатвор",
    "tee": "Тройник",
    "fork": "Вилка (разделение на две ветки)",
    "facade_link": "Фасадный газопровод (пунктир)",
    "cross": "Крестовина",
    "reducer": "Переход",
    "flange": "Фланец",
    "coupling": "Муфта",
    "insulation_end": "Концевая изоляция",
    "manometer": "Манометр",
    "regulator": "Регулятор давления",
    "meter": "Узел учёта",
    "inlet": "Ввод",
    "outlet": "Выпуск",
    "riser": "Стояк",
    "pit": "Ковер",
    "unknown": "Не распознано",
}

_ALIASES: dict[str, str] = {
    "задвижка": "valve",
    "кран": "valve_ball",
    "кран шаровой": "valve_ball",
    "шаровой кран": "valve_ball",
    "кгз": "kgz",
    "клапан термозапорный": "kgz",
    "ктз": "kgz",
    "кэм": "kem",
    "клапан электромагнитный": "kem",
    "фильтр": "filter",
    "расходомер": "flowmeter",
    "компенсатор": "compensator",
    "опора": "support",
    "неподвижная опора": "support",
    "колодец": "well",
    "кол.": "well",
    "грпш": "gpsh",
    "гру": "gpsh",
    "футляр": "sleeve",
    "гидрозатвор": "hydrolock",
    "тройник": "tee",
    "вилка": "fork",
    "развилка": "fork",
    "крестовина": "cross",
    "переход": "reducer",
    "фланец": "flange",
    "муфта": "coupling",
    "концевая изоляция": "insulation_end",
    "манометр": "manometer",
    "регулятор": "regulator",
    "узел учёта": "meter",
    "ввод": "inlet",
    "выпуск": "outlet",
    "стояк": "riser",
    "ковер": "pit",
}

SEGMENT_KINDS = {
    "main": "Магистраль",
    "branch": "Ответвление",
    "inlet": "Ввод",
    "outlet": "Выпуск",
    "crossing": "Переход (футляр)",
    "riser": "Стояк",
    "unknown": "Участок",
}


def normalize_element_type(value: str) -> str:
    key = (value or "").strip().lower()
    if key in ELEMENT_TYPES:
        return key
    if key in _ALIASES:
        return _ALIASES[key]
    # «задвижка Ø50» и подобное
    for alias, canonical in _ALIASES.items():
        if alias in key:
            return canonical
    for canonical, label in ELEMENT_TYPES.items():
        if label.lower() in key:
            return canonical
    return "unknown"


def _num(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return default
    try:
        return float(m.group(0))
    except ValueError:
        return default


def _point(value: Any) -> tuple[float, float] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        x, y = _num(value.get("x")), _num(value.get("y"))
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        x, y = _num(value[0]), _num(value[1])
    else:
        return None
    if x is None or y is None:
        return None
    return (x, y)


def _state(value: Any, default: str = CONFIRMED) -> str:
    s = str(value or "").strip().upper()
    return s if s in _STATES else default


@dataclass
class Node:
    id: str
    x: float
    y: float
    label: str = ""
    state: str = CONFIRMED

    @property
    def xy(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass
class Segment:
    id: str
    points: list[tuple[float, float]]
    diameter_mm: int | None = None
    kind: str = "main"
    material: str = ""
    length_mm: int | None = None
    pressure: str = ""
    state: str = CONFIRMED
    note: str = ""

    @property
    def length_px(self) -> float:
        total = 0.0
        for a, b in zip(self.points, self.points[1:]):
            total += math.dist(a, b)
        return total


@dataclass
class Element:
    id: str
    type: str
    x: float
    y: float
    node: str = ""
    diameter_mm: int | None = None
    label: str = ""
    rotation: float = 0.0
    size: float = 1.0
    state: str = CONFIRMED

    @property
    def xy(self) -> tuple[float, float]:
        return (self.x, self.y)

    @property
    def type_label(self) -> str:
        return ELEMENT_TYPES.get(self.type, self.type)


@dataclass
class Label:
    text: str
    x: float
    y: float
    role: str = "note"  # diameter | length | elevation | note | callout | title
    height: float = 2.5
    rotation: float = 0.0
    state: str = CONFIRMED


@dataclass
class Dimension:
    """Размерная цепь: ломаная + значения по звеньям (в мм)."""

    id: str
    points: list[tuple[float, float]]
    values_mm: list[int] = field(default_factory=list)
    offset_mm: float = 0.0
    state: str = CONFIRMED


@dataclass
class Callout:
    """Выноска на полке: текст, куда указывает и с какой стороны стоит.

    `targets` — одна или несколько точек: если их две (и больше), линия от
    полки раздваивается (например «Кран Ø15» на оба крана после вилки).
    """

    n: int | str = ""
    text: str = ""
    x: float | None = None  # где стоит полка (левый край текста)
    y: float | None = None
    tx: float | None = None  # первая точка привязки (совместимость)
    ty: float | None = None
    targets: list[tuple[float, float]] = field(default_factory=list)
    side: str = "left"  # left | right | up | down
    fixed: bool = False  # не двигать авто-разводкой (место задал автор)
    state: str = CONFIRMED


@dataclass
class Weld:
    """Номер сварного шва: штрих поперёк трубы + номер рядом."""

    id: str
    x: float
    y: float
    angle: float = 45.0  # направление самого штриха, градусы
    label_x: float | None = None  # где автор поставил номер (если задано)
    label_y: float | None = None
    state: str = CONFIRMED


@dataclass
class Support:
    """Опора (узел крепления к стене) — крестик поперёк трубы."""

    x: float
    y: float
    angle: float = 0.0  # направление трубы, чтобы крестик встал поперёк
    state: str = CONFIRMED


@dataclass
class Chain:
    """Размерная цепь: `СШ 1000`, `ОП 3000` или свободный размер."""

    kind: str = "plain"  # weld (СШ) | support (ОП) | plain
    points: list[tuple[float, float]] = field(default_factory=list)
    values_mm: list[int] = field(default_factory=list)
    offset_mm: float = 0.0
    side: str = "auto"
    state: str = CONFIRMED


@dataclass
class Room:
    """Крупная подпись помещения/подъезда: `КВ. 5`, `1 под.`."""

    text: str
    x: float
    y: float
    height: float = 3.8
    state: str = CONFIRMED


@dataclass
class LegendItem:
    symbol: str
    text: str


@dataclass
class SpecRow:
    diameter_mm: int | None = None
    length_m: float | None = None
    count: int | None = None
    note: str = ""
    name: str = ""


@dataclass
class TitleBlock:
    project: str = ""
    address: str = ""
    drawing_name: str = ""
    stage: str = "Р"
    sheet: str = "1"
    total: str = "1"
    scale: str = ""
    organization: str = ""
    developer: str = ""
    checker: str = ""
    approver: str = ""
    date: str = ""
    doc_code: str = ""
    # реквизиты ГОСТ-штампа исполнительной схемы (фаза 4)
    cipher: str = ""  # шифр: 09/11ПР-2026-ИОС6
    gip: str = ""
    ncontrol: str = ""
    city: str = ""
    object_lines: list[str] = field(default_factory=list)  # объект, 2–3 строки
    drawing: list[str] = field(default_factory=list)  # название чертежа, до 3 строк


@dataclass
class Model:
    network_type: str = "gas"
    mode: str = "plan"  # plan | schematic
    sheet: str = "A4"
    orientation: str = "portrait"
    title: TitleBlock = field(default_factory=TitleBlock)
    image_width: int = 0
    image_height: int = 0
    mm_per_px: float | None = None
    nodes: list[Node] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    dimensions: list[Dimension] = field(default_factory=list)
    callouts: list[Callout] = field(default_factory=list)
    welds: list[Weld] = field(default_factory=list)
    supports: list[Support] = field(default_factory=list)
    chains: list[Chain] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    legend: list[LegendItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    specification: list[SpecRow] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    def all_points(self) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        for s in self.segments:
            pts.extend(s.points)
        for n in self.nodes:
            pts.append(n.xy)
        for e in self.elements:
            pts.append(e.xy)
        for w in self.welds:
            pts.append((w.x, w.y))
        for s in self.supports:
            pts.append((s.x, s.y))
        for c in self.chains:
            pts.extend(c.points)
        for r in self.rooms:
            pts.append((r.x, r.y))
        for c in self.callouts:
            if c.x is not None and c.y is not None:
                pts.append((c.x, c.y))
            if c.tx is not None and c.ty is not None:
                pts.append((c.tx, c.ty))
        return pts

    def bbox(self) -> tuple[float, float, float, float] | None:
        pts = self.all_points()
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def used_element_types(self) -> list[str]:
        seen: list[str] = []
        for e in self.elements:
            if e.type not in seen:
                seen.append(e.type)
        return seen

    def node_map(self) -> dict[str, Node]:
        return {n.id: n for n in self.nodes}

    def total_length_m(self) -> float | None:
        vals = [r.length_m for r in self.specification if r.length_m]
        if vals:
            return float(sum(vals))
        vals2 = [s.length_mm for s in self.segments if s.length_mm]
        if vals2:
            return float(sum(vals2)) / 1000.0
        return None

    def is_two_pipe(self) -> bool:
        return bool(self.meta.get("two_pipe"))

    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        def pts(v: list[tuple[float, float]]) -> list[list[float]]:
            return [[round(p[0], 2), round(p[1], 2)] for p in v]

        return {
            "schema_version": SCHEMA_VERSION,
            "network_type": self.network_type,
            "mode": self.mode,
            "sheet": self.sheet,
            "orientation": self.orientation,
            "title": self.title.__dict__,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "mm_per_px": self.mm_per_px,
            "nodes": [n.__dict__ for n in self.nodes],
            "segments": [
                {
                    "id": s.id,
                    "points": pts(s.points),
                    "diameter_mm": s.diameter_mm,
                    "kind": s.kind,
                    "material": s.material,
                    "length_mm": s.length_mm,
                    "pressure": s.pressure,
                    "state": s.state,
                    "note": s.note,
                }
                for s in self.segments
            ],
            "elements": [e.__dict__ for e in self.elements],
            "labels": [l.__dict__ for l in self.labels],
            "dimensions": [
                {
                    "id": d.id,
                    "points": pts(d.points),
                    "values_mm": d.values_mm,
                    "offset_mm": d.offset_mm,
                    "state": d.state,
                }
                for d in self.dimensions
            ],
            "callouts": [c.__dict__ for c in self.callouts],
            "welds": [w.__dict__ for w in self.welds],
            "supports": [s.__dict__ for s in self.supports],
            "chains": [
                {
                    "kind": c.kind,
                    "points": pts(c.points),
                    "values_mm": c.values_mm,
                    "offset_mm": c.offset_mm,
                    "side": c.side,
                    "state": c.state,
                }
                for c in self.chains
            ],
            "rooms": [r.__dict__ for r in self.rooms],
            "summary": list(self.summary),
            "legend": [l.__dict__ for l in self.legend],
            "notes": self.notes,
            "specification": [r.__dict__ for r in self.specification],
            "assumptions": self.assumptions,
            "warnings": self.warnings,
            "meta": self.meta,
        }


def _iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def model_from_dict(data: dict[str, Any]) -> tuple[Model, list[str]]:
    """Терпимый разбор ответа модели зрения. Возвращает модель и предупреждения."""
    warnings: list[str] = []
    if not isinstance(data, dict):
        raise ValueError("model.json должен быть объектом")

    m = Model()
    m.network_type = str(data.get("network_type") or data.get("discipline") or "gas").lower()
    m.sheet = str(data.get("sheet") or data.get("format") or "A4").upper().replace("А", "A")
    m.orientation = str(data.get("orientation") or "portrait").lower()
    m.image_width = int(_num(data.get("image_width"), 0) or 0)
    m.image_height = int(_num(data.get("image_height"), 0) or 0)
    m.mm_per_px = _num(data.get("mm_per_px"))
    m.meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    m.meta = dict(m.meta)
    # `placement` может стоять и в корне — удобно для моделей, заданных
    # прямо в мм листа (эталон, ручная доводка)
    if data.get("placement") and "placement" not in m.meta:
        m.meta["placement"] = str(data["placement"])

    title_raw = data.get("title") if isinstance(data.get("title"), dict) else {}
    tb = TitleBlock()
    for key in tb.__dict__:
        if key not in title_raw or title_raw[key] is None:
            continue
        value = title_raw[key]
        if isinstance(getattr(tb, key), list):
            if isinstance(value, str):
                value = [line for line in value.split("\n") if line.strip()]
            else:
                value = [str(v) for v in value if str(v).strip()]
        else:
            value = str(value)
        setattr(tb, key, value)
    m.title = tb

    seen_nodes: dict[str, Node] = {}
    for raw in _iter_dicts(data.get("nodes")):
        p = _point(raw)
        if not p:
            continue
        nid = str(raw.get("id") or f"n{len(seen_nodes) + 1}")
        if nid in seen_nodes:
            warnings.append(f"узел {nid} повторяется — оставлен первый")
            continue
        node = Node(id=nid, x=p[0], y=p[1], label=str(raw.get("label") or ""), state=_state(raw.get("state")))
        seen_nodes[nid] = node
    m.nodes = list(seen_nodes.values())

    for i, raw in enumerate(_iter_dicts(data.get("segments"))):
        pts: list[tuple[float, float]] = []
        raw_points = raw.get("points")
        if isinstance(raw_points, list) and raw_points:
            for item in raw_points:
                p = _point(item)
                if p:
                    pts.append(p)
        if not pts:
            a = seen_nodes.get(str(raw.get("from") or ""))
            b = seen_nodes.get(str(raw.get("to") or ""))
            if a and b:
                pts = [a.xy, b.xy]
        if len(pts) < 2:
            # одиночная точка — вырожденный участок, пропускаем
            warnings.append(f"участок {raw.get('id') or i + 1}: меньше двух точек, пропущен")
            continue
        seg = Segment(
            id=str(raw.get("id") or f"s{i + 1}"),
            points=pts,
            diameter_mm=int(_num(raw.get("diameter_mm") or raw.get("diameter"), 0) or 0) or None,
            kind=str(raw.get("kind") or "main").lower(),
            material=str(raw.get("material") or ""),
            length_mm=int(_num(raw.get("length_mm"), 0) or 0) or None,
            pressure=str(raw.get("pressure") or ""),
            state=_state(raw.get("state")),
            note=str(raw.get("note") or ""),
        )
        if seg.kind not in SEGMENT_KINDS:
            seg.kind = "main" if seg.kind == "unknown" else seg.kind
        m.segments.append(seg)

    for i, raw in enumerate(_iter_dicts(data.get("elements"))):
        etype = normalize_element_type(str(raw.get("type") or ""))
        p = _point(raw)
        if not p:
            node = seen_nodes.get(str(raw.get("node") or ""))
            if node:
                p = node.xy
        if not p:
            warnings.append(f"элемент {raw.get('id') or i + 1} без координат, пропущен")
            continue
        if etype == "unknown":
            warnings.append(f"неизвестный тип элемента «{raw.get('type')}»")
        m.elements.append(
            Element(
                id=str(raw.get("id") or f"e{i + 1}"),
                type=etype,
                x=p[0],
                y=p[1],
                node=str(raw.get("node") or ""),
                diameter_mm=int(_num(raw.get("diameter_mm") or raw.get("diameter"), 0) or 0) or None,
                label=str(raw.get("label") or ""),
                rotation=float(_num(raw.get("rotation"), 0) or 0),
                size=float(_num(raw.get("size"), 1) or 1),
                state=_state(raw.get("state")),
            )
        )

    for raw in _iter_dicts(data.get("labels")):
        p = _point(raw)
        text = str(raw.get("text") or "").strip()
        if not p or not text:
            continue
        m.labels.append(
            Label(
                text=text,
                x=p[0],
                y=p[1],
                role=str(raw.get("role") or "note").lower(),
                height=float(_num(raw.get("height"), 2.5) or 2.5),
                rotation=float(_num(raw.get("rotation"), 0) or 0),
                state=_state(raw.get("state")),
            )
        )

    for i, raw in enumerate(_iter_dicts(data.get("dimensions"))):
        pts = [p for p in (_point(v) for v in raw.get("points") or []) if p]
        if len(pts) < 2:
            continue
        values = [int(_num(v, 0) or 0) for v in raw.get("values_mm") or []]
        m.dimensions.append(
            Dimension(
                id=str(raw.get("id") or f"d{i + 1}"),
                points=pts,
                values_mm=values,
                offset_mm=float(_num(raw.get("offset_mm"), 0) or 0),
                state=_state(raw.get("state")),
            )
        )

    for raw in _iter_dicts(data.get("callouts")):
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        targets = [p for p in (_point(v) for v in raw.get("targets") or []) if p]
        target = _point(raw.get("target")) or _point({"x": raw.get("tx"), "y": raw.get("ty")})
        if target:
            targets.insert(0, target)
        pos = _point(raw)
        n = raw.get("n")
        m.callouts.append(
            Callout(
                n="" if n is None else n,
                text=text,
                x=pos[0] if pos else None,
                y=pos[1] if pos else None,
                tx=targets[0][0] if targets else None,
                ty=targets[0][1] if targets else None,
                targets=targets,
                side=str(raw.get("side") or "left").lower(),
                fixed=bool(raw.get("fixed")),
                state=_state(raw.get("state")),
            )
        )

    for raw in _iter_dicts(data.get("welds")):
        p = _point(raw)
        wid = str(raw.get("id") or raw.get("n") or raw.get("number") or "").strip()
        if not p or not wid:
            continue
        label = _point(raw.get("label"))
        m.welds.append(
            Weld(
                id=wid,
                x=p[0],
                y=p[1],
                angle=float(_num(raw.get("angle"), 45) or 45),
                label_x=label[0] if label else _num(raw.get("label_x")),
                label_y=label[1] if label else _num(raw.get("label_y")),
                state=_state(raw.get("state")),
            )
        )

    for raw in _iter_dicts(data.get("supports")):
        p = _point(raw)
        if not p:
            continue
        m.supports.append(
            Support(
                x=p[0],
                y=p[1],
                angle=float(_num(raw.get("angle") or raw.get("rotation"), 0) or 0),
                state=_state(raw.get("state")),
            )
        )

    for raw in _iter_dicts(data.get("chains")):
        pts = [p for p in (_point(v) for v in raw.get("points") or []) if p]
        if len(pts) < 2:
            continue
        kind = str(raw.get("kind") or raw.get("prefix") or "plain").lower()
        if kind in {"сш", "weld", "svarka", "шов"}:
            kind = "weld"
        elif kind in {"оп", "support", "opora", "опора"}:
            kind = "support"
        m.chains.append(
            Chain(
                kind=kind,
                points=pts,
                values_mm=[int(_num(v, 0) or 0) for v in raw.get("values_mm") or raw.get("values") or []],
                offset_mm=float(_num(raw.get("offset_mm"), 0) or 0),
                side=str(raw.get("side") or "auto").lower(),
                state=_state(raw.get("state")),
            )
        )

    for raw in _iter_dicts(data.get("rooms")):
        p = _point(raw)
        text = str(raw.get("text") or "").strip()
        if not p or not text:
            continue
        m.rooms.append(
            Room(
                text=text,
                x=p[0],
                y=p[1],
                height=float(_num(raw.get("height"), 3.8) or 3.8),
                state=_state(raw.get("state")),
            )
        )

    # пустые строки сохраняем: в эталонном итоговом блоке они разделяют группы
    raw_summary = data.get("summary") or []
    if isinstance(raw_summary, str):
        raw_summary = raw_summary.split("\n")
    m.summary = [str(v).strip() for v in raw_summary if v is not None]
    mode = str(data.get("mode") or "plan").lower()
    m.mode = "schematic" if mode.startswith("schem") else "plan"

    for raw in _iter_dicts(data.get("legend")):
        sym_raw = str(raw.get("symbol") or raw.get("type") or "").strip()
        text = str(raw.get("text") or raw.get("label") or "").strip()
        if not text:
            continue
        sym = normalize_element_type(sym_raw)
        if sym == "unknown" and sym_raw:
            # литеральный маркер эталонной легенды: «30», «×», «□»
            sym = sym_raw
        m.legend.append(LegendItem(symbol=sym, text=text))

    m.notes = [str(n).strip() for n in (data.get("notes") or []) if str(n).strip()]
    m.assumptions = [str(n).strip() for n in (data.get("assumptions") or []) if str(n).strip()]

    for raw in _iter_dicts(data.get("specification")):
        m.specification.append(
            SpecRow(
                diameter_mm=int(_num(raw.get("diameter_mm") or raw.get("diameter"), 0) or 0) or None,
                length_m=_num(raw.get("length_m") or raw.get("length")),
                count=int(_num(raw.get("count"), 0) or 0) or None,
                note=str(raw.get("note") or ""),
                name=str(raw.get("name") or ""),
            )
        )

    if not m.segments and not m.elements:
        warnings.append("в модели нет ни одного участка или элемента")

    return m, warnings


def model_to_json(model: Model) -> str:
    return json.dumps(model.to_dict(), ensure_ascii=False, indent=2)


def load_model_file(path: str) -> tuple[Model, list[str]]:
    with open(path, "r", encoding="utf-8-sig") as fh:
        return model_from_dict(json.load(fh))


# ----------------------------------------------------------------------
# Проверки распознанной модели (фаза 5): то, что чаще всего теряется
# на рукописном эскизе.
# ----------------------------------------------------------------------

_WELD_ID = re.compile(r"^\d+(\.\d+)?$")
_SUMMARY_ROW = re.compile(r"ст\.?\s*д\.?\s*(\d+)\s*l\s*=\s*([\d.,]+)\s*м", re.IGNORECASE)
_SUMMARY_TOTAL = re.compile(r"(?:итого|всего|lобщ)[^\d\-]*([\d.,]+)\s*м", re.IGNORECASE)


def _as_float(value: str) -> float | None:
    try:
        return float(value.replace(",", "."))
    except (AttributeError, ValueError):
        return None


def normalize_recognized(data: dict) -> dict:
    """Починить типовые огрехи модели зрения до разбора в Model."""
    out = dict(data)
    out.setdefault("schema_version", SCHEMA_VERSION)

    welds = []
    for raw in out.get("welds") or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        wid = str(item.get("id") or item.get("number") or item.get("n") or "").strip()
        # «2,1» из русского текста, «2 . 1», лишние пробелы
        wid = wid.replace(",", ".").replace(" ", "").replace("–", "-")
        if wid:
            item["id"] = wid
        welds.append(item)
    if welds:
        out["welds"] = welds

    chains = []
    for raw in out.get("chains") or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        kind = str(item.get("kind") or item.get("prefix") or "").strip().lower()
        # «СП»/«сш» — сварные швы, «0П»/«on» — опоры
        if kind.replace("0", "о") in {"сш", "сп", "шов", "сварной"}:
            item["kind"] = "weld"
        elif kind.replace("0", "о") in {"оп", "опора", "on"}:
            item["kind"] = "support"
        chains.append(item)
    if chains:
        out["chains"] = chains

    if not out.get("mode"):
        out["mode"] = "schematic" if (out.get("welds") or out.get("supports") or out.get("summary")) else "plan"
    return out


def validate_model(model: Model) -> list[str]:
    """Проверки модели перед черчением. Возвращает предупреждения.

    Ловит типовые ошибки распознавания: потерянный суффикс шва, `Ø` вместо
    `0`, `СП`/`0П` вместо `СШ`/`ОП`, выноску без привязки и несходящийся
    итог длин.
    """
    warnings: list[str] = []

    ids = [w.id for w in model.welds]
    seen: set[str] = set()
    for wid in ids:
        if wid in seen:
            warnings.append(f"номер шва {wid} повторяется")
        seen.add(wid)
        if not _WELD_ID.match(wid):
            warnings.append(f"номер шва «{wid}» не похож на номер (ожидается 30 или 2.1)")

    for c in model.chains:
        if not isinstance(c, Chain):
            continue
        if c.kind in {"weld", "support"} and not c.values_mm:
            warnings.append(f"цепь {c.kind}: нет значений в мм")
        for value in c.values_mm:
            if value and not (50 <= value <= 200000):
                warnings.append(f"цепь {c.kind}: подозрительное значение {value} мм")

    for co in model.callouts:
        text = (co.text or "").strip()
        if not text:
            warnings.append("пустая выноска")
            continue
        if re.search(r"(^|[^\w])0[ПPп]\b|(^|[^\w])СП\b", text):
            warnings.append(f"выноска «{text}»: похоже на 0П/СП вместо ОП/СШ")
        if re.fullmatch(r"[0OОoо]\s?\d{1,3}", text):
            warnings.append(f"выноска «{text}»: похоже на Ø, прочитанный как 0/О")
        if co.tx is None and co.x is None:
            warnings.append(f"выноска «{text}» без привязки (target)")

    if model.summary:
        rows = [v for line in model.summary for v in _SUMMARY_ROW.findall(line)]
        total_match = None
        for line in model.summary:
            m = _SUMMARY_TOTAL.search(line)
            if m:
                total_match = _as_float(m.group(1))
        if rows and total_match is not None:
            s = sum(_as_float(v[1]) or 0.0 for v in rows)
            if abs(s - total_match) > 0.15:
                warnings.append(f"итог {total_match:g} м не сходится с суммой участков {s:.2f} м")

    if model.mode == "schematic":
        if not model.title.cipher:
            warnings.append("не заполнен шифр в штампе (title.cipher)")
        if not model.title.drawing:
            warnings.append("не заполнено название чертежа (title.drawing)")
        if model.welds and not model.legend:
            warnings.append("есть швы, но нет легенды (номер шва / опора / футляр)")

    return warnings

