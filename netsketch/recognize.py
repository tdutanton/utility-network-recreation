"""Распознавание эскиза моделью зрения.

Провайдер по умолчанию — любой OpenAI-совместимый endpoint
(DeepSeek, OpenAI, OpenRouter, Gemini OpenAI-mode, Ollama, локальный сервер).
Альтернатива — внешняя команда (`NS_LLM_COMMAND`), которой передаётся папка
задачи: так распознавание можно повесить на headless-агента, не давая
пользователю доступа к чату.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings
from .knowledge import few_shot, load_knowledge
from .model import model_from_dict, normalize_recognized, validate_model
from .prompts import build_system_prompt, build_user_prompt

MAX_IMAGE_EDGE = 1600


class RecognitionError(RuntimeError):
    pass


class RecognitionUnavailable(RecognitionError):
    pass


@dataclass
class RecognitionResult:
    data: dict
    raw: str = ""
    provider: str = ""
    model: str = ""
    elapsed: float = 0.0
    warnings: list[str] = field(default_factory=list)


def prepare_image(path: str | Path, *, max_edge: int = MAX_IMAGE_EDGE) -> tuple[bytes, int, int, str]:
    """Уменьшает скан до разумного размера, возвращает JPEG-байты и размеры."""
    from PIL import Image

    path = Path(path)
    with Image.open(path) as img:
        img = img.convert("RGB")
        w, h = img.size
        scale = min(1.0, max_edge / max(w, h))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            w, h = img.size
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue(), w, h, "image/jpeg"


def pdf_to_image(pdf_path: str | Path, out_path: str | Path, dpi: int = 170) -> Path:
    """Первую страницу PDF — в PNG."""
    import pymupdf

    pdf_path = Path(pdf_path)
    out_path = Path(out_path)
    doc = pymupdf.open(pdf_path)
    if doc.page_count == 0:
        raise RecognitionError("PDF без страниц")
    page = doc[0]
    pix = page.get_pixmap(dpi=dpi)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(out_path)
    doc.close()
    return out_path


def extract_json(text: str) -> dict:
    """Достаёт JSON-объект из ответа модели, даже если он в ```json."""
    if not text:
        raise RecognitionError("модель вернула пустой ответ")
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RecognitionError(f"в ответе нет JSON-объекта: {text[:300]}")
    candidate = cleaned[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # типовые огрехи: висячие запятые и комментарии
        repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
        repaired = re.sub(r"//[^\n]*", "", repaired)
        return json.loads(repaired)


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:800]
        raise RecognitionError(f"HTTP {exc.code} от модели: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RecognitionError(f"нет связи с моделью ({url}): {exc.reason}") from exc


def call_vision(
    *,
    settings: Settings,
    system_prompt: str,
    user_prompt: str,
    images: list[bytes],
) -> tuple[str, dict]:
    if not settings.llm_base_url:
        raise RecognitionUnavailable("не задан NS_LLM_BASE_URL")
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    content: list[dict] = [{"type": "text", "text": user_prompt}]
    for blob in images:
        b64 = base64.b64encode(blob).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    payload = {
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
    }
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    data = _post_json(url, payload, headers, settings.llm_timeout)
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RecognitionError(f"неожиданный ответ модели: {json.dumps(data, ensure_ascii=False)[:600]}") from exc
    return text, data


def finalize(data: dict, network_type: str) -> tuple[dict, list[str]]:
    """Нормализовать ответ модели и проверить его до черчения.

    Возвращает данные с дополненным `warnings` и список предупреждений:
    именно здесь отлавливаются потерянные суффиксы швов, `0` вместо `Ø`,
    `СП`/`0П` вместо `СШ`/`ОП` и несходящийся итог длин.
    """
    data = normalize_recognized(data)
    data["network_type"] = network_type
    model, parse_warnings = model_from_dict(data)
    warnings = list(dict.fromkeys(list(data.get("warnings") or []) + parse_warnings + validate_model(model)))
    data["warnings"] = warnings
    return data, warnings


def recognize(
    *,
    settings: Settings,
    job_dir: Path,
    images: list[Path],
    network_type: str,
    network_label: str,
    sheet: str,
    project: str,
    address: str,
) -> RecognitionResult:
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)

    knowledge = load_knowledge(settings, network_type)
    system_prompt = build_system_prompt(
        network_type=network_type,
        network_label=network_label,
        knowledge=knowledge,
        few_shot=few_shot(settings, network_type, limit=3),
    )

    prepared = []
    first_w, first_h = 0, 0
    for path in images[:3]:
        blob, w, h, _ = prepare_image(path)
        if not first_w:
            first_w, first_h = w, h
        prepared.append(blob)

    user_prompt = build_user_prompt(
        network_label=network_label,
        sheet=sheet,
        project=project,
        address=address,
        width=first_w,
        height=first_h,
    )
    (job_dir / "prompt_system.txt").write_text(system_prompt, encoding="utf-8")
    (job_dir / "prompt_user.txt").write_text(user_prompt, encoding="utf-8")

    started = time.time()

    if settings.llm_command:
        data, raw = _run_command(settings, job_dir, network_type, system_prompt, user_prompt, images)
        data, warnings = finalize(data, network_type)
        return RecognitionResult(
            data=data,
            raw=raw,
            provider="command",
            model=settings.llm_command,
            elapsed=time.time() - started,
            warnings=warnings,
        )

    if not settings.llm_ready:
        raise RecognitionUnavailable(
            "распознавание не настроено: задайте NS_LLM_PROVIDER/NS_LLM_API_KEY/NS_LLM_MODEL "
            "в файле .env или NS_LLM_COMMAND"
        )

    text, payload = call_vision(
        settings=settings,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        images=prepared,
    )
    (job_dir / "llm_raw.txt").write_text(text, encoding="utf-8")

    data = extract_json(text)
    data.setdefault("image_width", first_w)
    data.setdefault("image_height", first_h)
    data, warnings = finalize(data, network_type)

    return RecognitionResult(
        data=data,
        raw=text,
        provider=settings.llm_provider,
        model=settings.llm_model,
        elapsed=time.time() - started,
        warnings=warnings,
    )


def _run_command(
    settings: Settings,
    job_dir: Path,
    network_type: str,
    system_prompt: str,
    user_prompt: str,
    images: list[Path],
) -> tuple[dict, str]:
    """Внешняя команда распознавания. Ожидается, что она создаст model.json."""
    env = dict(os.environ)
    env.update(
        {
            "NS_JOB_DIR": str(job_dir),
            "NS_NETWORK_TYPE": network_type,
            "NS_PROMPT_FILE": str(job_dir / "prompt_system.txt"),
            "NS_IMAGES": ";".join(str(p) for p in images),
        }
    )
    model_path = job_dir / "model.json"
    if model_path.exists():
        model_path.unlink()
    proc = subprocess.run(
        settings.llm_command,
        shell=True,
        cwd=str(job_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=settings.llm_timeout * 3,
        env=env,
    )
    if not model_path.exists():
        raise RecognitionError(
            "внешняя команда не создала model.json.\n"
            f"код {proc.returncode}\nstdout: {proc.stdout[-1000:]}\nstderr: {proc.stderr[-1000:]}"
        )
    raw = model_path.read_text(encoding="utf-8")
    return json.loads(raw), raw
