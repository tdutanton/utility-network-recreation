"""Сборка промптов для распознавания эскиза."""

from __future__ import annotations

import json

SCHEMA_HINT = """{
  "schema_version": "1.0",
  "network_type": "gas" | "heat",
  "sheet": "A4" | "A3" | "A2" | "A1",
  "orientation": "landscape" | "portrait",
  "image_width": 0, "image_height": 0,
  "mm_per_px": 0.0,
  "title": {"project": "", "address": "", "drawing_name": "", "stage": "Р", "sheet": "1", "total": "1"},
  "nodes": [{"id": "n1", "x": 0, "y": 0, "label": ""}],
  "segments": [{"id": "s1", "points": [[x, y], [x, y]], "diameter_mm": 0,
                "kind": "main|branch|inlet|outlet|crossing", "material": "",
                "length_mm": 0, "pressure": "", "state": "CONFIRMED"}],
  "elements": [{"id": "e1", "type": "valve|valve_ball|filter|flowmeter|compensator|support|well|gpsh|sleeve|hydrolock|tee|cross|reducer|flange|coupling|insulation_end|manometer|regulator|meter|inlet|outlet|pit",
                "x": 0, "y": 0, "diameter_mm": 0, "label": "", "rotation": 0,
                "state": "CONFIRMED"}],
  "dimensions": [{"id": "d1", "points": [[x, y], [x, y]], "values_mm": [0], "offset_mm": 10}],
  "labels": [{"text": "Ø25", "x": 0, "y": 0, "role": "diameter|length|elevation|note|callout"}],
  "callouts": [{"n": 1, "text": "фильтр"}],
  "legend": [{"symbol": "filter", "text": "фильтр"}],
  "notes": ["текст примечания"],
  "specification": [{"diameter_mm": 57, "length_m": 64.0, "count": 1}],
  "assumptions": ["что домыслено и почему"],
  "warnings": ["что не удалось прочитать"]
}"""

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
    keep = ("network_type", "title", "nodes", "segments", "elements", "legend", "notes", "specification")
    return {k: data.get(k) for k in keep if k in data}

