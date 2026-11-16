"""Приёмка теплового листа heat/1: маркеры дефектов и ведомость.

    python tools\\heat_check.py

Проверяет то, что заменило 130 номеров на плане:

1. каждый дефект нарисован маркером (кружок r=1,0 мм), а не номером;
2. номеров дефектов на плане не осталось (в таблице — можно);
3. справа есть «Ведомость дефектов по подъездам», итог сходится с числом
   маркеров, столбцы 4/3/2/1 и «Всего» на месте;
4. таблица не налезает на план, план — на штамп и рамку;
5. DWG открывается обратно Open CAD Studio.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from netsketch.dwg import dwg_to_dxf  # noqa: E402
from netsketch.layout import _defect_table_data, build_scene  # noqa: E402
from netsketch.model import model_from_dict  # noqa: E402
from netsketch.scene import Circle, Line, Polyline, Text  # noqa: E402
from netsketch.sheets import Sheet  # noqa: E402
from netsketch.styles import layer_of  # noqa: E402

MODEL = ROOT / "examples" / "heat" / "1" / "models" / "obshaya.plan.json"
OUT = ROOT / "output"


def fail(errors: list[str], message: str) -> None:
    errors.append(message)
    print(f"  FAIL {message}")


def main() -> int:
    errors: list[str] = []
    data = json.loads(MODEL.read_text(encoding="utf-8-sig"))
    model, _ = model_from_dict(data)
    defects = [lbl for lbl in model.labels if lbl.role == "defect"]
    sheet = Sheet(model.sheet, model.orientation)
    scene, _ = build_scene(model, sheet=sheet, title=model.title.__dict__)
    print(f"NetSketch heat check: дефектов {len(defects)}, арматуры {len(model.elements)}")
    if not model.elements:
        fail(errors, "в модели нет арматуры (elements пуст)")

    # 1. маркеры
    markers = [p for p in scene.prims if isinstance(p, Circle) and abs(float(p.r) - 1.0) < 0.01]
    print(f"  маркеров-кружков: {len(markers)}")
    if len(markers) < len(defects):
        fail(errors, f"маркеров {len(markers)} < дефектов {len(defects)}")

    # 2. номера дефектов на плане
    codes = {str(lbl.text).strip() for lbl in defects}
    leftovers = [
        p
        for p in scene.prims
        if isinstance(p, Text)
        and str(p.text).strip() in codes
        and p.at[1] < 240.0
        and p.at[0] < 290.0
    ]
    if leftovers:
        fail(errors, f"на плане остались номера дефектов: {[p.text for p in leftovers[:5]]}")

    # 3. ведомость
    table = _defect_table_data(model)
    if not table:
        fail(errors, "нет данных ведомости дефектов")
    else:
        texts = [str(p.text) for p in scene.prims if isinstance(p, Text)]
        if not any(t.startswith("Ведомость дефектов") for t in texts):
            fail(errors, "нет заголовка ведомости дефектов")
        total = str(sum(int(row[-1]) for row in table["rows"][:-1]))
        if total != str(table["rows"][-1][-1]):
            fail(errors, "итог ведомости не сходится с суммой строк")
        if total != str(len(defects)):
            fail(errors, f"итог ведомости {total} != маркеров {len(defects)}")
        for cell in table["header"][2:]:
            if cell not in texts:
                fail(errors, f"нет заголовка столбца «{cell}»")
        print(f"  ведомость: {len(table['rows']) - 1} строк, итог {total}")

    # 4. рамка/штамп/пересечения
    defect_at = (model.meta or {}).get("defect_table_at")
    if defect_at:
        x_right, y_top = float(defect_at[0]), float(defect_at[1])
        x_left = x_right - sum(table["col_widths"]) if table else x_right - 120
        y_bottom = y_top - 9.2 - 4.4 * (len(table["rows"]) if table else 0)
        if y_bottom < 60.0:
            fail(errors, f"ведомость налезает на штамп (низ {y_bottom:.1f} < 60)")
        main_layer = layer_of(model.network_type, "main")
        below_table = [
            p
            for p in scene.prims
            if isinstance(p, (Line, Polyline))
            and p.layer == main_layer
            and any(
                x_left - 1 <= q[0] <= x_right + 1 and y_bottom - 1 <= q[1] <= y_top + 1
                for q in (p.points if isinstance(p, Polyline) else [p.a, p.b])
            )
        ]
        if below_table:
            fail(errors, f"план заходит в ведомость: {len(below_table)} линий")

    frame = sheet.frame
    outside = 0
    for p in scene.prims:
        pts = []
        if isinstance(p, Polyline):
            pts = p.points
        elif isinstance(p, Line):
            pts = [p.a, p.b]
        for q in pts:
            if q[0] < frame[0] - 0.5 or q[0] > frame[2] + 0.5 or q[1] < frame[1] - 0.5 or q[1] > frame[3] + 0.5:
                outside += 1
                break
    if outside:
        fail(errors, f"за рамкой линий: {outside}")

    # 5. DWG
    dwg = OUT / "heat1_obshaya.dwg"
    if not dwg.exists():
        fail(errors, "нет output/heat1_obshaya.dwg")
    else:
        try:
            dxf = dwg_to_dxf(dwg, ROOT / ".cache" / "heatcheck.dxf")
            import ezdxf

            count = len(list(ezdxf.readfile(str(dxf)).modelspace()))
            print(f"  DWG читается, сущностей {count}")
            if count < 100:
                fail(errors, f"DWG подозрительно пустой: {count}")
        except Exception as exc:  # noqa: BLE001
            fail(errors, f"DWG не читается: {type(exc).__name__}: {exc}")

    print("\n" + ("ВСЁ ЗЕЛЁНОЕ" if not errors else f"ПРОВАЛОВ: {len(errors)}"))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
