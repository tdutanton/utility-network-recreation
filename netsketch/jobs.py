"""Очередь задач, хранилище статусов и папки результатов.

Задача = папка data/jobs/<id>/:
    job.json          статус и метаданные
    input/            загруженные эскизы
    model.json        семантическая модель (после распознавания)
    output/           dwg, pdf, png, dxf
    prompt_*.txt      промпты (для режима ожидания агента)
"""

from __future__ import annotations

import json
import queue
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

STATUSES = {
    "queued": "В очереди",
    "recognizing": "Распознавание эскиза",
    "drafting": "Построение чертежа",
    "waiting_agent": "Ожидает распознавания",
    "done": "Готово",
    "error": "Ошибка",
    "canceled": "Отменено",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    network_type: str = "gas"
    sheet: str = "A3"
    orientation: str = "landscape"
    project: str = ""
    address: str = ""
    drawing_name: str = ""
    organization: str = ""
    developer: str = ""
    checker: str = ""
    scale: int | None = None
    status: str = "queued"
    stage: str = ""
    progress: int = 0
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    created: str = field(default_factory=now_iso)
    updated: str = field(default_factory=now_iso)
    mm_per_px: float | None = None
    final_scale: int | None = None
    specs: dict[str, Any] = field(default_factory=dict)
    inputs: list[str] = field(default_factory=list)

    def public(self) -> dict:
        data = self.__dict__.copy()
        data["status_label"] = STATUSES.get(self.status, self.status)
        return data


class JobStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def job_dir(self, job_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_\-]{4,64}", job_id or ""):
            raise ValueError("некорректный id задачи")
        return self.root / job_id

    def new_id(self) -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]

    def create(self, job: Job) -> Job:
        with self._lock:
            d = self.job_dir(job.id)
            (d / "input").mkdir(parents=True, exist_ok=True)
            (d / "output").mkdir(parents=True, exist_ok=True)
            self.save(job)
        return job

    def save(self, job: Job) -> None:
        with self._lock:
            job.updated = now_iso()
            d = self.job_dir(job.id)
            d.mkdir(parents=True, exist_ok=True)
            (d / "job.json").write_text(
                json.dumps(job.public(), ensure_ascii=False, indent=2), encoding="utf-8"
            )

    def load(self, job_id: str) -> Job:
        payload = json.loads((self.job_dir(job_id) / "job.json").read_text(encoding="utf-8"))
        payload.pop("status_label", None)
        known = set(Job.__dataclass_fields__)
        return Job(**{k: v for k, v in payload.items() if k in known})

    def get(self, job_id: str) -> Job | None:
        try:
            return self.load(job_id)
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def list(self, limit: int = 50) -> list[Job]:
        jobs: list[Job] = []
        for d in sorted(self.root.iterdir(), reverse=True) if self.root.exists() else []:
            if not d.is_dir():
                continue
            job = self.get(d.name)
            if job:
                jobs.append(job)
            if len(jobs) >= limit:
                break
        return jobs

    def log(self, job: Job, message: str) -> None:
        job.log.append(f"{datetime.now().strftime('%H:%M:%S')} {message}")
        job.log = job.log[-200:]
        self.save(job)

    def cleanup(self, keep: int = 200) -> None:
        dirs = [d for d in sorted(self.root.iterdir(), reverse=True) if d.is_dir()]
        for d in dirs[keep:]:
            shutil.rmtree(d, ignore_errors=True)


class Worker:
    """Один фоновый поток: тяжёлые CAD-операции не должны идти параллельно."""

    def __init__(self, handler: Callable[[str], None]):
        self.handler = handler
        self.queue: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self.current: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="netsketch-worker", daemon=True)
        self._thread.start()

    def submit(self, job_id: str) -> None:
        self.queue.put(job_id)

    def _loop(self) -> None:
        while True:
            job_id = self.queue.get()
            self.current = job_id
            try:
                self.handler(job_id)
            except Exception:  # noqa: BLE001 — ошибка задачи не должна убивать воркер
                pass
            finally:
                self.current = None
                self.queue.task_done()
                time.sleep(0.2)
