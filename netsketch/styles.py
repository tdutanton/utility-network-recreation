"""Слои, типы линий, текстовые и размерные стили для DWG."""

from __future__ import annotations

from dataclasses import dataclass

# Стандартные значения толщин линий DXF (1/100 мм).
LW_VALUES = [0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200]


def snap_lw(mm: float) -> int:
    target = mm * 100.0
    best = min(LW_VALUES, key=lambda v: abs(v - target))
    return best


@dataclass(frozen=True)
class LayerSpec:
    name: str
    color: int
    linetype: str = "CONTINUOUS"
    lw: float = 0.25
    description: str = ""
    printable: bool = True


BASE_LAYERS = [
    LayerSpec("FRAME", 7, "CONTINUOUS", 0.6, "Рамка и основная надпись"),
    LayerSpec("TITLE", 7, "CONTINUOUS", 0.35, "Основная надпись"),
    LayerSpec("TEXT", 7, "CONTINUOUS", 0.18, "Тексты, примечания"),
    LayerSpec("DIM", 7, "CONTINUOUS", 0.18, "Размеры"),
    LayerSpec("LEGEND", 7, "CONTINUOUS", 0.18, "Условные обозначения"),
    LayerSpec("TABLE", 7, "CONTINUOUS", 0.25, "Таблицы и ведомости"),
    LayerSpec("AXIS", 8, "CENTER", 0.18, "Осевые линии"),
    LayerSpec("ASSUMED", 6, "DASHED", 0.18, "Домысленные данные (ASSUMED)"),
    LayerSpec("HIDDEN", 8, "DASHED", 0.18, "Скрытые/подземные участки"),
]

NETWORK_LAYERS: dict[str, list[LayerSpec]] = {
    "gas": [
        LayerSpec("GAS_MAIN", 7, "CONTINUOUS", 0.5, "Газопровод — магистраль"),
        LayerSpec("GAS_BRANCH", 7, "CONTINUOUS", 0.35, "Газопровод — ответвление"),
        LayerSpec("GAS_INLET", 7, "DASHED", 0.35, "Ввод газопровода"),
        LayerSpec("GAS_SLEEVE", 8, "DASHED", 0.25, "Футляр"),
        LayerSpec("GAS_EQUIP", 7, "CONTINUOUS", 0.25, "Арматура и оборудование"),
        LayerSpec("GAS_WELL", 7, "CONTINUOUS", 0.35, "Колодцы, коверы"),
        LayerSpec("GAS_LABEL", 7, "CONTINUOUS", 0.18, "Подписи диаметров"),
    ],
    "heat": [
        LayerSpec("HEAT_SUPPLY", 1, "CONTINUOUS", 0.5, "Теплосеть — подающий"),
        LayerSpec("HEAT_RETURN", 5, "CONTINUOUS", 0.5, "Теплосеть — обратный"),
        LayerSpec("HEAT_BRANCH", 7, "CONTINUOUS", 0.35, "Ответвления"),
        LayerSpec("HEAT_SLEEVE", 8, "DASHED", 0.25, "Футляр / канал"),
        LayerSpec("HEAT_EQUIP", 7, "CONTINUOUS", 0.25, "Арматура и оборудование"),
        LayerSpec("HEAT_WELL", 7, "CONTINUOUS", 0.35, "Камеры, колодцы"),
        LayerSpec("HEAT_LABEL", 7, "CONTINUOUS", 0.18, "Подписи диаметров"),
    ],
}

DEFAULT_LAYERS: list[LayerSpec] = [
    LayerSpec("NET_MAIN", 7, "CONTINUOUS", 0.5, "Сеть — магистраль"),
    LayerSpec("NET_BRANCH", 7, "CONTINUOUS", 0.35, "Сеть — ответвление"),
    LayerSpec("NET_EQUIP", 7, "CONTINUOUS", 0.25, "Арматура и оборудование"),
    LayerSpec("NET_LABEL", 7, "CONTINUOUS", 0.18, "Подписи"),
]

TEXT_STYLE = "NS_GOST"
TEXT_BOLD_STYLE = "NS_BOLD"
TEXT_FONT = "Arial"
DIM_STYLE = "NS_DIM"


def layers_for(network_type: str) -> list[LayerSpec]:
    return BASE_LAYERS + NETWORK_LAYERS.get(network_type, DEFAULT_LAYERS)


def layer_names(network_type: str) -> set[str]:
    return {l.name for l in layers_for(network_type)}


def layer_of(network_type: str, role: str, kind: str = "main") -> str:
    """Роль → слой. role: main|branch|inlet|equip|well|label|sleeve."""
    table = {
        "gas": {
            "main": "GAS_MAIN",
            "branch": "GAS_BRANCH",
            "inlet": "GAS_INLET",
            "outlet": "GAS_BRANCH",
            "crossing": "GAS_SLEEVE",
            "sleeve": "GAS_SLEEVE",
            "equip": "GAS_EQUIP",
            "well": "GAS_WELL",
            "label": "GAS_LABEL",
        },
        "heat": {
            "main": "HEAT_SUPPLY",
            "supply": "HEAT_SUPPLY",
            "return": "HEAT_RETURN",
            "branch": "HEAT_BRANCH",
            "inlet": "HEAT_BRANCH",
            "outlet": "HEAT_BRANCH",
            "crossing": "HEAT_SLEEVE",
            "sleeve": "HEAT_SLEEVE",
            "equip": "HEAT_EQUIP",
            "well": "HEAT_WELL",
            "label": "HEAT_LABEL",
        },
    }.get(network_type)
    if not table:
        return {
            "main": "NET_MAIN",
            "branch": "NET_BRANCH",
            "inlet": "NET_BRANCH",
            "outlet": "NET_BRANCH",
            "crossing": "NET_BRANCH",
            "sleeve": "NET_BRANCH",
            "equip": "NET_EQUIP",
            "well": "NET_EQUIP",
            "label": "NET_LABEL",
        }.get(role, "NET_MAIN")
    if role == "automatic" and kind in table:
        return table[kind]
    return table.get(role, table["main"])


def apply_to_dxf(doc, network_type: str) -> None:
    """Создаёт слои, типы линий, текстовый и размерный стили."""
    from ezdxf.enums import TextEntityAlignment  # noqa: F401  (проверка импорта ezdxf)

    # типы линий: в новом документе уже есть стандартные при setup=True,
    # но на всякий случай догружаем недостающие.
    existing = {lt.dxf.name for lt in doc.linetypes}
    for name in ("DASHED", "CENTER", "DASHDOT", "DOT"):
        if name not in existing:
            try:
                doc.linetypes.add(
                    name,
                    pattern=[0.5, 0.25, -0.25] if name == "DASHED" else [1.0, 0.5, -0.25, 0.25, -0.25],
                    description=name,
                )
            except Exception:
                pass

    for spec in layers_for(network_type):
        if spec.name in doc.layers:
            layer = doc.layers.get(spec.name)
        else:
            layer = doc.layers.add(spec.name)
        layer.color = spec.color
        layer.dxf.linetype = spec.linetype if spec.linetype in doc.linetypes else "CONTINUOUS"
        layer.dxf.lineweight = snap_lw(spec.lw)
        layer.description = spec.description

    if TEXT_STYLE not in doc.styles:
        style = doc.styles.add(TEXT_STYLE, font=TEXT_FONT)
        style.dxf.width = 1.0
    if TEXT_BOLD_STYLE not in doc.styles:
        bold = doc.styles.add(TEXT_BOLD_STYLE, font=TEXT_FONT + " Bold")
        bold.dxf.width = 1.0

    doc.header["$CLAYER"] = layers_for(network_type)[0].name if not network_type else layer_of(
        network_type, "main"
    )

# Слой → тип линии (для рендера PDF/PNG, где DXF-типы линий не работают).
LINETYPE_BY_LAYER: dict[str, str] = {}
for _spec in BASE_LAYERS + [l for ls in NETWORK_LAYERS.values() for l in ls] + DEFAULT_LAYERS:
    LINETYPE_BY_LAYER[_spec.name] = _spec.linetype


def render_dashes(layer: str) -> tuple | None:
    """Штриховой шаблон matplotlib для слоя (None — сплошная)."""
    lt = LINETYPE_BY_LAYER.get(layer, "CONTINUOUS")
    if lt == "DASHED":
        return (0, (4.0, 2.0))
    if lt == "CENTER":
        return (0, (8.0, 2.0, 2.0, 2.0))
    if lt in {"DOT", "DASHDOT"}:
        return (0, (1.0, 1.5))
    return None
