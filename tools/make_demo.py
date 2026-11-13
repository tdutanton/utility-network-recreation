"""Демонстрационные модели: используются смоук-тестом и для показа возможностей.

    python tools/make_demo.py --type gas --out data/demo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from netsketch.build import build_drawings  # noqa: E402
from netsketch.model import model_from_dict  # noqa: E402


def gas_model() -> dict:
    return {
        "schema_version": "1.0",
        "network_type": "gas",
        "sheet": "A3",
        "orientation": "landscape",
        "mm_per_px": 80,
        "image_width": 1600,
        "image_height": 1000,
        "title": {
            "project": "Газоснабжение жилой застройки",
            "address": "г. Москва, ул. Примерная, д. 12",
            "drawing_name": "Схема газоснабжения",
            "stage": "Р",
            "sheet": "1",
            "total": "1",
            "organization": "ООО «Проект»",
            "developer": "Иванов",
            "checker": "Петров",
            "doc_code": "ГСВ-01-2026",
        },
        "nodes": [
            {"id": "n1", "x": 120, "y": 520},
            {"id": "n2", "x": 420, "y": 520},
            {"id": "n3", "x": 700, "y": 520},
            {"id": "n4", "x": 980, "y": 520},
            {"id": "n5", "x": 1250, "y": 520},
            {"id": "n6", "x": 1450, "y": 520},
            {"id": "n7", "x": 420, "y": 300},
            {"id": "n8", "x": 620, "y": 300},
            {"id": "n9", "x": 980, "y": 760},
        ],
        "segments": [
            {"id": "s1", "points": [[120, 520], [420, 520]], "diameter_mm": 108, "kind": "main", "length_mm": 24000},
            {"id": "s2", "points": [[420, 520], [700, 520]], "diameter_mm": 108, "kind": "main", "length_mm": 22400},
            {"id": "s3", "points": [[700, 520], [980, 520]], "diameter_mm": 108, "kind": "main", "length_mm": 22400},
            {"id": "s4", "points": [[980, 520], [1250, 520]], "diameter_mm": 108, "kind": "main", "length_mm": 21600},
            {"id": "s5", "points": [[1250, 520], [1450, 520]], "diameter_mm": 108, "kind": "main", "length_mm": 16000},
            {"id": "s6", "points": [[420, 520], [420, 300], [620, 300]], "diameter_mm": 57, "kind": "branch", "length_mm": 42000},
            {"id": "s7", "points": [[980, 520], [980, 760]], "diameter_mm": 32, "kind": "outlet", "length_mm": 19200},
        ],
        "elements": [
            {"id": "e1", "type": "valve", "x": 220, "y": 520, "diameter_mm": 108},
            {"id": "e2", "type": "filter", "x": 600, "y": 520, "diameter_mm": 108},
            {"id": "e3", "type": "flowmeter", "x": 800, "y": 520, "diameter_mm": 108},
            {"id": "e4", "type": "well", "x": 700, "y": 520, "label": "Кол. 1"},
            {"id": "e5", "type": "well", "x": 1250, "y": 520, "label": "Кол. 2"},
            {"id": "e6", "type": "gpsh", "x": 620, "y": 300, "label": "ГРПШ"},
            {"id": "e7", "type": "valve_ball", "x": 980, "y": 660, "diameter_mm": 32},
            {"id": "e8", "type": "tee", "x": 980, "y": 520},
            {"id": "e9", "type": "tee", "x": 420, "y": 520},
            {"id": "e10", "type": "inlet", "x": 120, "y": 520, "label": "Ввод Ø108"},
        ],
        "dimensions": [
            {
                "id": "d1",
                "points": [[120, 520], [420, 520], [700, 520], [980, 520], [1250, 520], [1450, 520]],
                "values_mm": [24000, 22400, 22400, 21600, 16000],
                "offset_mm": 12,
            }
        ],
        "labels": [
            {"text": "Ø108", "x": 270, "y": 500, "role": "diameter"},
            {"text": "Ø57", "x": 430, "y": 410, "role": "diameter"},
            {"text": "Ø32", "x": 995, "y": 640, "role": "diameter"},
        ],
        "legend": [
            {"symbol": "valve", "text": "Задвижка"},
            {"symbol": "valve_ball", "text": "Кран шаровой"},
            {"symbol": "filter", "text": "Фильтр"},
            {"symbol": "flowmeter", "text": "Расходомер"},
            {"symbol": "well", "text": "Колодец газовый"},
            {"symbol": "gpsh", "text": "ГРПШ"},
            {"symbol": "tee", "text": "Врезка (тройник)"},
        ],
        "notes": [
            "Газопровод принят подземной прокладки, глубина заложения 1,2 м.",
            "Диаметры и длины уточнить по проекту и ведомости.",
            "Испытание газопровода — воздухом, P = 0,3 МПа.",
        ],
        "specification": [
            {"diameter_mm": 108, "length_m": 106.4, "count": 1},
            {"diameter_mm": 57, "length_m": 42.0, "count": 1},
            {"diameter_mm": 32, "length_m": 19.2, "count": 1},
        ],
        "assumptions": [],
    }


def heat_model() -> dict:
    """Аксонометрическая схема: ствол по горизонтали, ветки под 30°, стояки вертикально."""
    return {
        "schema_version": "1.0",
        "network_type": "heat",
        "sheet": "A3",
        "orientation": "portrait",
        "mm_per_px": 55,
        "image_width": 1600,
        "image_height": 1000,
        "meta": {"two_pipe": True, "ortho": "iso", "projection": "axonometric"},
        "title": {
            "project": "Теплоснабжение квартала",
            "address": "г. Москва, ул. Примерная, д. 12",
            "drawing_name": "Схема тепловой сети",
            "stage": "Р",
            "sheet": "1",
            "total": "1",
            "organization": "ООО «Проект»",
            "developer": "Иванов",
            "checker": "Петров",
            "doc_code": "ТС-01-2026",
        },
        "nodes": [
            {"id": "n1", "x": 120, "y": 760},
            {"id": "n2", "x": 380, "y": 760},
            {"id": "n3", "x": 680, "y": 587},
            {"id": "n4", "x": 800, "y": 760},
            {"id": "n5", "x": 1120, "y": 760},
            {"id": "n6", "x": 900, "y": 633},
            {"id": "n7", "x": 1480, "y": 760},
        ],
        "segments": [
            {"id": "s1", "points": [[120, 760], [380, 760]], "diameter_mm": 159, "kind": "main", "length_mm": 14000},
            {"id": "s2", "points": [[380, 760], [800, 760]], "diameter_mm": 159, "kind": "main", "length_mm": 22000},
            {"id": "s3", "points": [[800, 760], [1120, 760]], "diameter_mm": 133, "kind": "main", "length_mm": 17000},
            {"id": "s4", "points": [[1120, 760], [1480, 760]], "diameter_mm": 108, "kind": "main", "length_mm": 19000},
            {"id": "s5", "points": [[380, 760], [680, 587], [680, 420]], "diameter_mm": 89, "kind": "branch", "length_mm": 18000},
            {"id": "s6", "points": [[1120, 760], [900, 633], [900, 470]], "diameter_mm": 76, "kind": "branch", "length_mm": 15000},
            {"id": "s7", "points": [[800, 760], [980, 864]], "diameter_mm": 57, "kind": "branch", "length_mm": 12000},
        ],
        "elements": [
            {"id": "e1", "type": "valve", "x": 260, "y": 760, "diameter_mm": 159},
            {"id": "e2", "type": "compensator", "x": 600, "y": 760, "diameter_mm": 159},
            {"id": "e3", "type": "support", "x": 480, "y": 760},
            {"id": "e4", "type": "support", "x": 980, "y": 760},
            {"id": "e5", "type": "well", "x": 380, "y": 760, "label": "ТК-1"},
            {"id": "e6", "type": "well", "x": 1120, "y": 760, "label": "ТК-2"},
            {"id": "e7", "type": "valve", "x": 900, "y": 540, "diameter_mm": 76},
            {"id": "e8", "type": "flowmeter", "x": 1400, "y": 760, "diameter_mm": 108},
            {"id": "e9", "type": "filter", "x": 520, "y": 679, "diameter_mm": 89},
            {"id": "e10", "type": "tee", "x": 800, "y": 760},
        ],
        "labels": [
            {"text": "Ø159", "x": 540, "y": 735, "role": "diameter"},
            {"text": "Ø133", "x": 960, "y": 735, "role": "diameter"},
            {"text": "Ø108", "x": 1300, "y": 735, "role": "diameter"},
            {"text": "Ø89", "x": 700, "y": 500, "role": "diameter"},
        ],
        "legend": [
            {"symbol": "valve", "text": "Задвижка"},
            {"symbol": "compensator", "text": "Компенсатор П-образный"},
            {"symbol": "support", "text": "Опора неподвижная"},
            {"symbol": "well", "text": "Тепловая камера"},
            {"symbol": "flowmeter", "text": "Расходомер"},
            {"symbol": "filter", "text": "Фильтр"},
            {"symbol": "tee", "text": "Ответвление"},
        ],
        "notes": [
            "Трасса тепловой сети — двухтрубная, подающий и обратный трубопроводы.",
            "Схема аксонометрическая: ствол по горизонтали, ответвления под 30°.",
            "Компенсация — П-образными компенсаторами.",
        ],
        "specification": [
            {"diameter_mm": 159, "length_m": 36.0, "count": 2},
            {"diameter_mm": 133, "length_m": 17.0, "count": 2},
            {"diameter_mm": 108, "length_m": 19.0, "count": 2},
            {"diameter_mm": 89, "length_m": 18.0, "count": 2},
        ],
        "assumptions": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", default="gas", choices=["gas", "heat"])
    ap.add_argument("--out", default=str(ROOT / "data" / "demo"))
    args = ap.parse_args()
    data = gas_model() if args.type == "gas" else heat_model()
    out = Path(args.out) / args.type
    out.mkdir(parents=True, exist_ok=True)
    (out / "model.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    model, warnings = model_from_dict(data)
    if warnings:
        print("warnings:", warnings)
    res = build_drawings(model, out, stem=f"demo_{args.type}", title=model.title.__dict__)
    print(json.dumps({"files": res.files, "errors": res.errors, "scale": res.info.scale,
                      "warnings": res.info.warnings, "prims": res.scene.count()}, ensure_ascii=False, indent=2))
    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
