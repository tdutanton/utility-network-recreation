"""Командная строка NetSketch.

    python -m netsketch serve                 # веб-интерфейс
    python -m netsketch build model.json      # модель → DWG/PDF/PNG
    python -m netsketch recognize sketch.jpg  # эскиз → model.json
    python -m netsketch doctor                # проверка окружения
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .build import build_drawings
from .config import load_settings


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    settings = load_settings()
    if args.port:
        settings.port = args.port
    if args.no_browser:
        settings.open_browser = False
    serve(settings)
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from .gost_sheet import GostSheet
    from .model import load_model_file

    model, warnings = load_model_file(args.model)
    if warnings:
        print("предупреждения модели:")
        for w in warnings:
            print("  -", w)
    title = model.title.__dict__.copy()
    for key in ("project", "address", "organization", "developer", "checker", "cipher", "object", "drawing"):
        value = getattr(args, key, None)
        if value:
            title[key] = value
    sheet = None
    if args.stamp:
        sheet = GostSheet("A3", "landscape", args.stamp)
    res = build_drawings(
        model,
        args.out,
        stem=args.stem or Path(args.model).stem,
        title=title,
        sheet=sheet,
        scale=args.scale or None,
        mode=args.mode,
        make_dwg=not args.no_dwg,
    )
    print(json.dumps({"files": res.files, "errors": res.errors, "scale": res.info.scale,
                      "mode": res.info.mode, "stamp": res.info.stamp_corner,
                      "warnings": res.info.warnings}, ensure_ascii=False, indent=2))
    return 0 if not res.errors else 1


def cmd_recognize(args: argparse.Namespace) -> int:
    from .recognize import RecognitionError, recognize

    settings = load_settings()
    image = Path(args.image)
    if not image.exists():
        print(f"нет файла: {image}", file=sys.stderr)
        return 2
    label = settings.network_types.get(args.network, {}).get("label", args.network)
    try:
        result = recognize(
            settings=settings,
            job_dir=Path(args.out_dir or image.parent),
            images=[image],
            network_type=args.network,
            network_label=label,
            sheet=args.sheet,
            project=args.project,
            address=args.address,
        )
    except RecognitionError as exc:
        print(f"ошибка распознавания: {exc}", file=sys.stderr)
        return 1
    out = Path(args.out or (image.with_suffix(".model.json")))
    out.write_text(json.dumps(result.data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"готово: {out}  ({result.provider}/{result.model}, {result.elapsed:.1f} с)")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    settings = load_settings()
    print(f"NetSketch {__version__}")
    print(f"  проект:          {settings.root}")
    print(f"  Open CAD Studio: {settings.ocs_exe or 'НЕ НАЙДЕН'}")
    print(f"  DWG версия:      {settings.dwg_version}")
    print(f"  провайдер:       {settings.llm_provider}")
    print(f"  модель:          {settings.llm_model or '—'}")
    print(f"  base_url:        {settings.llm_base_url or '—'}")
    print(f"  ключ:            {'задан' if settings.llm_api_key else 'не задан'}")
    print(f"  команда:         {settings.llm_command or '—'}")
    print(f"  готово к распознаванию: {'да' if settings.llm_ready else 'нет'}")
    print(f"  типы сетей:      {', '.join(settings.network_types)}")
    print(f"  примеры:         {settings.examples_dir}")
    try:
        import ezdxf  # noqa: F401
        import matplotlib  # noqa: F401
        import PIL  # noqa: F401
        import pymupdf  # noqa: F401

        print("  библиотеки:      ezdxf, matplotlib, Pillow, PyMuPDF — ok")
    except ImportError as exc:
        print(f"  библиотеки:      не хватает {exc.name}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="netsketch", description="Чертежи инженерных сетей по эскизам")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="запустить веб-интерфейс")
    p_serve.add_argument("--port", type=int, default=0)
    p_serve.add_argument("--no-browser", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    p_build = sub.add_parser("build", help="построить чертёж по model.json")
    p_build.add_argument("model")
    p_build.add_argument("--out", default="output")
    p_build.add_argument("--stem", default="")
    p_build.add_argument("--scale", type=int, default=0)
    p_build.add_argument("--mode", default="", choices=["", "plan", "schematic"],
                         help="plan — план в масштабе, schematic — лист ГОСТ с штампом")
    p_build.add_argument("--stamp", default="", choices=["", "left", "right", "auto"],
                         help="угол штампа для schematic")
    p_build.add_argument("--no-dwg", action="store_true")
    p_build.add_argument("--project", default="")
    p_build.add_argument("--address", default="")
    p_build.add_argument("--organization", default="")
    p_build.add_argument("--developer", default="")
    p_build.add_argument("--checker", default="")
    p_build.add_argument("--cipher", default="")
    p_build.add_argument("--object", default="")
    p_build.add_argument("--drawing", default="")
    p_build.set_defaults(func=cmd_build)

    p_rec = sub.add_parser("recognize", help="распознать эскиз в model.json")
    p_rec.add_argument("image")
    p_rec.add_argument("--network", default="gas")
    p_rec.add_argument("--sheet", default="A4")
    p_rec.add_argument("--project", default="")
    p_rec.add_argument("--address", default="")
    p_rec.add_argument("--out", default="")
    p_rec.add_argument("--out-dir", default="")
    p_rec.set_defaults(func=cmd_recognize)

    p_doc = sub.add_parser("doctor", help="проверить окружение")
    p_doc.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

