# Схема model.json

Единственный контракт между распознаванием и черчением. Файл кладётся
в `data/jobs/<id>/model.json` или передаётся в `POST /api/jobs/<id>/model`.

## Полный пример

```json
{
  "schema_version": "1.0",
  "network_type": "gas",
  "sheet": "A3",
  "orientation": "landscape",
  "image_width": 1240,
  "image_height": 1754,
  "mm_per_px": null,
  "meta": { "two_pipe": false, "view": "plan" },

  "title": {
    "project": "Газоснабжение жилой застройки",
    "address": "г. Москва, ул. Примерная, 12",
    "drawing_name": "Схема газоснабжения",
    "stage": "Р", "sheet": "1", "total": "1",
    "organization": "ООО «Проект»",
    "developer": "Иванов", "checker": "Петров",
    "doc_code": "ГСВ-01-2026"
  },

  "nodes": [
    { "id": "n1", "x": 120, "y": 520 },
    { "id": "n2", "x": 420, "y": 520 }
  ],

  "segments": [
    {
      "id": "s1",
      "points": [[120, 520], [420, 520]],
      "diameter_mm": 108,
      "kind": "main",
      "material": "сталь",
      "length_mm": 24000,
      "pressure": "низкое",
      "state": "CONFIRMED"
    }
  ],

  "elements": [
    { "id": "e1", "type": "valve", "x": 220, "y": 520, "diameter_mm": 108 },
    { "id": "e2", "type": "well", "x": 420, "y": 520, "label": "Кол. 1" }
  ],

  "dimensions": [
    { "id": "d1", "points": [[120, 520], [420, 520]],
      "values_mm": [24000], "offset_mm": 10 }
  ],

  "labels": [
    { "text": "Ø108", "x": 270, "y": 500, "role": "diameter" }
  ],

  "callouts": [{ "n": 1, "text": "фильтр" }],
  "legend": [{ "symbol": "filter", "text": "Фильтр" }],
  "notes": ["Газопровод подземный, глубина 1,2 м."],
  "specification": [
    { "diameter_mm": 108, "length_m": 106.4, "count": 1 }
  ],
  "assumptions": ["ASSUMED: глубина заложения принята 1,2 м."],
  "warnings": ["Не читается номер колодца у правого края."]
}
```

## Поля

| Поле | Обязательно | Смысл |
|---|---|---|
| `network_type` | да | `gas` / `heat` / ключ из `knowledge/*.md` |
| `sheet`, `orientation` | нет | по умолчанию `A3`, `landscape` |
| `image_width`, `image_height` | желательно | пиксели исходника (для калибровки) |
| `mm_per_px` | нет | масштаб скана; `null` — вычислить |
| `title` | да | реквизиты штампа |
| `nodes` | нет | точки трассы; нужны, если `segments` ссылаются на `from`/`to` |
| `segments` | да* | участки; `points` — ломаная ≥ 2 точек |
| `elements` | да* | арматура/сооружения на координатах |
| `dimensions` | нет | размерные цепи (значения в мм) |
| `labels` | нет | свободные подписи с эскиза |
| `legend` | нет | если пусто — собирается из использованных элементов |
| `notes` | нет | примечания на лист |
| `specification` | нет | таблица диаметров/длин; если пусто — считается по участкам |
| `assumptions` | нет | домысленное, попадёт на слой `ASSUMED` |
| `warnings` | нет | что не прочитано — в «На что обратить внимание» |

\* хотя бы одно из `segments` / `elements` должно быть непустым.

## Перечисления

`segments[].kind`: `main`, `branch`, `inlet`, `outlet`, `crossing`, `riser`.

`elements[].type`:

```
valve valve_ball gate_valve filter flowmeter compensator support well gpsh
sleeve hydrolock tee cross reducer flange coupling insulation_end manometer
regulator meter inlet outlet riser pit unknown
```

Русские подписи («задвижка», «колодец», «ГРПШ», «муфта», «переход»)
нормализуются автоматически.

`state`: `CONFIRMED` (прочитано), `DERIVED` (вычислено), `ASSUMED` (домыслено).

`labels[].role`: `diameter`, `length`, `elevation`, `note`, `callout`, `title`.

## Как считается масштаб

1. `mm_per_px` задан — используется как есть (CONFIRMED).
2. Иначе `сумма длин / длина линии в пикселях` (DERIVED).
3. Иначе считается, что эскиз покрывает ≈60 м (ASSUMED, есть примечание).

Дальше масштаб листа выбирается из ряда 1:50…1:5000 так, чтобы план занял
поле чертежа.

## Минимальный валидный файл

```json
{
  "network_type": "gas",
  "title": { "project": "Тест", "address": "Тест" },
  "segments": [
    { "id": "s1", "points": [[100, 100], [500, 100]], "diameter_mm": 57, "length_mm": 6000 }
  ],
  "elements": [
    { "id": "e1", "type": "valve", "x": 300, "y": 100 }
  ]
}
```
