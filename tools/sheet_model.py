"""Сборка модели исполнительной схемы из готового DWG (спеки extract.py).

    python tools/sheet_model.py --spec .cache/etalon-spec/kv2_6.json \
        --out examples/gas/1/models/3_кв_2_6.schematic.json \
        --sheet 3 --source examples/gas/1/result/dwg/3_кв_2_6.dwg

Правила общие для всех листов серии «квартирная схема»:
* трубы склеиваются в трассы по концам, дуги дают вершину угла;
* засечки швов — короткие штрихи 6 мм, номер берётся из ближайшего TEXT;
* опоры — пары штрихов ±45° с общим центром;
* выноски — MULTILEADER (острие → полка → сторона), из текста берётся тип;
* счётчик и футляр — маленькие прямоугольники на трубе;
* квартиры — крупные тексты «КВ. N», итог и легенда — MTEXT справа от чертежа.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

X_MAX = 258.0  # правее — легенда/итог
Y_MIN = 42.0

ELEMENT_BY_TEXT = (
    ("тройник", "tee"),
    ("переход", "reducer"),
    ("кэм", "kem"),
    ("ктз", "kgz"),
    ("кшпр", "valve_ball"),
    ("кран", "valve_ball"),
    ("фильтр", "filter"),
)

TITLE_BASE = {
    "cipher": "09/11ПР-2026-ИОС6",
    "address": "город Великий Новгород, ул. Красилова, д. 51/28",
    "object_lines": [
        "Капитальный ремонт систем газоснабжения многоквартирного жилого дома по адресу:",
        "город Великий Новгород, ул. Красилова, д. 51/28",
    ],
    "stage": "ИД",
    "total": "9",
    "organization": 'ООО "Новгородаудит-ЭНЕРГО"',
    "city": "Великий Новгород",
    "developer": "Евгеньев А.А.",
    "date": "10.26",
    "drawing": ["Исполнительная схема.", "Схема сварных соединений.", "Внутренние газопроводы"],
}

META = {
    "fillet_mm": 4.6,
    "weld_height": 4.26,
    "callout_height": 4.26,
    "weld_stroke": 6.0,
    "support_size": 4.8,
    "legend_height": 4.5,
    "legend_row": 10.8,
    "legend_marker_height": 2.4,
    "summary_height": 11.26,
    "summary_row": 12.9,
    "legend_at": [270.3, 240.5],
    "summary_at": [271.9, 213.4],
}


def norm_angle(angle: float) -> float:
    """Угол к диапазону [-90, 90): -45 и 135 — одно и то же зеркало."""
    a = math.fmod(angle + 90.0, 180.0)
    if a < 0:
        a += 180.0
    return a - 90.0


def is_diag(angle: float, tol: float = 5.0) -> bool:
    return abs(abs(norm_angle(angle)) - 45.0) <= tol


def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def seg_proj(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy or 1.0
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    q = (a[0] + dx * t, a[1] + dy * t)
    return q, math.hypot(p[0] - q[0], p[1] - q[1])


def in_area(x, y):
    return x < X_MAX and y > Y_MIN


def build_paths(edges):
    nodes: list[tuple] = []

    def node_of(p):
        for i, q in enumerate(nodes):
            if dist(p, q) <= 2.0:
                return i
        nodes.append(tuple(p))
        return len(nodes) - 1

    adj: dict[int, list[tuple[int, tuple | None]]] = {}
    for a, b, corner in edges:
        na, nb = node_of(a), node_of(b)
        if na == nb:
            continue
        adj.setdefault(na, []).append((nb, corner))
        adj.setdefault(nb, []).append((na, corner))

    used: set[tuple[int, int]] = set()
    paths: list[list[tuple]] = []

    def walk(start: int, nxt: int, corner):
        path = [nodes[start]]
        prev, cur = start, nxt
        while True:
            path.append(nodes[cur])
            if corner is not None:
                path.insert(len(path) - 1, corner)
            used.add((prev, cur))
            used.add((cur, prev))
            follows = [(n, c) for n, c in adj[cur] if (cur, n) not in used]
            if not follows:
                break
            prev, cur = cur, follows[0][0]
            corner = follows[0][1]
        return path

    for start, nbrs in adj.items():
        if len(nbrs) != 1:
            continue
        n, corner = nbrs[0]
        if (start, n) in used:
            continue
        paths.append(walk(start, n, corner))
    for start, nbrs in adj.items():
        for n, corner in nbrs:
            if (start, n) in used:
                continue
            paths.append(walk(start, n, corner))
    return paths


def is_symbol_rect(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    return 7.0 <= max(w, h) <= 10.0 and 1.5 <= min(w, h) <= 4.5


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--source", default="")
    ap.add_argument("--date", default="10.26")
    args = ap.parse_args(argv)

    data = json.loads(Path(args.spec).read_text(encoding="utf-8"))

    edges = []
    symbols = []
    for p in data["pipes"]:
        pts = p.get("points") or []
        if len(pts) < 2 or not all(in_area(q[0], q[1]) for q in pts):
            continue
        if len(pts) == 4 and is_symbol_rect(pts):
            symbols.append(pts)
            continue
        for a, b in zip(pts, pts[1:]):
            if dist(a, b) > 0.3:
                edges.append((tuple(a), tuple(b), None))
    for arc in data["arcs"]:
        c, r = arc["c"], arc["r"]
        if not in_area(c[0], c[1]):
            continue
        a0, a1 = math.radians(arc["a0"]), math.radians(arc["a1"])
        t1 = (c[0] + r * math.cos(a0), c[1] + r * math.sin(a0))
        t2 = (c[0] + r * math.cos(a1), c[1] + r * math.sin(a1))
        edges.append((t1, t2, (t1[0] + t2[0] - c[0], t1[1] + t2[1] - c[1])))

    segments = []
    for path in build_paths(edges):
        cleaned = [path[0]]
        for q in path[1:]:
            if dist(q, cleaned[-1]) > 0.05:
                cleaned.append(q)
        if len(cleaned) < 2:
            continue
        length = sum(dist(a, b) for a, b in zip(cleaned, cleaned[1:]))
        xs = [q[0] for q in cleaned]
        ys = [q[1] for q in cleaned]
        if length < 10.0 or (max(xs) - min(xs) < 13.0 and max(ys) - min(ys) < 13.0):
            continue
        segments.append(
            {
                "points": [[round(q[0], 1), round(q[1], 1)] for q in cleaned],
                "diameter_mm": 25,
            }
        )
    segments.sort(key=lambda s: -sum(dist(tuple(a), tuple(b)) for a, b in zip(s["points"], s["points"][1:])))

    def snap_to_pipe(p):
        best = None
        for s in segments:
            pts = [tuple(q) for q in s["points"]]
            for a, b in zip(pts, pts[1:]):
                q, d = seg_proj(p, a, b)
                if best is None or d < best[0]:
                    best = (d, q)
        return best[1] if best and best[0] < 6.0 else p

    def pipe_dir(p):
        for s in segments:
            pts = [tuple(q) for q in s["points"]]
            for a, b in zip(pts, pts[1:]):
                _, d = seg_proj(p, a, b)
                if d < 1.5:
                    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        return 0.0

    strokes = [
        s
        for s in data["short_lines"]
        if s["layer"] == "0" and in_area(s["mid"][0], s["mid"][1]) and 4.5 <= s["len"] <= 8.0
    ]
    supports = []
    used: set[int] = set()
    for i, s in enumerate(strokes):
        if i in used or abs(s["len"] - 4.8) > 0.5 or not is_diag(s["angle"], 4.0):
            continue
        for j in range(i + 1, len(strokes)):
            t = strokes[j]
            if j in used:
                continue
            if abs(t["mid"][0] - s["mid"][0]) <= 0.7 and abs(t["mid"][1] - s["mid"][1]) <= 0.7:
                if is_diag(t["angle"], 4.0) and norm_angle(s["angle"]) * norm_angle(t["angle"]) < 0:
                    used.add(i)
                    used.add(j)
                    q = snap_to_pipe((s["mid"][0], s["mid"][1]))
                    supports.append({"x": round(q[0], 1), "y": round(q[1], 1), "angle": 0.0})
                    break

    weld_strokes = [
        s for i, s in enumerate(strokes) if i not in used and 5.0 < s["len"] < 7.5 and 35 < abs(norm_angle(s["angle"])) < 75
    ]
    for s in weld_strokes:
        q = snap_to_pipe((s["mid"][0], s["mid"][1]))
        s["mid"] = [q[0], q[1]]

    num = re.compile(r"^\d+(\.\d+){1,2}$")
    texts = [t for t in data["texts"] if in_area(t["x"], t["y"])]
    welds = []
    for t in texts:
        label = t["text"].strip()
        if not num.match(label) or not (1.9 <= t["h"] <= 2.5):
            continue
        near = min(weld_strokes, key=lambda w: dist((w["mid"][0], w["mid"][1]), (t["x"], t["y"])), default=None)
        if near is None:
            continue
        welds.append(
            {
                "id": label,
                "x": round(near["mid"][0], 1),
                "y": round(near["mid"][1], 1),
                "angle": round(abs(near["angle"]), 1),
                "label": [round(t["x"], 1), round(t["y"], 1)],
            }
        )

    callouts = []
    elements = []
    for lead in data["leaders"]:
        raw = " ".join((lead.get("text") or "").replace("\n", " ").split())
        pts = lead.get("points") or []
        if not raw or len(pts) < 2 or not in_area(pts[0][0], pts[0][1]):
            continue
        tip = pts[0]
        # подпись ставится в точку вставки текста MULTILEADER; конец полки
        # (pts[-1]) — это конец подчёркивания, он дальше текста на его ширину
        anchor = lead.get("at") or pts[-1]  # точка вставки текста MULTILEADER
        callouts.append(
            {
                "text": raw,
                "targets": [[round(tip[0], 1), round(tip[1], 1)]],
                "x": round(anchor[0], 1),
                "y": round(anchor[1], 1),
                "side": "right" if anchor[0] >= tip[0] else "left",
                "fixed": True,
            }
        )
        low = raw.lower()
        kind = next((k for prefix, k in ELEMENT_BY_TEXT if low.startswith(prefix)), None)
        if kind:
            q = snap_to_pipe((tip[0], tip[1]))
            elements.append(
                {
                    "id": f"e{len(elements) + 1}",
                    "type": kind,
                    "x": round(q[0], 1),
                    "y": round(q[1], 1),
                    "rotation": round(pipe_dir(tip), 1),
                }
            )

    # счётчик (горизонтальный прямоугольник) и футляр (вертикальный)
    for pts in symbols:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        q = snap_to_pipe((cx, cy))
        kind = "flowmeter" if w > h else "sleeve"
        elements.append(
            {
                "id": f"e{len(elements) + 1}",
                "type": kind,
                "x": round(q[0], 1),
                "y": round(q[1], 1),
                "rotation": 0.0 if w > h else 90.0,
            }
        )

    rooms = []
    for t in texts:
        label = t["text"].strip()
        if label.upper().startswith("КВ"):
            rooms.append(
                {"text": label, "x": round(t["x"], 1), "y": round(t["y"] - 3.0, 1), "height": 4.26, "label_align": "left"}
            )

    summary, summary_at, legend_at = [], META["summary_at"], META["legend_at"]
    for t in data["texts"]:
        label = t.get("text") or ""
        if t["x"] <= X_MAX:
            continue
        if "Итого" in label and "\n" in label:
            summary = [line.strip() for line in label.split("\n")]
            summary_at = [round(t["x"] - 1.0, 1), round(t["y"], 1)]
        if "номер сварного" in label.lower():
            legend_at = [round(t["x"] + 2.0, 1), round(t["y"], 1)]

    meta = dict(META)
    meta["source"] = args.source or args.spec
    meta["legend_at"] = legend_at
    meta["summary_at"] = summary_at

    title = dict(TITLE_BASE)
    title["sheet"] = args.sheet
    title["date"] = args.date

    model = {
        "schema_version": "1.1",
        "network_type": "gas",
        "mode": "schematic",
        "sheet": "A3",
        "orientation": "landscape",
        "placement": "absolute",
        "title": title,
        "meta": meta,
        "segments": [{"id": f"s{i + 1}", "points": s["points"], "diameter_mm": 25, "kind": "main" if i == 0 else "branch"} for i, s in enumerate(segments)],
        "welds": welds,
        "supports": supports,
        "elements": elements,
        "callouts": callouts,
        "rooms": rooms,
        "summary": summary,
        "legend": [
            {"symbol": "30", "text": "номер сварного шва"},
            {"symbol": "×", "text": "опора (узел крепления к стене)"},
            {"symbol": "□", "text": "футляр"},
        ],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"-> {out}\n   трасс {len(model['segments'])}, швов {len(welds)}, опор {len(supports)}, "
        f"выносок {len(callouts)}, элементов {len(elements)}, квартир {len(rooms)}, строк итога {len(summary)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
