"""Приёмка распознавания (фаза 5): сверка модели с тем, что есть на эталоне.

    python tools/recognize_check.py --extract     # снять ожидания из 9 DWG
    python tools/recognize_check.py               # сверить модели examples/ с эталоном
    python tools/recognize_check.py --model путь  # сверить одну модель
    python tools/recognize_check.py --selftest    # проверить сам инструмент

Ожидания берутся из готовых DWG пользователя (`examples/gas/1/result/dwg`):
номера сварных швов (с суффиксами `.1`), шифр штампа, строки итогового блока.
Для каждой модели сравнивается набор номеров швов, шифр и арифметика итога —
именно то, что чаще всего теряется при распознавании эскиза.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ezdxf  # noqa: E402

from netsketch.dwg import dwg_to_dxf  # noqa: E402
from netsketch.model import load_model_file, validate_model  # noqa: E402

DWG_DIR = ROOT / "examples" / "gas" / "1" / "result" / "dwg"
MODELS = ROOT / "examples" / "gas" / "1" / "models"
EXPECT = ROOT / "examples" / "gas" / "1" / "etalon-expectations.json"
DXF_CACHE = ROOT / ".cache" / "etalon-dxf"

FRAME_LAYER = "анп Рамка жирная"
WELD_ID = re.compile(r"^\d+(\.\d+)?$")
_SHORT_LINE = (4.0, 8.0)  # штрих шва, мм
_TICK_ANGLE = (40.0, 70.0)
_TICK_NEAR = 9.0  # мм от номера до штриха


def dxf_of(dwg: Path) -> Path:
    DXF_CACHE.mkdir(parents=True, exist_ok=True)
    target = DXF_CACHE / (dwg.stem + ".dxf")
    if target.exists() and target.stat().st_size > 1024:
        return target
    dwg_to_dxf(dwg, target)
    return target


def sheet_frame(doc) -> tuple[tuple[float, float], float]:
    from ezdxf import bbox as ebbox

    xs: list[float] = []
    ys: list[float] = []
    for e in doc.modelspace():
        if e.dxf.layer != FRAME_LAYER:
            continue
        b = ebbox.extents([e], fast=True)
        if b.has_data:
            xs += [b.extmin.x, b.extmax.x]
            ys += [b.extmin.y, b.extmax.y]
    if not xs:
        return (0.0, 0.0), 1.0
    return (min(xs), min(ys)), (max(xs) - min(xs)) / 420.0


def entities(doc):
    out = []
    for e in doc.modelspace():
        if e.dxftype() == "INSERT":
            try:
                out.extend(e.virtual_entities())
            except Exception:
                pass
        else:
            out.append(e)
    return out


def _stamp_rect(corner: str) -> tuple[float, float, float, float]:
    return (20.0, 5.0, 205.0, 60.0) if corner == "left" else (230.0, 5.0, 415.0, 60.0)


def extract_expectations(dwg: Path) -> dict:
    doc = ezdxf.readfile(str(dxf_of(dwg)))
    (ox, oy), scale = sheet_frame(doc)
    if scale <= 0:
        scale = 1.0

    def mm(x, y):
        return ((x - ox) / scale, (y - oy) / scale)

    def length_of(a, b):
        return ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 / scale

    welds: list[str] = []
    cipher = ""
    summary: list[str] = []
    texts: list[tuple[str, float, float, float, str]] = []
    callouts = sum(1 for e in doc.modelspace() if e.dxftype() == "MULTILEADER")

    for e in entities(doc):
        t = e.dxftype()
        if t not in {"TEXT", "MTEXT"}:
            continue
        value = e.dxf.text if t == "TEXT" else e.text
        value = value.replace("\\P", "\n")
        value = re.sub(r"\{\\[^;]*;", "", value).replace("}", "")
        value = value.replace("%%C", "Ø").replace("%%c", "Ø")
        p = e.dxf.insert
        x, y = mm(p[0], p[1])
        h = (e.dxf.height if t == "TEXT" else e.dxf.char_height) / scale
        texts.append((value.strip(), x, y, h, t))

    for text, x, y, h, t in texts:
        if "ИОС" in text and len(text) < 40 and not cipher:
            cipher = text
            break
    # угол штампа: по положению шифра
    corner = "left" if cipher and next((x for t, x, y, h, _ in texts if "ИОС" in t), 999) < 210 else "right"
    stamp = _stamp_rect(corner)

    # легенда: рядом с ней стоит образец номера шва («30»), его нельзя
    # считать швом на схеме
    legend_at = [
        (x, y)
        for text, x, y, h, t in texts
        if "номер сварного" in text.lower() or "номер шва" in text.lower()
    ]

    for text, x, y, h, t in texts:
        if "\n" in text and h > 2.5 and re.search(r"Итого|lобщ|ст\.?\s*д", text):
            summary = [line.strip() for line in text.split("\n") if line.strip()]
        if not (t == "TEXT" and WELD_ID.match(text) and 1.2 <= h <= 3.2):
            continue
        if stamp[0] <= x <= stamp[2] and stamp[1] <= y <= stamp[3]:
            continue  # графы штампа
        if any(math.dist((x, y), pos) <= 25.0 for pos in legend_at):
            continue  # образец номера в легенде
        welds.append(text)

    total = None
    for line in summary:
        m = re.search(r"(?:Итого|lобщ|всего)[^\d\-]*([\d.,]+)", line, re.IGNORECASE)
        if m:
            total = float(m.group(1).replace(",", "."))

    return {
        "file": dwg.name,
        "corner": corner,
        "cipher": cipher,
        "welds": sorted(set(welds), key=_weld_key),
        "summary": summary,
        "total_m": total,
        "callouts": callouts,
    }


def _weld_key(value: str) -> tuple[int, float]:
    parts = value.split(".")
    return (int(parts[0]), float(parts[1]) if len(parts) > 1 else 0.0)


def cmd_extract() -> int:
    if not DWG_DIR.is_dir():
        print(f"нет папки эталонов: {DWG_DIR}", file=sys.stderr)
        return 2
    data = {}
    for dwg in sorted(DWG_DIR.glob("*.dwg")):
        try:
            info = extract_expectations(dwg)
        except Exception as exc:  # noqa: BLE001
            print(f"{dwg.name}: ОШИБКА {exc}")
            continue
        data[dwg.stem] = info
        print(f"{dwg.stem}: швов {len(info['welds'])}, шифр {info['cipher']!r}, "
              f"итог {info['total_m']}, выносок {info['callouts']}")
    EXPECT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n-> {EXPECT}")
    return 0


def compare(model_path: Path, expected: dict) -> list[str]:
    model, parse_warnings = load_model_file(str(model_path))
    problems: list[str] = list(parse_warnings)
    problems.extend(validate_model(model))

    got = {w.id for w in model.welds}
    want = set(expected.get("welds") or [])
    if want or got:
        missing = sorted(want - got, key=_weld_key)
        extra = sorted(got - want, key=_weld_key)
        if missing:
            problems.append(f"не найдены швы: {', '.join(missing)}")
        if extra:
            problems.append(f"лишние номера: {', '.join(extra)}")

    cipher = (model.title.cipher or "").strip()
    want_cipher = (expected.get("cipher") or "").strip()
    if want_cipher and cipher != want_cipher:
        problems.append(f"шифр «{cipher}» вместо «{want_cipher}»")

    want_total = expected.get("total_m")
    if want_total and model.summary:
        m = None
        for line in model.summary:
            hit = re.search(r"Итого[^\d]*([\d.,]+)", line)
            if hit:
                m = float(hit.group(1).replace(",", "."))
        if m is None:
            problems.append("в итоговом блоке нет строки «Итого»")
        elif abs(m - want_total) > 0.15:
            problems.append(f"итог {m:g} м вместо {want_total:g} м")

    return problems


def negative_selftest(expected: dict) -> list[str]:
    """Проверка, что инструмент действительно ловит ошибки распознавания."""
    failures: list[str] = []
    source = json.loads((MODELS / "2_кв1_5.schematic.json").read_text(encoding="utf-8"))
    tmp = ROOT / ".cache" / "recognize_check_tmp.json"

    # 1. потерян суффикс шва: 2.1 → 21
    broken = json.loads(json.dumps(source))
    for w in broken["welds"]:
        if w["id"] == "2.1":
            w["id"] = "21"
    tmp.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
    problems = compare(tmp, expected)
    if not any("21" in p for p in problems):
        failures.append("не поймана потеря суффикса шва (2.1 → 21)")

    # 2. неверный шифр
    broken = json.loads(json.dumps(source))
    broken["title"]["cipher"] = "004-ППР-2026-ИОС8"
    tmp.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
    if not any("шифр" in p for p in compare(tmp, expected)):
        failures.append("не пойман неверный шифр")

    # 3. итог не сходится с суммой строк
    broken = json.loads(json.dumps(source))
    broken["summary"] = [line if "Итого" not in line else "Итого 12,0 м" for line in broken["summary"]]
    tmp.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
    problems = compare(tmp, expected)
    if not any("не сходится" in p for p in problems):
        failures.append("не пойман несходящийся итог")

    # 4. «Ø» прочитан как «0» и «СП» вместо «СШ»
    from netsketch.model import model_from_dict, validate_model

    bad, _ = model_from_dict(
        {
            "mode": "schematic",
            "welds": [{"id": "2.1", "x": 0, "y": 0}],
            "callouts": [
                {"text": "0 25", "x": 0, "y": 0, "target": [1, 1]},
                {"text": "СП 1000", "x": 0, "y": 0, "target": [1, 1]},
            ],
            "title": {"cipher": "x"},
            "legend": [{"symbol": "30", "text": "номер сварного шва"}],
        }
    )
    warnings = validate_model(bad)
    if not any("0П" in w or "СП" in w for w in warnings):
        failures.append("не поймано СП/0П вместо СШ/ОП")
    if not any("Ø" in w for w in warnings):
        failures.append("не поймано 0 вместо Ø")

    # 5. «2,1» нормализуется в «2.1»
    from netsketch.model import normalize_recognized

    fixed = normalize_recognized({"welds": [{"id": "2,1", "x": 0, "y": 0}]})
    if fixed["welds"][0]["id"] != "2.1":
        failures.append("не нормализуется запятая в номере шва (2,1 → 2.1)")

    tmp.unlink(missing_ok=True)
    return failures


def main() -> int:
    if "--extract" in sys.argv:
        return cmd_extract()

    if not EXPECT.exists():
        print(f"нет ожиданий: {EXPECT}. Сначала запустите --extract", file=sys.stderr)
        return 2
    expected_all = json.loads(EXPECT.read_text(encoding="utf-8"))

    single = None
    if "--model" in sys.argv:
        single = Path(sys.argv[sys.argv.index("--model") + 1])

    if "--selftest" in sys.argv:
        model_path = MODELS / "2_кв1_5.schematic.json"
        expected = expected_all.get("2_кв1_5") or {}
        problems = compare(model_path, expected)
        print(f"самопроверка на эталонной модели {model_path.name}: проблем {len(problems)}")
        for p in problems:
            print(f"   - {p}")
        negatives = negative_selftest(expected)
        if negatives:
            print(f"негативные проверки: провалов {len(negatives)}")
            for p in negatives:
                print(f"   - {p}")
        else:
            print("негативные проверки: все ошибки ловятся")
        return 0 if not problems and not negatives else 1

    if single:
        key = None
        for cand in expected_all:
            if cand in single.stem or single.stem in cand:
                key = cand
        if not key:
            print(f"не нашёл ожиданий для {single.name}", file=sys.stderr)
            return 2
        problems = compare(single, expected_all[key])
        print(f"{single.name}: проблем {len(problems)}")
        for p in problems:
            print(f"   - {p}")
        return 0 if not problems else 1

    failures = 0
    for model_path in sorted(MODELS.glob("*.json")):
        key = None
        for cand in expected_all:
            if cand in model_path.stem:
                key = cand
        if not key:
            continue
        model, _ = load_model_file(str(model_path))
        if model.mode != "schematic":
            print(f"  ..  {model_path.name}: режим {model.mode} — пропуск (сверяются схемы)")
            continue
        problems = compare(model_path, expected_all[key])
        status = "ok  " if not problems else "FAIL"
        print(f"{status} {model_path.name} ← эталон {key}: проблем {len(problems)}")
        for p in problems[:6]:
            print(f"       - {p}")
        failures += bool(problems)
    print()
    print("ВСЁ ЗЕЛЁНОЕ" if not failures else f"ПРОВАЛЕНО: {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

