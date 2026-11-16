"""Проверка выносок: модель -> сцена -> MULTILEADER (острие, излом, полка).

    python tools\\callout_check.py

Проверяет модели gas/1–4 после обогащения `callouts[].elbow`:

1. у каждой выноски с `elbow` в сцене есть MULTILEADER с текстом в авторской
   точке (верхний угол, `align`), ветка идёт `полка -> излом -> острие`,
   полка стоит на уровне излома, конец полки — у противоположного края текста;
2. ветвящаяся выноска (`targets` > 1) имеет ветку на КАЖДОЕ острие;
3. точка излома в модели совпадает с `last_leader_point` эталонного
   MULTILEADER (`.cache/etalon-dxf`, допуск 0,3 мм), а `targets` — с его
   остриями.

Сцена строится тем же `layout.build_schematic_scene`, что и при сборке,
поэтому проверяется именно рендер, а не файл-посредник.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from netsketch.annotations import _callout_box, _callout_shelf_start  # noqa: E402
from netsketch.dxfout import scene_to_dxf  # noqa: E402
from netsketch.layout import build_schematic_scene  # noqa: E402
from netsketch.model import Model, model_from_dict  # noqa: E402
from netsketch.scene import MLeader, Scene, text_width  # noqa: E402

import enrich_callout_elbows as ec  # noqa: E402

TOL = 0.3


def norm_text(value: str) -> str:
    return " ".join((value or "").replace("\n", " ").replace("\\P", " ").split())


def check_scene(model: Model, sheet_name: str, scene: Scene) -> list[str]:
    errors: list[str] = []
    leaders = [p for p in scene.prims if isinstance(p, MLeader)]
    height = float((model.meta or {}).get("callout_height") or 2.2)
    checked = 0
    for callout in model.callouts:
        if callout.elbow is None or callout.x is None or callout.y is None:
            continue
        checked += 1
        text = callout.text
        align = str(callout.align or "").lower()
        width = text_width(text, height)
        left = callout.x - width if align == "right" else callout.x
        anchor = (left, callout.y)
        cands = [
            p
            for p in leaders
            if norm_text(p.text) == norm_text(text)
            and p.valign == "top"
            and math.dist(p.at, anchor) <= TOL
        ]
        if not cands:
            errors.append(f"{sheet_name}: нет MULTILEADER «{norm_text(text)}» у ({anchor[0]:.1f},{anchor[1]:.1f})")
            continue
        mleader = cands[0]
        targets = list(callout.targets)
        if not targets:
            errors.append(f"{sheet_name}: у выноски «{norm_text(text)}» нет targets")
            continue
        box = _callout_box((callout.x, callout.y), text, height, align)
        start = _callout_shelf_start(box, callout.elbow, (callout.x, callout.y), height)
        for target in targets:
            ok = any(
                len(path) >= 3
                and math.dist(path[0], start) <= TOL
                and any(math.dist(q, callout.elbow) <= TOL for q in path[1:-1])
                and math.dist(path[-1], target) <= TOL
                for path in mleader.leaders
            )
            if not ok:
                errors.append(
                    f"{sheet_name}: «{norm_text(text)}» нет ветки {start}->излом{callout.elbow}->острие{target}"
                )
    print(f"  {sheet_name}: выносок с изломом {checked}")
    return errors


def check_dxf(scene: Scene, model: Model, sheet_name: str) -> list[str]:
    """Геометрия, которая уедет в DWG: last_leader_point и dogleg.

    Если отдать builder'у всю ломаную, MULTILEADER добавляет свою «собачью
    ножку» от острия к тексту — в DWG появляется лишняя линия через лист.
    Поэтому проверяем контекст уже собранного DXF, а не только сцену.
    """
    errors: list[str] = []
    doc = scene_to_dxf(scene, model.network_type, dim_scale=1)
    heights = float((model.meta or {}).get("callout_height") or 2.2)
    leaders = []
    for entity in doc.modelspace().query("MULTILEADER"):
        for leader_data in getattr(entity.context, "leaders", []) or []:
            leaders.append(leader_data)
    checked = 0
    for callout in model.callouts:
        if callout.elbow is None or callout.x is None or callout.y is None:
            continue
        checked += 1
        near = [
            ld
            for ld in leaders
            if math.dist((ld.last_leader_point[0], ld.last_leader_point[1]), callout.elbow) <= TOL
        ]
        if not near:
            errors.append(f"{sheet_name}: в DXF нет last_leader_point у излома {callout.elbow}")
            continue
        text = callout.text
        align = str(callout.align or "").lower()
        box = _callout_box((callout.x, callout.y), text, heights, align)
        far = _callout_shelf_start(box, callout.elbow, (callout.x, callout.y), heights)
        want_dogleg = math.dist(far, callout.elbow)
        ok = False
        for ld in near:
            # вершины ветки идут от острия к излому, острие — первая
            ends = {
                (round(v[0], 1), round(v[1], 1))
                for ln in (getattr(ld, "lines", []) or [])
                for v in [ln.vertices[0]]
            }
            if abs(float(ld.dogleg_length) - want_dogleg) > TOL:
                continue
            if not all(any(math.dist(t, e) <= TOL for e in ends) for t in callout.targets):
                continue
            ok = True
            break
        if not ok:
            errors.append(
                f"{sheet_name}: «{norm_text(text)}» dogleg {want_dogleg:.1f} мм "
                f"или острия не совпали с DXF"
            )
    print(f"  {sheet_name}: проверено в DXF {checked}")
    return errors


def check_etalon(model: Model, dxf_path: Path, rect, scale, sheet_name: str) -> list[str]:
    errors: list[str] = []
    leaders = ec.read_leaders(dxf_path, rect, scale)
    used: set[int] = set()
    matched = 0
    for callout in model.callouts:
        if callout.elbow is None or not callout.targets:
            continue
        text = norm_text(callout.text)
        best = None
        for i, leader in enumerate(leaders):
            if i in used or norm_text(leader.text) != text:
                continue
            d_tip = min(math.dist(t, tip) for t in callout.targets for tip in leader.tips)
            if best is None or d_tip < best[0]:
                best = (d_tip, i, leader)
        if best is None or best[0] > TOL:
            errors.append(f"{sheet_name}: «{text}» не найдена в эталонном DXF")
            continue
        _, i, leader = best
        d_elbow = math.dist(callout.elbow, leader.elbow)
        d_anchor = math.dist((callout.x, callout.y), leader.insert) if callout.x is not None else 0.0
        if d_elbow > TOL:
            errors.append(f"{sheet_name}: «{text}» излом {callout.elbow} != эталон {leader.elbow}")
        if d_anchor > TOL:
            errors.append(f"{sheet_name}: «{text}» якорь {callout.x, callout.y} != эталон {leader.insert}")
        used.add(i)
        matched += 1
    print(f"  {sheet_name}: сверено с эталоном {matched}")
    return errors


def main() -> int:
    errors: list[str] = []
    for model_path, dxf_path, rect, scale in ec.SHEETS:
        if not model_path.exists():
            errors.append(f"нет модели {model_path}")
            continue
        data = json.loads(model_path.read_text(encoding="utf-8-sig"))
        model, _ = model_from_dict(data)
        tag = f"{model_path.parent.parent.name}/{model_path.name}"
        print(f"\n[{tag}]")
        if str((model.meta or {}).get("placement") or "").lower() != "absolute":
            print("  пропуск: координаты не absolute")
            continue
        scene, _ = build_schematic_scene(model, title=model.title.__dict__)
        errors.extend(check_scene(model, tag, scene))
        errors.extend(check_dxf(scene, model, tag))
        if dxf_path.exists():
            errors.extend(check_etalon(model, dxf_path, rect, scale, tag))
        else:
            errors.append(f"{tag}: нет DXF {dxf_path}")

    print("\n" + ("ВСЁ ЗЕЛЁНОЕ" if not errors else f"ПРОВАЛОВ: {len(errors)}"))
    for err in errors[:40]:
        print(f"  FAIL {err}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
