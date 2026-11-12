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
    """Пары «эскиз → семантическая модель» из examples/ для промпта."""
    index = load_index(settings)
    out: list[dict] = []
    for item in index.get("examples", []):
        if item.get("network") != network_type:
            continue
        model_path = item.get("model")
        if not model_path:
            continue
        p = settings.root / model_path
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append({"id": item.get("id"), "model": data, "notes": item.get("notes", "")})
        if len(out) >= limit:
            break
    return out
