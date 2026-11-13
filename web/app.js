/* NetSketch — клиент. Без сборки: обычный ES-модуль на странице. */
(() => {
  "use strict";

  const state = {
    network: "gas",
    networkDefaults: {},
    sheet: "A4",
    orientation: "portrait",
    scale: 0,
    files: [],
    jobId: null,
    pollTimer: null,
    busy: false,
  };

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const el = {
    netGrid: $("#net-grid"),
    sheetSeg: $("#sheet-seg"),
    orientSeg: $("#orient-seg"),
    scaleSelect: $("#scale-select"),
    dropzone: $("#dropzone"),
    fileInput: $("#file-input"),
    fileList: $("#file-list"),
    form: $("#wizard"),
    submitBtn: $("#submit-btn"),
    pillLlm: $("#pill-llm"),
    pillOcs: $("#pill-ocs"),
    empty: $("#empty-state"),
    progress: $("#progress-panel"),
    progressTitle: $("#progress-title"),
    progressSub: $("#progress-sub"),
    bar: $("#bar-fill"),
    log: $("#log"),
    done: $("#done-panel"),
    doneSub: $("#done-sub"),
    doneScale: $("#done-scale"),
    previewImg: $("#preview-img"),
    previewLink: $("#preview-link"),
    downloads: $("#downloads"),
    warnings: $("#warnings"),
    warningsList: $("#warnings-list"),
    wait: $("#wait-panel"),
    waitText: $("#wait-text"),
    promptLink: $("#prompt-link"),
    modelJson: $("#model-json"),
    sendModel: $("#send-model"),
    error: $("#error-panel"),
    errorText: $("#error-text"),
    retry: $("#retry-btn"),
    newJob: $("#new-job"),
    history: $("#history-list"),
    refreshHistory: $("#refresh-history"),
  };

  const NETWORK_ICONS = {
    gas: "M4 18h16M7 18V9l5-4 5 4v9M10 18v-4h4v4",
    heat: "M6 16c0-4 4-4 4-8M14 16c0-4 4-4 4-8M4 20h16",
  };

  const STATUS_LABEL = {
    queued: "В очереди",
    recognizing: "Распознавание эскиза",
    drafting: "Построение чертежа",
    waiting_agent: "Нужно распознавание",
    done: "Готово",
    error: "Ошибка",
    canceled: "Отменено",
  };

  const FILE_LABEL = { dwg: "DWG", pdf: "PDF", png: "PNG", dxf: "DXF" };

  // ---------------------------------------------------------------- utils
  function fmtSize(bytes) {
    if (bytes < 1024) return bytes + " Б";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " КБ";
    return (bytes / 1024 / 1024).toFixed(1) + " МБ";
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    return data;
  }

  // ---------------------------------------------------------------- init
  async function init() {
    renderSheets();
    bindEvents();
    await Promise.all([loadOptions(), loadHealth(), loadHistory()]);
  }

  async function loadOptions() {
    try {
      const data = await api("/api/options");
      state.networkDefaults = {};
      (data.network_types || []).forEach((t) => {
        state.networkDefaults[t.id] = { sheet: t.sheet, orientation: t.orientation };
      });
      renderNetworks(data.network_types);
      state.network = data.defaults?.network_type || "gas";
      applyNetworkDefaults(state.network);
      markNetwork(state.network);
      if (data.llm_ready) {
        el.pillLlm.textContent = `Распознавание: ${data.llm_model || data.llm_provider}`;
        el.pillLlm.className = "pill ok";
      } else {
        el.pillLlm.textContent = "Распознавание не настроено";
        el.pillLlm.className = "pill warn";
        el.pillLlm.title = "Добавьте ключ в .env или включите ручной режим model.json";
      }
    } catch (err) {
      el.pillLlm.textContent = "Сервер недоступен";
      el.pillLlm.className = "pill bad";
    }
  }

  async function loadHealth() {
    try {
      const data = await api("/api/health");
      if (data.ocs) {
        el.pillOcs.textContent = "Open CAD Studio";
        el.pillOcs.className = "pill ok";
        el.pillOcs.title = data.ocs;
      } else {
        el.pillOcs.textContent = "CAD не найден";
        el.pillOcs.className = "pill bad";
        el.pillOcs.title = "Open CAD Studio не найден — DWG не будет создан";
      }
    } catch (err) {
      el.pillOcs.textContent = "CAD: нет связи";
      el.pillOcs.className = "pill bad";
    }
  }

  function renderNetworks(types) {
    el.netGrid.innerHTML = "";
    (types || []).forEach((t) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "net-card";
      btn.dataset.id = t.id;
      const icon = NETWORK_ICONS[t.id] || NETWORK_ICONS.gas;
      btn.innerHTML = `
        <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">
          <path d="${icon}" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <strong>${escapeHtml(t.label)}</strong>
        <span>${escapeHtml(t.discipline || "")}</span>`;
      btn.addEventListener("click", () => {
        state.network = t.id;
        markNetwork(t.id);
        applyNetworkDefaults(t.id);
      });
      el.netGrid.appendChild(btn);
    });
  }

  function applyNetworkDefaults(id) {
    const preset = state.networkDefaults[id];
    if (!preset) return;
    if (preset.sheet) setSheet(preset.sheet);
    if (preset.orientation) setOrientation(preset.orientation);
  }

  function setOrientation(value) {
    state.orientation = value;
    $$("#orient-seg button").forEach((b) => b.classList.toggle("active", b.dataset.value === value));
  }

  function markNetwork(id) {
    $$(".net-card").forEach((c) => c.classList.toggle("active", c.dataset.id === id));
  }

  function renderSheets() {
    const formats = ["A4", "A3", "A2", "A1"];
    el.sheetSeg.innerHTML = "";
    formats.forEach((f) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = f;
      b.dataset.value = f;
      b.addEventListener("click", () => setSheet(f));
      el.sheetSeg.appendChild(b);
    });
    setSheet(state.sheet);
  }

  function setSheet(value) {
    state.sheet = value;
    $$("#sheet-seg button").forEach((b) => b.classList.toggle("active", b.dataset.value === value));
  }

  // ---------------------------------------------------------------- files
  function bindEvents() {
    el.dropzone.addEventListener("click", () => el.fileInput.click());
    el.fileInput.addEventListener("change", (e) => addFiles(Array.from(e.target.files || [])));

    ["dragenter", "dragover"].forEach((ev) =>
      el.dropzone.addEventListener(ev, (e) => {
        e.preventDefault();
        el.dropzone.classList.add("drag");
      })
    );
    ["dragleave", "drop"].forEach((ev) =>
      el.dropzone.addEventListener(ev, (e) => {
        e.preventDefault();
        el.dropzone.classList.remove("drag");
      })
    );
    el.dropzone.addEventListener("drop", (e) => {
      const files = Array.from(e.dataTransfer?.files || []);
      addFiles(files);
    });

    el.orientSeg.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      setOrientation(btn.dataset.value);
    });

    el.scaleSelect.addEventListener("change", () => {
      state.scale = Number(el.scaleSelect.value) || 0;
    });

    el.form.addEventListener("submit", (e) => {
      e.preventDefault();
      submitJob();
    });

    el.sendModel.addEventListener("click", sendManualModel);
    el.retry.addEventListener("click", () => {
      if (state.jobId) retryJob(state.jobId);
    });
    el.newJob.addEventListener("click", resetToForm);
    el.refreshHistory.addEventListener("click", loadHistory);

    ["project", "address"].forEach((id) => {
      document.getElementById(id)?.addEventListener("input", (e) => e.target.classList.remove("invalid"));
    });
  }

  function addFiles(files) {
    const allowed = /\.(jpe?g|png|pdf|webp|bmp)$/i;
    for (const file of files) {
      if (!allowed.test(file.name)) continue;
      if (state.files.length >= 5) break;
      if (file.size > 25 * 1024 * 1024) continue;
      state.files.push(file);
    }
    renderFiles();
  }

  function renderFiles() {
    el.fileList.innerHTML = "";
    state.files.forEach((file, index) => {
      const li = document.createElement("li");
      const isImage = /\.(jpe?g|png|webp|bmp)$/i.test(file.name);
      const thumb = isImage ? URL.createObjectURL(file) : "";
      li.innerHTML = `
        ${isImage ? `<img src="${thumb}" alt="" />` : `<span class="doc-icon">PDF</span>`}
        <div class="meta"><b>${escapeHtml(file.name)}</b><small>${fmtSize(file.size)}</small></div>
        <button type="button" class="remove" title="Убрать" aria-label="Убрать">×</button>`;
      li.querySelector(".remove").addEventListener("click", () => {
        state.files.splice(index, 1);
        renderFiles();
      });
      el.fileList.appendChild(li);
    });
  }

  function readAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  // ---------------------------------------------------------------- submit
  async function submitJob() {
    if (state.busy) return;
    const project = $("#project");
    const address = $("#address");
    let ok = true;
    if (!project.value.trim()) { project.classList.add("invalid"); ok = false; }
    if (!address.value.trim()) { address.classList.add("invalid"); ok = false; }
    if (!state.files.length) {
      el.dropzone.classList.add("drag");
      setTimeout(() => el.dropzone.classList.remove("drag"), 1200);
      ok = false;
    }
    if (!ok) return;

    state.busy = true;
    el.submitBtn.disabled = true;
    el.submitBtn.textContent = "Отправка…";

    try {
      const files = [];
      for (const file of state.files) {
        files.push({ name: file.name, data: await readAsBase64(file) });
      }
      const payload = {
        network_type: state.network,
        sheet: state.sheet,
        orientation: state.orientation,
        scale: state.scale || null,
        project: project.value.trim(),
        address: address.value.trim(),
        drawing_name: $("#drawing_name").value.trim(),
        organization: $("#organization").value.trim(),
        developer: $("#developer").value.trim(),
        checker: $("#checker").value.trim(),
        files,
      };
      const data = await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
      state.jobId = data.job.id;
      showPanel("progress");
      renderJob(data.job);
      startPolling();
      loadHistory();
    } catch (err) {
      showPanel("error");
      el.errorText.textContent = err.message;
    } finally {
      state.busy = false;
      el.submitBtn.disabled = false;
      el.submitBtn.textContent = "Создать чертёж";
    }
  }

  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(async () => {
      if (!state.jobId) return;
      try {
        const data = await api(`/api/jobs/${state.jobId}`);
        renderJob(data.job);
        if (["done", "error", "waiting_agent"].includes(data.job.status)) {
          stopPolling();
          loadHistory();
        }
      } catch (err) {
        stopPolling();
      }
    }, 1500);
  }

  function stopPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = null;
  }

  // ---------------------------------------------------------------- render job
  function showPanel(name) {
    el.empty.hidden = name !== "empty";
    el.progress.hidden = name !== "progress";
    el.done.hidden = name !== "done";
    el.wait.hidden = name !== "wait";
    el.error.hidden = name !== "error";
  }

  function renderJob(job) {
    if (!job) return;
    if (job.status === "done") return renderDone(job);
    if (job.status === "error") return renderError(job);
    if (job.status === "waiting_agent") return renderWait(job);
    return renderProgress(job);
  }

  function renderProgress(job) {
    showPanel("progress");
    el.progressTitle.textContent = STATUS_LABEL[job.status] || job.stage || "Работа";
    el.progressSub.textContent = job.stage || "";
    el.bar.style.width = `${Math.max(4, job.progress || 4)}%`;
    el.log.innerHTML = (job.log || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("");
    el.log.scrollTop = el.log.scrollHeight;
  }

  function renderDone(job) {
    showPanel("done");
    const kinds = ["dwg", "pdf", "png", "dxf"];
    el.doneSub.textContent = `${job.project || "Чертёж"} · ${job.sheet}`;
    el.doneScale.textContent = job.final_scale ? `1:${job.final_scale}` : "";

    const preview = job.files?.png;
    if (preview) {
      const url = `/api/jobs/${job.id}/file/png?v=${Date.now()}`;
      el.previewImg.src = url;
      el.previewLink.href = url;
    } else {
      el.previewImg.removeAttribute("src");
    }

    el.downloads.innerHTML = "";
    kinds.forEach((kind) => {
      if (!job.files?.[kind]) return;
      const a = document.createElement("a");
      a.href = `/api/jobs/${job.id}/file/${kind}`;
      a.innerHTML = `<b>${FILE_LABEL[kind]}</b> Скачать`;
      a.setAttribute("download", "");
      el.downloads.appendChild(a);
    });

    const warns = (job.warnings || []).filter(Boolean);
    if (warns.length) {
      el.warnings.hidden = false;
      el.warningsList.innerHTML = warns.map((w) => `<li>${escapeHtml(w)}</li>`).join("");
    } else {
      el.warnings.hidden = true;
    }
  }

  function renderError(job) {
    showPanel("error");
    el.errorText.textContent = job.error || "неизвестная ошибка";
  }

  function renderWait(job) {
    showPanel("wait");
    el.waitText.textContent =
      (job.warnings && job.warnings[job.warnings.length - 1]) ||
      "Модуль распознавания не настроен. Скачайте задание, разберите эскиз и вставьте model.json.";
    el.promptLink.href = `/api/jobs/${job.id}/prompt`;
  }

  async function sendManualModel() {
    const raw = el.modelJson.value.trim();
    if (!raw) return;
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (err) {
      el.modelJson.classList.add("invalid");
      return;
    }
    el.modelJson.classList.remove("invalid");
    try {
      await api(`/api/jobs/${state.jobId}/model`, { method: "POST", body: JSON.stringify(parsed) });
      showPanel("progress");
      el.progressTitle.textContent = "Построение чертежа";
      el.bar.style.width = "60%";
      startPolling();
    } catch (err) {
      showPanel("error");
      el.errorText.textContent = err.message;
    }
  }

  async function retryJob(jobId) {
    try {
      await api(`/api/jobs/${jobId}/retry`, { method: "POST" });
      showPanel("progress");
      state.jobId = jobId;
      startPolling();
    } catch (err) {
      el.errorText.textContent = err.message;
    }
  }

  function resetToForm() {
    stopPolling();
    state.jobId = null;
    showPanel("empty");
    el.form.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---------------------------------------------------------------- history
  async function loadHistory() {
    try {
      const data = await api("/api/jobs");
      const jobs = data.jobs || [];
      if (!jobs.length) {
        el.history.innerHTML = '<li class="muted">Пока пусто</li>';
        return;
      }
      el.history.innerHTML = "";
      jobs.forEach((job) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "history-item";
        btn.innerHTML = `
          <span class="dot ${job.status}"></span>
          <span style="flex:1;min-width:0">
            <b>${escapeHtml(job.project || "Без названия")}</b>
            <small>${escapeHtml(job.sheet)} · ${escapeHtml(job.network_type)} · ${new Date(job.created).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</small>
          </span>
          <span style="font-size:11.5px;color:var(--muted)">${STATUS_LABEL[job.status] || job.status}</span>`;
        btn.addEventListener("click", () => {
          state.jobId = job.id;
          renderJob(job);
          if (!["done", "error", "waiting_agent"].includes(job.status)) startPolling();
        });
        li.appendChild(btn);
        el.history.appendChild(li);
      });
    } catch (err) {
      el.history.innerHTML = '<li class="muted">не удалось загрузить</li>';
    }
  }

  init();
})();
