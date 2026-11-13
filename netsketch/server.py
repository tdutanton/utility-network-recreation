"""HTTP-сервер приложения: API + статический интерфейс.

Без внешних зависимостей — ThreadingHTTPServer из стандартной библиотеки.
Модели работают «за кулисами»: пользователь видит только форму и результат.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
import threading
import traceback
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__
from .config import Settings, load_settings
from .jobs import STATUSES, Job, JobStore, Worker
from .pipeline import Pipeline
from .recognize import RecognitionUnavailable

log = logging.getLogger(__name__)

MIME = {
    ".dwg": "application/acad",
    ".dxf": "application/dxf",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".json": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


class App:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = JobStore(settings.jobs_dir)
        self.pipeline = Pipeline(settings, self.store)
        self.worker = Worker(self.pipeline.process)
        self.worker.start()
        self.store.cleanup(settings.keep_jobs)

    def submit(self, job_id: str) -> None:
        self.worker.submit(job_id)


def _safe_name(name: str) -> str:
    name = Path(name or "input").name
    name = re.sub(r"[^\w\-. ]+", "_", name, flags=re.UNICODE).strip() or "input"
    return name[:120]


class Handler(BaseHTTPRequestHandler):
    server_version = f"NetSketch/{__version__}"
    app: App = None  # type: ignore[assignment]

    # ------------------------------------------------------------------
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        log.debug("%s - %s", self.address_string(), fmt % args)

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": message})

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > self.app.settings.max_upload_mb * 1024 * 1024 * 2:
            raise ValueError("слишком большой запрос")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    # ------------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path in {"/", "/index.html"}:
                return self._serve_static("index.html")
            if path.startswith("/static/"):
                return self._serve_static(path[len("/static/") :])
            if path == "/api/health":
                return self._health()
            if path == "/api/options":
                return self._options()
            if path == "/api/jobs":
                return self._json(200, {"ok": True, "jobs": [j.public() for j in self.app.store.list(30)]})
            m = re.fullmatch(r"/api/jobs/([A-Za-z0-9_\-]+)", path)
            if m:
                job = self.app.store.get(m.group(1))
                if not job:
                    return self._error(404, "задача не найдена")
                return self._json(200, {"ok": True, "job": job.public()})
            m = re.fullmatch(r"/api/jobs/([A-Za-z0-9_\-]+)/file/([a-z_]+)", path)
            if m:
                return self._download(m.group(1), m.group(2))
            m = re.fullmatch(r"/api/jobs/([A-Za-z0-9_\-]+)/prompt", path)
            if m:
                return self._prompt(m.group(1))
            return self._error(404, "не найдено")
        except BrokenPipeError:
            return
        except Exception as exc:  # noqa: BLE001
            log.error("GET %s: %s\n%s", path, exc, traceback.format_exc())
            return self._error(500, f"{type(exc).__name__}: {exc}")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/jobs":
                return self._create_job()
            m = re.fullmatch(r"/api/jobs/([A-Za-z0-9_\-]+)/model", path)
            if m:
                return self._submit_model(m.group(1))
            m = re.fullmatch(r"/api/jobs/([A-Za-z0-9_\-]+)/retry", path)
            if m:
                job = self.app.store.get(m.group(1))
                if not job:
                    return self._error(404, "задача не найдена")
                job.status = "queued"
                job.error = ""
                job.stage = "Повторная попытка"
                job.progress = 0
                self.app.store.save(job)
                self.app.submit(job.id)
                return self._json(200, {"ok": True, "job": job.public()})
            return self._error(404, "не найдено")
        except BrokenPipeError:
            return
        except Exception as exc:  # noqa: BLE001
            log.error("POST %s: %s\n%s", path, exc, traceback.format_exc())
            return self._error(500, f"{type(exc).__name__}: {exc}")

    def do_DELETE(self) -> None:  # noqa: N802
        m = re.fullmatch(r"/api/jobs/([A-Za-z0-9_\-]+)", urllib.parse.urlparse(self.path).path)
        if not m:
            return self._error(404, "не найдено")
        import shutil

        job = self.app.store.get(m.group(1))
        if not job:
            return self._error(404, "задача не найдена")
        shutil.rmtree(self.app.store.job_dir(job.id), ignore_errors=True)
        return self._json(200, {"ok": True})

    # ------------------------------------------------------------------
    def _serve_static(self, rel: str) -> None:
        rel = urllib.parse.unquote(rel)
        base = self.app.settings.web_dir.resolve()
        target = (base / rel).resolve()
        if base not in target.parents and target != base:
            return self._error(403, "доступ запрещён")
        if not target.is_file():
            return self._error(404, "файл не найден")
        ctype = MIME.get(target.suffix.lower()) or mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("charset=utf-8"):
            ctype = ctype.split(";")[0] + "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    def _health(self) -> None:
        s = self.app.settings
        self._json(
            200,
            {
                "ok": True,
                "version": __version__,
                "llm_ready": s.llm_ready,
                "llm_provider": s.llm_provider,
                "llm_model": s.llm_model,
                "ocs": s.ocs_exe,
                "dwg_version": s.dwg_version,
                "worker_busy": self.app.worker.current is not None,
                "queue": self.app.worker.queue.qsize(),
            },
        )

    def _options(self) -> None:
        s = self.app.settings
        self._json(
            200,
            {
                "ok": True,
                "network_types": [
                    {
                        "id": key,
                        "label": val.get("label", key),
                        "discipline": val.get("discipline", ""),
                        "sheet": val.get("default_sheet", s.default_sheet),
                        "orientation": val.get("default_orientation", s.default_orientation),
                    }
                    for key, val in s.network_types.items()
                ],
                "sheets": ["A4", "A3", "A2", "A1"],
                "defaults": {
                    "network_type": "gas",
                    "sheet": s.default_sheet,
                    "scale": 0,
                    "orientation": s.default_orientation,
                },
                "llm_ready": s.llm_ready,
                "llm_provider": s.llm_provider,
                "llm_model": s.llm_model,
            },
        )

    def _create_job(self) -> None:
        payload = self._read_json()
        network_type = str(payload.get("network_type") or "gas")
        if network_type not in self.app.settings.network_types:
            return self._error(400, f"неизвестный тип сети: {network_type}")
        sheet = str(payload.get("sheet") or self.app.settings.default_sheet).upper().replace("А", "A")
        if sheet not in {"A4", "A3", "A2", "A1", "A0"}:
            return self._error(400, "неизвестный формат листа")
        files = payload.get("files") or []
        if not files:
            return self._error(400, "не приложен эскиз")

        job = Job(
            id=self.app.store.new_id(),
            network_type=network_type,
            sheet=sheet,
            orientation=str(payload.get("orientation") or self.app.settings.default_orientation),
            project=str(payload.get("project") or "")[:200],
            address=str(payload.get("address") or "")[:300],
            drawing_name=str(payload.get("drawing_name") or "")[:200],
            organization=str(payload.get("organization") or "")[:200],
            developer=str(payload.get("developer") or "")[:100],
            checker=str(payload.get("checker") or "")[:100],
            status="queued",
            stage="В очереди",
        )
        scale = payload.get("scale")
        if scale:
            try:
                job.scale = int(scale)
            except (TypeError, ValueError):
                job.scale = None

        self.app.store.create(job)
        saved: list[str] = []
        for index, item in enumerate(files[:5]):
            name = _safe_name(item.get("name") or f"sketch_{index + 1}.png")
            data = item.get("data") or ""
            if "," in data[:100] and data.strip().startswith("data:"):
                data = data.split(",", 1)[1]
            try:
                blob = base64.b64decode(data, validate=False)
            except Exception:  # noqa: BLE001
                return self._error(400, "файл повреждён при передаче")
            if len(blob) > self.app.settings.max_upload_mb * 1024 * 1024:
                return self._error(413, "файл слишком большой")
            suffix = Path(name).suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".pdf", ".webp", ".bmp"}:
                return self._error(400, f"неподдерживаемый формат: {suffix or 'без расширения'}")
            target = self.app.store.job_dir(job.id) / "input" / name
            target.write_bytes(blob)
            saved.append(name)
        job.inputs = saved
        self.app.store.save(job)
        self.app.store.log(job, f"задача создана, файлов: {len(saved)}")
        self.app.submit(job.id)
        return self._json(201, {"ok": True, "job": job.public()})

    def _submit_model(self, job_id: str) -> None:
        payload = self._read_json()
        model = payload.get("model") if isinstance(payload.get("model"), dict) else payload
        if not isinstance(model, dict):
            return self._error(400, "ожидается JSON-объект модели")
        if "segments" not in model and "elements" not in model:
            return self._error(400, "в модели нет segments/elements")
        try:
            job = self.app.pipeline.submit_model(job_id, model)
        except FileNotFoundError:
            return self._error(404, "задача не найдена")
        self.app.submit(job.id)
        return self._json(200, {"ok": True, "job": job.public()})

    def _download(self, job_id: str, kind: str) -> None:
        job = self.app.store.get(job_id)
        if not job:
            return self._error(404, "задача не найдена")
        path = job.files.get(kind)
        if not path:
            return self._error(404, f"файл «{kind}» ещё не готов")
        target = Path(path)
        if not target.is_file():
            return self._error(404, "файл не найден на диске")
        ctype = MIME.get(target.suffix.lower()) or "application/octet-stream"
        encoded = urllib.parse.quote(target.name)
        self._send(
            200,
            target.read_bytes(),
            ctype,
            {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
        )

    def _prompt(self, job_id: str) -> None:
        job = self.app.store.get(job_id)
        if not job:
            return self._error(404, "задача не найдена")
        job_dir = self.app.store.job_dir(job_id)
        system_prompt = job_dir / "prompt_system.txt"
        user_prompt = job_dir / "prompt_user.txt"
        if not system_prompt.exists():
            return self._error(404, "промпт ещё не сформирован — дождитесь этапа распознавания")
        text = (
            "# Задание на распознавание эскиза\n\n"
            f"Задача: {job.id}\nТип сети: {job.network_type}\nЛист: {job.sheet}\n"
            f"Проект: {job.project}\nАдрес: {job.address}\n\n"
            "## Системная инструкция\n\n"
            + system_prompt.read_text(encoding="utf-8")
            + "\n\n## Сообщение пользователя\n\n"
            + (user_prompt.read_text(encoding="utf-8") if user_prompt.exists() else "")
        )
        self._send(200, text.encode("utf-8"), "text/plain; charset=utf-8")


def create_app(settings: Settings | None = None) -> App:
    settings = settings or load_settings()
    return App(settings)


def serve(settings: Settings | None = None) -> None:
    settings = settings or load_settings()
    app = create_app(settings)
    Handler.app = app

    port = settings.port
    httpd = None
    for attempt in range(12):
        try:
            httpd = ThreadingHTTPServer((settings.host, port), Handler)
            break
        except OSError:
            port += 1
    if httpd is None:
        raise SystemExit("не удалось занять порт")
    url = f"http://{settings.host}:{port}"
    print(f"NetSketch {__version__} → {url}")
    print(f"  Open CAD Studio: {settings.ocs_exe or 'НЕ НАЙДЕН'}")
    print(f"  Распознавание:   {settings.llm_provider}/{settings.llm_model or '—'}"
          f"{' (готово)' if settings.llm_ready else ' (не настроено)'}")
    try:
        if settings.open_browser:
            import webbrowser

            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nостановлено")
    finally:
        httpd.server_close()

