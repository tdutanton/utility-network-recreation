"""Конфигурация приложения.

Все настройки читаются из переменных окружения, при старте подхватывается
файл `.env` рядом с корнем проекта. Никаких секретов в коде.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Минимальный парсер .env (KEY=VALUE, # комментарии, кавычки)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # окружение главнее файла
        os.environ.setdefault(key, value)


_load_dotenv(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


@dataclass
class Settings:
    root: Path = ROOT
    data_dir: Path = ROOT / "data"
    examples_dir: Path = ROOT / "examples"
    knowledge_dir: Path = ROOT / "knowledge"
    web_dir: Path = ROOT / "web"
    pydeps_dir: Path = ROOT / ".pydeps"

    host: str = "127.0.0.1"
    port: int = 8770

    # --- LLM (распознавание эскиза) -------------------------------------
    # Провайдер: openai | deepseek | openrouter | gemini | ollama | custom | none
    llm_provider: str = "none"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout: int = 180
    llm_max_tokens: int = 8000
    llm_temperature: float = 0.1
    # Внешняя команда распознавания (для headless-агента):
    # получает путь к папке задачи, должна положить model.json.
    llm_command: str = ""

    # --- CAD ------------------------------------------------------------
    ocs_exe: str = ""
    dwg_version: str = "2018"
    default_sheet: str = "A4"
    default_orientation: str = "portrait"
    default_stamp: str = "horizontal"
    default_scale: int = 500

    # --- Поведение ------------------------------------------------------
    max_upload_mb: int = 25
    keep_jobs: int = 200
    open_browser: bool = True

    network_types: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def llm_ready(self) -> bool:
        if self.llm_command:
            return True
        return bool(self.llm_api_key and self.llm_model and self.llm_provider != "none")


PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4.1"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "google/gemini-2.0-flash-001"},
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
    },
    "ollama": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5vl:7b"},
    "custom": {"base_url": "", "model": ""},
}


def _find_ocs() -> str:
    """Ищем Open CAD Studio: env → PATH → стандартная установка."""
    candidates = [
        _env("NS_OCS_EXE"),
        shutil.which("OpenCADStudio") or "",
        r"C:\Program Files\Open CAD Studio\OpenCADStudio.exe",
        r"C:\Program Files (x86)\Open CAD Studio\OpenCADStudio.exe",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return str(Path(c))
    return ""


def load_settings() -> Settings:
    provider = (_env("NS_LLM_PROVIDER") or "none").lower()
    preset = PROVIDER_PRESETS.get(provider, {})
    s = Settings(
        host=_env("NS_HOST", "127.0.0.1"),
        port=_env_int("NS_PORT", 8770),
        llm_provider=provider,
        llm_base_url=_env("NS_LLM_BASE_URL") or preset.get("base_url", ""),
        llm_api_key=_env("NS_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", ""),
        llm_model=_env("NS_LLM_MODEL") or preset.get("model", ""),
        llm_timeout=_env_int("NS_LLM_TIMEOUT", 180),
        llm_max_tokens=_env_int("NS_LLM_MAX_TOKENS", 8000),
        llm_command=_env("NS_LLM_COMMAND"),
        ocs_exe=_find_ocs(),
        dwg_version=_env("NS_DWG_VERSION", "2018"),
        default_sheet=_env("NS_DEFAULT_SHEET", "A4"),
        default_orientation=_env("NS_DEFAULT_ORIENTATION", "portrait"),
        default_stamp=_env("NS_DEFAULT_STAMP", "horizontal"),
        default_scale=_env_int("NS_DEFAULT_SCALE", 500),
        max_upload_mb=_env_int("NS_MAX_UPLOAD_MB", 25),
        open_browser=_env("NS_OPEN_BROWSER", "1") not in {"0", "false", "no"},
    )
    try:
        s.llm_temperature = float(_env("NS_LLM_TEMPERATURE") or 0.1)
    except ValueError:
        s.llm_temperature = 0.1
    s.data_dir = Path(_env("NS_DATA_DIR") or (ROOT / "data"))
    s.examples_dir = Path(_env("NS_EXAMPLES_DIR") or (ROOT / "examples"))
    s.knowledge_dir = Path(_env("NS_KNOWLEDGE_DIR") or (ROOT / "knowledge"))
    s.network_types = discover_network_types(s.knowledge_dir)
    return s


# Сеть-типы, известные «из коробки». Новый тип = новый файл knowledge/<id>.md
# плюс, при необходимости, ветка оформления в netsketch/styles.py.
BUILTIN_NETWORK_TYPES: dict[str, dict[str, str]] = {
    "heat": {
        "label": "Теплоснабжение",
        "short": "Тепло",
        "discipline": "ТС",
        "default_drawing": "Схема тепловой сети",
        "default_stage": "Р",
        "default_sheet": "A3",
        "default_orientation": "portrait",
    },
    "gas": {
        "label": "Газоснабжение",
        "short": "Газ",
        "discipline": "ГСВ",
        "default_drawing": "Схема газоснабжения",
        "default_stage": "Р",
        "default_sheet": "A4",
        "default_orientation": "portrait",
    },
}


# Служебные документы в knowledge/: не являются типами сетей и не должны
# попадать в список на форме.
_KNOWLEDGE_DOCS = {"common", "readme", "index", "prompts", "template", "handoff"}


def discover_network_types(knowledge_dir: Path) -> dict[str, dict[str, str]]:
    found = dict(BUILTIN_NETWORK_TYPES)
    if knowledge_dir.is_dir():
        for md in knowledge_dir.glob("*.md"):
            key = md.stem.lower()
            if key in _KNOWLEDGE_DOCS or key.startswith("style"):
                continue
            # планы, схемы и отчёты — тоже документы, а не типы сетей
            if key.endswith(("-plan", "-schema", "-report", "-observed")):
                continue
            if key not in found:
                found[key] = {
                    "label": key.capitalize(),
                    "short": key.capitalize(),
                    "discipline": key.upper()[:6],
                    "default_drawing": f"Схема {key}",
                    "default_stage": "Р",
                }
    return found



