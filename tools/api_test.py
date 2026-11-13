"""Проверка HTTP API без браузера: создать задачу, дождаться, скачать файлы.

    python tools/api_test.py [http://127.0.0.1:8770]
"""

from __future__ import annotations

import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def call(base: str, path: str, payload: dict | None = None, timeout: int = 30) -> dict:
    url = base.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch(base: str, path: str) -> bytes:
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=30) as resp:
        return resp.read()


def wait_for(base: str, job_id: str, statuses: set[str], limit: float = 180.0) -> dict:
    started = time.time()
    while time.time() - started < limit:
        job = call(base, f"/api/jobs/{job_id}")["job"]
        print(f"   … {job['status']:<14} {job['stage']} ({job['progress']}%)")
        if job["status"] in statuses:
            return job
        time.sleep(2)
    raise TimeoutError(f"задача не дошла до {statuses}")


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8770"
    print(f"API: {base}")

    health = call(base, "/api/health")
    print(f"  здоровье:    ok={health['ok']} llm={health['llm_ready']} ocs={'да' if health['ocs'] else 'нет'}")
    options = call(base, "/api/options")
    print(f"  типы сетей:  {[n['id'] for n in options['network_types']]}")
    print(f"  форматы:     {options['sheets']}")

    image = ROOT / "examples" / "gas" / "1" / "input" / "02_кв1_5.jpg"
    payload = {
        "network_type": "gas",
        "sheet": "A3",
        "orientation": "landscape",
        "project": "Проверка API — газоснабжение",
        "address": "г. Москва, ул. Тестовая, 1",
        "organization": "ООО «Тест»",
        "developer": "Скрипт",
        "checker": "Проверка",
        "files": [{"name": image.name, "data": base64.b64encode(image.read_bytes()).decode("ascii")}],
    }
    job = call(base, "/api/jobs", payload)["job"]
    print(f"  задача:      {job['id']}")

    if health["llm_ready"]:
        job = wait_for(base, job["id"], {"done", "error"})
    else:
        job = wait_for(base, job["id"], {"waiting_agent", "error"})
        if job["status"] == "waiting_agent":
            print("  распознавание не настроено → отправляю model.json вручную")
            model = json.loads((ROOT / "examples/gas/1/models/2_кв1_5.json").read_text(encoding="utf-8-sig"))
            call(base, f"/api/jobs/{job['id']}/model", model)
            job = wait_for(base, job["id"], {"done", "error"})

    if job["status"] != "done":
        print(f"  ОШИБКА: {job['error']}")
        return 1

    print(f"  масштаб:     1:{job.get('final_scale')}")
    for kind in ("dwg", "pdf", "png", "dxf"):
        if job["files"].get(kind):
            blob = fetch(base, f"/api/jobs/{job['id']}/file/{kind}")
            print(f"  {kind}: {len(blob):>8} байт")
    if job.get("warnings"):
        print("  предупреждения:")
        for w in job["warnings"]:
            print("   -", w)

    # страница интерфейса
    html = fetch(base, "/").decode("utf-8", "replace")
    assert "NetSketch" in html, "интерфейс не отдаётся"
    print("  интерфейс:   ok")

    print("\nAPI: всё хорошо")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

