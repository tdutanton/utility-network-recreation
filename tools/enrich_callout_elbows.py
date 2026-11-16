"""Дополнить модели выносок изломом поводка ``callouts[].elbow``.

    python tools\\enrich_callout_elbows.py            # отчёт, без записи
    python tools\\enrich_callout_elbows.py --write    # записать в модели

Модели gas/1–4 уже собраны — здесь они НЕ пересобираются. Скрипт читает
готовые `.cache/etalon-dxf/*.dxf` и дописывает в каждую выноску то, чего
в модели не было:

* ``elbow`` — точка излома поводка (мм листа), это ``last_leader_point``
  настоящей ветки MULTILEADER (не proxy/virtual geometry, где лежит ещё
  подчёркивание текста);
* ``align`` — к какому краю прижат текст (`mtext.alignment` 1/4/7 → left,
  3/6/9 → right);
* ``x``/``y`` — если в модели записан конец полки, а не вставка текста
  (так было у фасада gas/1), они заменяются на ``mtext.insert``;
* ``text`` — если в модели перевод строки MULTILEADER был склеен пробелом,
  возвращается авторская многострочность (`КранØ15\\nИСØ15`); это одна
  выноска, а не две.

Сопоставление — по тексту и острию стрелки (допуск 1 мм), один-к-одному
по возрастанию расстояния. Несопоставленные выноски печатаются в отчёте и
остаются без `elbow` — рендер нарисует их по-старому.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".cache" / "etalon-spec"))

import ezdxf  # noqa: E402

import extract as ex  # noqa: E402

# Модель -> (сконвертированный DXF, рамка листа и масштаб для не-A3 файлов).
# В gas2/3/4.dxf лежит весь объект (много листов), поэтому общий frame_scale
# не годится: рамка конкретного листа и цена единицы взяты из скриптов,
# которыми собирались эти модели (to_iso2/to_iso3/to_iso.py).
Rect = tuple[float, float, float, float]
SHEETS: list[tuple[Path, Path, Rect | None, float | None]] = [
    (Path("examples/gas/1/models/1_фасад.schematic.json"), Path(".cache/etalon-dxf/1_фасад.dxf"), None, None),
    (Path("examples/gas/1/models/2_кв1_5.schematic.json"), Path(".cache/etalon-dxf/2_кв1_5.dxf"), None, None),
    (Path("examples/gas/1/models/3_кв_2_6.schematic.json"), Path(".cache/etalon-dxf/3_кв_2_6.dxf"), None, None),
    (Path("examples/gas/1/models/4_кв3_7.schematic.json"), Path(".cache/etalon-dxf/4_кв3_7.dxf"), None, None),
    (Path("examples/gas/1/models/5_кв4_8.schematic.json"), Path(".cache/etalon-dxf/5_кв4_8.dxf"), None, None),
    (Path("examples/gas/1/models/6_кв9_13.schematic.json"), Path(".cache/etalon-dxf/6_кв9_13.dxf"), None, None),
    (Path("examples/gas/1/models/7_кв10_19.schematic.json"), Path(".cache/etalon-dxf/7_кв10_19.dxf"), None, None),
    (Path("examples/gas/1/models/8_кв11_15.schematic.json"), Path(".cache/etalon-dxf/8_кв11_15.dxf"), None, None),
    (Path("examples/gas/1/models/9_кв12_16.schematic.json"), Path(".cache/etalon-dxf/9_кв12_16.dxf"), None, None),
    (
        Path("examples/gas/2/models/общая.schematic.json"),
        Path(".cache/etalon-dxf/gas2.dxf"),
        (252948.0, -89178.0, 297048.0, -57993.0),
        105.0,
    ),
    (
        Path("examples/gas/3/models/общая.schematic.json"),
        Path(".cache/etalon-dxf/gas3.dxf"),
        (304034.0, -172525.0, 348134.0, -141340.0),
        105.0,
    ),
    (
        Path("examples/gas/4/models/общая.schematic.json"),
        Path(".cache/etalon-dxf/gas4.dxf"),
        (122575.0, 41765.0, 166675.0, 72950.0),
        105.0,
    ),
]

TIP_TOL = 1.0  # мм: острие модели и эталона


@dataclass
class Leader:
    text: str
    tips: list[tuple[float, float]]
    elbow: tuple[float, float]
    insert: tuple[float, float]
    align: str


def norm_text(value: str) -> str:
    return " ".join((value or "").replace("\n", " ").replace("\\P", " ").split())


def tidy_text(value: str) -> str:
    """Сохранить авторские переводы строк, убрав лишние пробелы внутри строк."""
    lines = [" ".join(line.split()) for line in (value or "").replace("\\P", "\n").splitlines()]
    return "\n".join(line for line in lines if line)


def read_leaders(
    path: Path, rect: Rect | None = None, scale: float | None = None
) -> list[Leader]:
    """Настоящие ветки MULTILEADER: острия, last_leader_point, вставка текста."""
    doc = ezdxf.readfile(str(path))
    if rect is not None and scale:
        def to_mm(x: float, y: float) -> list[float]:
            return [(x - rect[0]) / scale, (y - rect[1]) / scale]
    else:
        frame_norm = ex.Norm(*ex.frame_scale(doc))

        def to_mm(x: float, y: float) -> list[float]:
            return frame_norm.pt(x, y)

    out: list[Leader] = []
    for e in doc.modelspace().query("MULTILEADER"):
        ctx = e.context
        mt = getattr(ctx, "mtext", None)
        if mt is None:
            continue
        text = ex.clean_mtext(mt.default_content or "")
        if not text.strip():
            continue
        tips: list[tuple[float, float]] = []
        elbow_raw = None
        for ld in getattr(ctx, "leaders", []) or []:
            elbow_raw = ld.last_leader_point
            for ln in getattr(ld, "lines", []) or []:
                verts = list(getattr(ln, "vertices", []) or [])
                if verts:
                    tips.append(tuple(to_mm(float(verts[-1][0]), float(verts[-1][1]))))
        if not tips or elbow_raw is None:
            continue
        align = {1: "left", 4: "left", 7: "left", 3: "right", 6: "right", 9: "right"}.get(
            int(mt.alignment), ""
        )
        out.append(
            Leader(
                text=text,
                tips=tips,
                elbow=tuple(to_mm(float(elbow_raw[0]), float(elbow_raw[1]))),
                insert=tuple(to_mm(float(mt.insert[0]), float(mt.insert[1]))),
                align=align,
            )
        )
    return out


def apply_to_data(data: dict[str, Any], leaders: list[Leader]) -> tuple[int, int, list[str]]:
    """Дописать elbow/align/anchor в выноски. Возвращает (изломов, без пары, лог)."""
    callouts = [c for c in (data.get("callouts") or []) if isinstance(c, dict)]
    pairs: list[tuple[float, int, int]] = []
    for ci, callout in enumerate(callouts):
        text = norm_text(str(callout.get("text") or ""))
        targets = [
            (float(t[0]), float(t[1]))
            for t in (callout.get("targets") or [])
            if isinstance(t, (list, tuple)) and len(t) >= 2
        ]
        if not text or not targets:
            continue
        for li, leader in enumerate(leaders):
            if norm_text(leader.text) != text:
                continue
            d_tip = min(math.dist(t, tip) for t in targets for tip in leader.tips)
            x, y = callout.get("x"), callout.get("y")
            d_anchor = (
                math.dist((float(x), float(y)), leader.insert)
                if x is not None and y is not None
                else 9e9
            )
            # в старых моделях target иногда равен излому, а не острию:
            # тогда выручает совпадение вставки текста. На фасаде наоборот —
            # якорь был концом полки, поэтому достаточно остия.
            if min(d_tip, d_anchor) > max(TIP_TOL, 3.0):
                continue
            pairs.append((min(d_tip, d_anchor), ci, li))
    pairs.sort(key=lambda p: p[0])

    used_c: set[int] = set()
    used_l: set[int] = set()
    matched: list[tuple[int, Leader]] = []
    for score, ci, li in pairs:
        if ci in used_c or li in used_l or score > 1.0:
            continue
        used_c.add(ci)
        used_l.add(li)
        matched.append((ci, leaders[li]))

    log: list[str] = []
    updated = 0
    for ci, leader in matched:
        callout = callouts[ci]
        label = norm_text(leader.text)
        changed = False
        # в старых моделях переводы строк MULTILEADER склеены пробелом —
        # возвращаем авторскую многострочность (одна выноска, текст в \P)
        author_text = tidy_text(leader.text)
        if author_text and author_text != str(callout.get("text") or ""):
            if norm_text(author_text) == norm_text(str(callout.get("text") or "")):
                log.append(f"«{label}»: многострочность {str(callout.get('text'))!r} -> {author_text!r}")
                callout["text"] = author_text
                changed = True
        old_elbow = callout.get("elbow")
        callout["elbow"] = [round(leader.elbow[0], 1), round(leader.elbow[1], 1)]
        if old_elbow != callout["elbow"]:
            changed = True
        if leader.align and callout.get("align") != leader.align:
            callout["align"] = leader.align
            changed = True

        # target в старых моделях мог указывать на излом или конец полки —
        # ставим настоящие острия стрелок из веток MULTILEADER
        new_targets = [[round(t[0], 1), round(t[1], 1)] for t in leader.tips]
        old_targets = callout.get("targets") or []
        if len(old_targets) != len(new_targets) or any(
            math.dist((float(a[0]), float(a[1])), (b[0], b[1])) > 0.5
            for a, b in zip(old_targets, new_targets)
        ):
            log.append(
                f"«{label}»: острие {[[round(float(v),1) for v in t[:2]] for t in old_targets]} -> {new_targets}"
            )
            callout["targets"] = new_targets
            callout["tx"] = new_targets[0][0]
            callout["ty"] = new_targets[0][1]
            changed = True

        x, y = callout.get("x"), callout.get("y")
        if x is not None and y is not None:
            if abs(float(x) - leader.insert[0]) > 0.6 or abs(float(y) - leader.insert[1]) > 0.6:
                log.append(
                    f"«{label}»: якорь ({float(x):.1f},{float(y):.1f}) -> "
                    f"({leader.insert[0]:.1f},{leader.insert[1]:.1f})"
                )
                callout["x"] = round(leader.insert[0], 1)
                callout["y"] = round(leader.insert[1], 1)
                changed = True
        if changed:
            updated += 1

    unmatched = [norm_text(str(c.get("text") or "")) for i, c in enumerate(callouts) if i not in used_c]
    for text in unmatched:
        log.append(f"не сопоставлена выноска «{text}»")
    return updated, len(unmatched), log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="записать изменения в модели")
    args = parser.parse_args(argv)

    total_updated = 0
    total_unmatched = 0
    for model_path, dxf_path, rect, scale in SHEETS:
        if not model_path.exists():
            print(f"! нет модели {model_path}")
            continue
        if not dxf_path.exists():
            print(f"! нет DXF {dxf_path}")
            continue
        data = json.loads(model_path.read_text(encoding="utf-8-sig"))
        updated, unmatched, log = apply_to_data(data, read_leaders(dxf_path, rect, scale))
        total_updated += updated
        total_unmatched += unmatched
        for msg in log:
            print(f"  {msg}")
        tag = f"{model_path.parent.parent.name}/{model_path.name}"
        print(f"[{tag}] изломов: {updated}, без пары: {unmatched}")
        if args.write:
            model_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

    print(f"\nитого изломов: {total_updated}, без пары: {total_unmatched}")
    if not args.write:
        print("это отчёт; для записи запусти с --write")
    return 0 if total_unmatched == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
