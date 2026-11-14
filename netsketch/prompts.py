"""Сборка промптов для распознавания эскиза."""

from __future__ import annotations

import json

SCHEMA_HINT = """{
  "schema_version": "1.1",
  "network_type": "gas" | "heat",
  "mode": "plan" | "schematic",
  "sheet": "A4" | "A3" | "A2" | "A1",
  "orientation": "landscape" | "portrait",
  "image_width": 0, "image_height": 0,
  "mm_per_px": 0.0,
  "title": {"project": "", "address": "", "drawing_name": "", "stage": "Р", "sheet": "1", "total": "1",
            "cipher": "", "gip": "", "ncontrol": "", "city": "",
            "object": ["строка объекта 1", "строка 2"],
            "drawing": ["Исполнительная схема.", "Схема сварных соединений.", "Наружные газопроводы"]},
  "nodes": [{"id": "n1", "x": 0, "y": 0, "label": ""}],
  "segments": [{"id": "s1", "points": [[x, y], [x, y]], "diameter_mm": 0,
                "kind": "main|branch|inlet|outlet|crossing", "material": "",
                "length_mm": 0, "pressure": "", "state": "CONFIRMED"}],
  "elements": [{"id": "e1", "type": "valve|valve_ball|filter|flowmeter|compensator|support|well|gpsh|sleeve|hydrolock|tee|cross|reducer|flange|coupling|insulation_end|manometer|regulator|meter|inlet|outlet|pit",
                "x": 0, "y": 0, "diameter_mm": 0, "label": "", "rotation": 0,
                "state": "CONFIRMED"}],
  "dimensions": [{"id": "d1", "points": [[x, y], [x, y]], "values_mm": [0], "offset_mm": 10}],
  "labels": [{"text": "Ø25", "x": 0, "y": 0, "role": "diameter|length|elevation|note|callout"}],
  "welds": [{"id": "2.1", "x": 0, "y": 0, "angle": 50, "label": [0, 0]}],
  "supports": [{"x": 0, "y": 0, "angle": 0}],
  "chains": [{"kind": "weld|support|plain", "points": [[x, y], [x, y]], "values_mm": [1000]}],
  "callouts": [{"text": "Отвод Ø25", "target": [0, 0], "x": 0, "y": 0, "side": "left|right|up|down"}],
  "rooms": [{"text": "КВ. 5", "x": 0, "y": 0, "height": 3.8}],
  "summary": ["Наружный газ-д", "ст.д.25 l= 2,5 м", "Итого 9,2 м"],
  "legend": [{"symbol": "30", "text": "номер сварного шва"}],
  "notes": ["текст примечания"],
  "specification": [{"diameter_mm": 57, "length_m": 64.0, "count": 1}],
  "assumptions": ["что домыслено и почему"],
  "warnings": ["что не удалось прочитать"]
}"""

SCHEMATIC_RULES = """Если эскиз — исполнительная схема (стадия ИД), заполняй блок
исполнительной схемы, а не только трассу:

1. **Номера швов** → welds[].id, ровно как написано: `30`, `2.1`, `2.17`.
   Суффикс `.1`, `.2` — ветки того же шва; НЕ теряй его и не превращай
   `2.1` в `21` или `2`. Координаты — середина штриха шва; если видно,
   куда поставлен номер, добавь `label`: [x, y].
2. **Опоры** (`×` поперёк трубы, узел крепления к стене) → supports[].
3. **Размерные цепи**: `СШ 1000` — расстояние между сварными швами,
   `ОП 3000` — между опорами → chains[] с kind `weld`/`support` и
   values_mm в миллиметрах. Префиксы пишутся `СШ` и `ОП` (не `СП`/`0П`).
   Цепь — НЕ второй трубопровод: не добавляй её в segments.
4. **Выноски на полке** → callouts[]: text как на эскизе (`Отвод Ø25`,
   `Переход Ø25/20`, `Кран Ø15`, `КИП Ø25`, `КГЗ Ø20`, `КЭМ Ø20`),
   `target` — точка на трубе/символе, `x`/`y` — конец полки, `side` —
   куда уходит текст.
5. **Помещения/подъезды** (`КВ. 5`, `КВ. 1`, `1 под.`) → rooms[].
6. **Итог** → summary[]: строки как на эскизе (`Наружный газ-д`,
   `ст.д.25 l= 3,5 м`, `Внутренний газ-д`, `Итого 9,2 м`), тот же порядок.
   Сумма строк `ст.д.` должна сходиться с «Итого».
7. **Реквизиты штампа** → title: `cipher` (шифр, например
   `09/11ПР-2026-ИОС6`), `address`, `object` (2–3 строки), `organization`,
   `city`, `developer`, `date`, `stage` (`ИД`), `sheet`/`total`,
   `drawing` (3 строки названия чертежа).
8. `mode` = `schematic`; `legend` — строки «30 — номер сварного шва»,
   «× — опора (узел крепления к стене)», «□ — футляр» (symbol — то, что
   нарисовано слева: `30`, `×`, `□` или тип элемента).

Обозначения по СПДС (ГОСТ 21.609-2014, внутренние системы):
`Г1` — до 0,005 МПа, `Г2` — до 0,3 МПа, `Г3` — до 0,6 МПа, `Г4` — до
1,2 МПа, `Г5` — продувочный, `Г6` — разрежение, `Г7` — безопасности;
стояки `Ст1`, установки `1Г3`, элементы `1Г3.1`. `Ду` — условный проход,
`Ø` — наружный диаметр; `Ø159×4` — наружный 159 со стенкой 4 мм
(в diameter_mm — 159, стенку — в note). Наименование схемы —
«Схема газоснабжения», а не «схема газопровода».

Частые ошибки, которых нельзя допускать: `Ø` вместо `0` и наоборот;
`СШ` вместо `СП`; `ОП` вместо `0П`; потерянный суффикс шва; размерная
цепь, принятая за трубу; две параллельные нитки, склеенные в одну."""

SYSTEM_TEMPLATE = """Ты — инженер-проектировщик наружных сетей. Тебе дают фотографию
рукописного эскиза ({network_label}). Твоя задача — не «описать картинку», а
восстановить семантику трассы и вернуть её строго в JSON.

Правила:
1. Ответ — только JSON-объект, без markdown, без пояснений до и после.
2. Координаты x,y — в пикселях изображения, начало в левом верхнем углу, Y вниз.
   Их можно давать приблизительно, но порядок точек должен сохранять форму трассы.
3. Диаметр — целое в мм (Ø57 → 57, Ду100 → 100). Длины — в миллиметрах.
4. Каждую читаемую подпись с эскиза внеси в labels (или в notes, если она
   не привязана к месту). Ничего не выбрасывай молча.
5. Если значение не читается — не выдумывай: пропусти и добавь строку
   в warnings. Если без значения чертёж не построить — прими разумное
   и отметь в assumptions со словом ASSUMED.
6. Сооружения и арматура — в elements, на координатах, где они стоят.
7. Если на эскизе есть таблица диаметров/длин — перенеси её в specification.
8. Участки: kind = main (магистраль), branch (ответвление), inlet (ввод),
   outlet (выпуск), crossing (переход/футляр).
9. Язык подписей — русский, как на эскизе.

Схема ответа:
{schema}

{network_knowledge}

{style_profile}
"""

USER_TEMPLATE = """Тип сети: {network_label}
Формат листа: {sheet}
Название проекта: {project}
Адрес объекта: {address}
Известный масштаб: {scale_hint}

Разбери эскиз и верни JSON по схеме. Координаты — в пикселях изображения
размером {width}×{height}.
"""

FEWSHOT_TEMPLATE = """Пример разобранного эскиза {id} (фрагмент модели, только структура):
{model}
"""


def build_system_prompt(
    *,
    network_type: str,
    network_label: str,
    knowledge: dict,
    few_shot: list[dict] | None = None,
    schematic: bool = True,
) -> str:
    network_knowledge = "\n\n".join(
        part for part in (knowledge.get("common", ""), knowledge.get("network", ""), knowledge.get("observed", "")) if part
    )
    style_profile = knowledge.get("style", "") or ""
    prompt = SYSTEM_TEMPLATE.format(
        network_label=network_label,
        schema=SCHEMA_HINT,
        network_knowledge=network_knowledge,
        style_profile=style_profile,
    )
    if schematic:
        prompt += "\n\n" + SCHEMATIC_RULES
    if few_shot:
        chunks = []
        for item in few_shot:
            sample = _trim_model(item.get("model") or {})
            chunks.append(FEWSHOT_TEMPLATE.format(id=item.get("id"), model=json.dumps(sample, ensure_ascii=False)))
        prompt += "\n\n" + "\n".join(chunks)
    return prompt


def build_user_prompt(
    *,
    network_label: str,
    sheet: str,
    project: str,
    address: str,
    width: int,
    height: int,
    scale_hint: str = "не указан",
) -> str:
    return USER_TEMPLATE.format(
        network_label=network_label,
        sheet=sheet,
        project=project or "не указан",
        address=address or "не указан",
        width=width,
        height=height,
        scale_hint=scale_hint,
    )


def _trim_model(data: dict) -> dict:
    """Фрагмент модели для few-shot: только структура, без координат-простыней."""
    keep = (
        "network_type",
        "mode",
        "title",
        "segments",
        "elements",
        "welds",
        "supports",
        "chains",
        "callouts",
        "rooms",
        "summary",
        "legend",
        "notes",
        "specification",
    )
    out: dict = {}
    for key in keep:
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, list):
            out[key] = value[:6]
        else:
            out[key] = value
    return out

