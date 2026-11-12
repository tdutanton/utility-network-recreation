"""Пайплайн: эскиз → модель → чертёж → проверка."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from .build import build_drawings
from .config import Settings
from .jobs import Job, JobStore
from .model import Model, model_from_dict
from .qa import check_build
from .recognize import RecognitionError, RecognitionUnavailable, pdf_to_image, recognize

log = logging.getLogger(__name__)

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".pdf", ".webp", ".bmp", ".tif", ".tiff"}


class Pipeline:
    def __init__(self, settings: Settings, store: JobStore):
        self.settings = settings
        self.store = store

    # ------------------------------------------------------------------
    def process(self, job_id: str) -> None:
        job = self.store.load(job_id)
        if job.status == "canceled":
            return
        try:
            self._run(job)
        except RecognitionUnavailable as exc:
            job.status = "waiting_agent"
            job.stage = "Нужно распознавание"
            job.progress = 15
            job.warnings.append(str(exc))
            self.store.log(job, f"распознавание недоступно: {exc}")
            self.store.save(job)
        except RecognitionError as exc:
            job.status = "error"
            job.error = str(exc)
            job.stage = "Ошибка распознавания"
            self.store.log(job, f"ошибка распознавания: {exc}")
            self.store.save(job)
        except Exception as exc:  # noqa: BLE001
            log.exception("job %s failed", job_id)
            job.status = "error"
            job.error = f"{type(exc).__name__}: {exc}"
            job.stage = "Ошибка"
            self.store.log(job, f"ошибка: {job.error}")
            self.store.save(job)

    # ------------------------------------------------------------------
    def _run(self, job: Job) -> None:
        job_dir = self.store.job_dir(job.id)
        images = [job_dir / "input" / name for name in job.inputs]
        images = [p for p in images if p.exists()]
        if not images:
            raise RecognitionError("в задаче нет входных файлов")

        job.status = "recognizing"
        job.stage = "Подготовка скана"
        job.progress = 5
        self.store.log(job, "подготовка изображения")
        self.store.save(job)

        prepared: list[Path] = []
        for i, path in enumerate(images):
            if path.suffix.lower() == ".pdf":
                out = job_dir / "input" / f"page_{i + 1}.png"
                try:
                    pdf_to_image(path, out)
                    prepared.append(out)
                    self.store.log(job, f"PDF → PNG: {path.name}")
                except Exception as exc:  # noqa: BLE001
                    raise RecognitionError(f"не удалось прочитать PDF {path.name}: {exc}") from exc
            else:
                prepared.append(path)

        model_path = job_dir / "model.json"
        model: Model | None = None

        if model_path.exists() and job.status != "waiting_agent":
            try:
                payload = json.loads(model_path.read_text(encoding="utf-8-sig"))
                model, warns = model_from_dict(payload)
                job.warnings.extend(warns)
                self.store.log(job, "использую готовую model.json")
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                self.store.log(job, f"model.json не прочитан: {exc}")

        if model is None:
            job.stage = "Распознавание эскиза"
            job.progress = 20
            self.store.save(job)
            label = self.settings.network_types.get(job.network_type, {}).get("label", job.network_type)
            result = recognize(
                settings=self.settings,
                job_dir=job_dir,
                images=prepared,
                network_type=job.network_type,
                network_label=label,
                sheet=job.sheet,
                project=job.project,
                address=job.address,
            )
            payload = dict(result.data)
            payload.setdefault("sheet", job.sheet)
            payload.setdefault("orientation", job.orientation)
            title = payload.setdefault("title", {})
            if isinstance(title, dict):
                title.setdefault("project", job.project)
                title.setdefault("address", job.address)
                if job.drawing_name:
                    title.setdefault("drawing_name", job.drawing_name)
                if job.organization:
                    title.setdefault("organization", job.organization)
                if job.developer:
                    title.setdefault("developer", job.developer)
                if job.checker:
                    title.setdefault("checker", job.checker)
            model_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            model, warns = model_from_dict(payload)
            job.warnings.extend(warns)
            job.mm_per_px = model.mm_per_px
            self.store.log(job, f"распознано моделью {result.provider}/{result.model} за {result.elapsed:.1f} с")
            job.specs = {
                "provider": result.provider,
                "model": result.model,
                "elapsed": round(result.elapsed, 1),
            }

        self._draft(job, model, job_dir)

    # ------------------------------------------------------------------
    def _draft(self, job: Job, model: Model, job_dir: Path) -> None:
        job.status = "drafting"
        job.stage = "Построение чертежа"
        job.progress = 60
        self.store.log(job, f"сегментов: {len(model.segments)}, элементов: {len(model.elements)}")
        self.store.save(job)

        title = {
            "project": job.project or model.title.project,
            "address": job.address or model.title.address,
            "drawing_name": job.drawing_name
            or model.title.drawing_name
            or self.settings.network_types.get(job.network_type, {}).get("default_drawing", "Схема сети"),
            "stage": job.scale or model.title.stage or "Р",
            "sheet": model.title.sheet or "1",
            "total": model.title.total or "1",
            "organization": job.organization or model.title.organization,
            "developer": job.developer or model.title.developer,
            "checker": job.checker or model.title.checker,
            "doc_code": model.title.doc_code,
        }
        title["stage"] = model.title.stage or "Р"

        stem = f"{job.network_type}_{job.id}"
        outdir = job_dir / "output"
        result = build_drawings(
            model,
            outdir,
            stem=stem,
            title=title,
            sheet=None,
            scale=job.scale,
            ocs_exe=self.settings.ocs_exe,
            dwg_version=self.settings.dwg_version,
        )

        job.final_scale = result.info.scale
        job.assumptions = list(dict.fromkeys(model.assumptions + result.info.assumed))

        errors, warnings = check_build(model, result.files, result.info, result.sheet)
        job.warnings.extend(warnings)
        job.files = {k: v for k, v in result.files.items()}
        job.files["model"] = str(job_dir / "model.json")
        job.files["preview"] = job.files.get("png", "")

        # превью исходника рядом с результатом — удобно сравнивать
        input_png = job_dir / "input" / "page_1.png"
        if not input_png.exists():
            first = job_dir / "input" / (job.inputs[0] if job.inputs else "")
            if first.exists() and first.suffix.lower() != ".pdf":
                try:
                    shutil.copyfile(first, job_dir / "input" / "source.png")
                except OSError:
                    pass

        if errors:
            job.status = "error"
            job.error = "; ".join(errors)
            job.stage = "Ошибка построения"
            job.progress = 90
        else:
            job.status = "done"
            job.stage = "Готово"
            job.progress = 100
        self.store.log(job, "чертёж собран: " + ", ".join(sorted(job.files)))
        self.store.save(job)

    # ------------------------------------------------------------------
    def submit_model(self, job_id: str, payload: dict) -> Job:
        """Ручная/агентская модель: сразу в построение."""
        job = self.store.load(job_id)
        job_dir = self.store.job_dir(job_id)
        (job_dir / "model.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        job.status = "queued"
        job.stage = "Модель получена"
        job.error = ""
        job.warnings = []
        self.store.save(job)
        return job
