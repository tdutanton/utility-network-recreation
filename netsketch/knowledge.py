"""База знаний: тексты по типам сетей + профиль стиля, выученный на примерах."""

from __future__ import annotations

import json
from pathlib import Path

from .config import Settings


def _read(path: Path, limit: int = 20000) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""


def load_knowledge(settings: Settings, network_type: str) -> dict:
    base = settings.knowledge_dir
    return {
        "common": _read(base / "common.md"),
        "network": _read(base / f"{network_type}.md"),
        "observed": _read(base / "style-observed.md"),
        "style": style_profile(settings, network_type),
    }


def load_index(settings: Settings) -> dict:
    path = settings.examples_dir / "index.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def style_profile(settings: Settings, network_type: str) -> str:
    """Текстовое описание того, как оформлены готовые DWG пользователя."""
    index = load_index(settings)
    profile = (index.get("profiles") or {}).get(network_type)
    if not profile:
        return ""
    lines = [f"Профиль оформления по вашим готовым чертежам ({network_type}):"]
    for key, value in profile.items():
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value[:12])
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def few_shot(settings: Settings, network_type: str, limit: int = 2) -> list[dict]:
    """Пары «эскиз → семантическая модель» для промпта.

    Ищем в двух местах: `examples/index.json` (поле model) и файлы
    `examples/<тип>/<объект>/models/*.json`.
    """
    out: list[dict] = []
    seen: set[str] = set()

    for item in load_index(settings).get("examples", []):
        if item.get("network") != network_type or not item.get("model"):
            continue
        p = settings.root / item["model"]
        if not p.exists() or str(p) in seen:
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        seen.add(str(p))
        out.append({"id": item.get("id"), "model": data, "notes": item.get("notes", "")})
        if len(out) >= limit:
            return out

    net_dir = settings.examples_dir / network_type
    if net_dir.is_dir():
        for path in sorted(net_dir.glob("*/models/*.json")):
            if str(path) in seen:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            seen.add(str(path))
            out.append({"id": f"{network_type}/{path.parent.parent.name}/{path.stem}", "model": data, "notes": ""})
            if len(out) >= limit:
                break
    return out

