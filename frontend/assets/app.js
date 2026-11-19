const state = { files: [], currentUpload: null, resultId: null, activeCategory: "all", batchQueue: [], preferredRoute: null, preferredArchiveTarget: null, batchRunning: false, stopBatch: false, engineRoutes: [], hostPreviewFilename: null };

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { message = (await response.json()).detail || message; } catch (_) {}
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2600);
}

function showView(name) {
  if ([...document.querySelectorAll(".nav-item[data-view]")].some(button => button.dataset.view === name)) {
    localStorage.setItem("uc-last-view", name);
  }
  document.querySelectorAll(".content").forEach(section => section.classList.add("hidden"));
  document.getElementById("sidebar").classList.remove("open");
  const map = { dashboard: "dashboardView", converter: "converterView", zip: "converterView", history: "historyView", host: "hostView", batch: "batchView", favorites: "favoritesView", engines: "enginesView", settings: "settingsView", about: "aboutView", support: "supportView" };
  document.getElementById(map[name] || "converterView").classList.remove("hidden");
  document.querySelectorAll(".nav-item").forEach(button => button.classList.toggle("active", button.dataset.view === name));
  const activeNavItem = [...document.querySelectorAll(".nav-item[data-view]")].find(button => button.dataset.view === name);
  activeNavItem?.closest(".nav-group")?.setAttribute("open", "");
  const categoryTitles = { documents: "Documents", programming: "Programming", images: "Images", media: "Audio / Video", spreadsheets: "Spreadsheets", data: "Data", archives: "Archives" };
  if (name === "zip") {
    document.getElementById("categoryCatalog").classList.remove("hidden");
    state.activeCategory = "archives";
    state.preferredArchiveTarget = "zip";
    document.getElementById("converterTitle").textContent = "ZIP Converter";
    document.getElementById("converterView").classList.remove("hidden");
    loadCategoryCatalog("archives");
    if (state.currentUpload) loadTargets(state.currentUpload.extension);
  } else if (categoryTitles[name]) {
    document.getElementById("categoryCatalog").classList.remove("hidden");
    state.preferredArchiveTarget = null;
    state.activeCategory = name;
    document.getElementById("converterTitle").textContent = categoryTitles[name];
    document.getElementById("converterView").classList.remove("hidden");
    document.querySelectorAll(".nav-item").forEach(button => button.classList.toggle("active", button.dataset.view === name));
    loadCategoryCatalog(name);
    if (state.currentUpload) loadTargets(state.currentUpload.extension);
  } else if (name === "converter") {
    document.getElementById("categoryCatalog").classList.add("hidden");
    state.activeCategory = "all";
    state.preferredArchiveTarget = null;
    document.getElementById("converterTitle").textContent = "All Converters";
    if (state.currentUpload) loadTargets(state.currentUpload.extension);
  }
  if (name === "history") loadHistory();
  if (name === "host") loadHostedFiles();
  if (name === "batch") renderBatchQueue();
  if (name === "favorites") renderFavorites();
  if (name === "engines") loadEngines();
}

async function loadDashboard() {
  try {
    const history = await api("/api/history");
    const items = history.items;
    document.getElementById("totalCount").textContent = items.length;
    document.getElementById("successCount").textContent = items.filter(item => item.status === "success").length;
    document.getElementById("failedCount").textContent = items.filter(item => item.status === "failed").length;
    const engines = await api("/api/engines");
    document.getElementById("engineCount").textContent = engines.engines.filter(engine => engine.status === "available").length;
    document.getElementById("engineStatus").textContent = `${document.getElementById("engineCount").textContent} engines ready`;
    const recent = document.getElementById("recentActivity");
    renderCategoryOverview(items);
    if (!items.length) {
      recent.innerHTML = '<div class="empty-state">No conversions yet</div>';
    } else {
      recent.innerHTML = items.slice(0, 5).map(item => `<div class="activity-row"><div><strong>${escapeHtml(item.original_filename)}</strong><br><small>${item.source_format.toUpperCase()} to ${item.target_format.toUpperCase()}</small></div><span class="status-pill ${item.status === "failed" ? "failed" : ""}">${item.status}</span></div>`).join("");
    }
  } catch (error) { showToast(error.message); }
}

const categoryFormats = {
  documents: new Set(["pdf", "docx", "doc", "rtf", "odt", "epub", "html", "md", "txt"]),
  programming: new Set(["php", "html", "css", "js", "ts", "py", "java", "c", "cpp", "cs", "go", "rs", "sql", "xml", "yaml", "toml", "md", "sh", "ps1"]),
  images: new Set(["png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff", "ico", "avif"]),
  media: new Set(["mp3", "wav", "flac", "aac", "ogg", "m4a", "opus", "mp4", "mkv", "avi", "mov", "webm", "gif"]),
  spreadsheets: new Set(["xlsx", "csv", "tsv", "ods"]),
  data: new Set(["json", "xml", "csv", "yaml", "yml", "toml", "tsv"]),
  archives: new Set(["zip", "tar", "tar.gz", "gz", "rar"])
};
const archiveFormats = new Set(["zip", "tar", "tar.gz", "gz", "rar"]);

function categoryForFormat(format) {
  return Object.entries(categoryFormats).find(([, formats]) => formats.has(format))?.[0] || "other";
}

function renderCategoryOverview(items) {
  const categories = ["documents", "programming", "images", "media", "spreadsheets", "data", "archives"];
  const counts = categories.map(category => ({ category, count: items.filter(item => categoryForFormat(item.source_format) === category).length }));
  const max = Math.max(1, ...counts.map(item => item.count));
  document.getElementById("categoryOverview").innerHTML = counts.map(item => `<button class="category-bar" data-open-category="${item.category}"><span>${item.category === "media" ? "Audio / Video" : item.category[0].toUpperCase() + item.category.slice(1)}</span><span class="bar-track"><i style="width:${Math.max(3, item.count / max * 100)}%"></i></span><strong>${item.count}</strong></button>`).join("");
}

async function loadCategoryCatalog(category) {
  try {
    const data = await api("/api/formats");
    const formats = category === "archives"
      ? [...archiveFormats].sort()
      : data.sources.filter(format => categoryFormats[category]?.has(format)).sort();
    const routes = category === "archives"
      ? data.routes.filter(route => archiveFormats.has(route.target))
      : data.routes.filter(route => categoryFormats[category]?.has(route.source));
    const title = category === "media" ? "Audio / Video" : category[0].toUpperCase() + category.slice(1);
    const formatLabel = category === "archives" ? "archive output formats" : "source formats";
    document.getElementById("categoryCatalog").innerHTML = `<div class="category-copy"><strong>${escapeHtml(title)} conversions</strong><span>${formats.length} ${formatLabel} · ${routes.length} registered routes</span></div><div class="format-chips">${formats.map(format => `<span>${escapeHtml(format.toUpperCase())}</span>`).join("")}</div>`;
  } catch (error) { showToast(error.message); }
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

async function loadTargets(source) {
  const select = document.getElementById("targetFormat");
  select.innerHTML = '<option value="">Select output</option>';
  if (!source) return;
  try {
    const data = await api("/api/formats");
    const allowedSources = categoryFormats[state.activeCategory];
    const sourceMatchesCategory = state.activeCategory === "archives" || !allowedSources || allowedSources.has(source);
    const targets = sourceMatchesCategory
      ? data.routes.filter(route => route.source === source && (state.activeCategory !== "archives" || archiveFormats.has(route.target))).map(route => route.target)
      : [];
    [...new Set(targets)].sort().forEach(target => {
      const option = document.createElement("option");
      option.value = target;
      option.textContent = target.toUpperCase();
      select.appendChild(option);
    });
    const preferred = state.preferredRoute?.source === source ? state.preferredRoute.target : favoritePairs().find(pair => pair.source === source)?.target;
    const preferredTarget = state.preferredArchiveTarget || preferred;
    if (preferredTarget && [...select.options].some(option => option.value === preferredTarget)) select.value = preferredTarget;
    document.getElementById("convertButton").disabled = !state.currentUpload || targets.length === 0 || !select.value;
    syncFavoriteToggle();
    syncImageTools();
  } catch (error) { showToast(error.message); }
}

async function handleFiles(files) {
  if (!files.length) return;
  if (files.length > 1) {
    await addBatchFiles(files);
    showView("batch");
    showToast(`${files.length} files added to the batch queue`);
    return;
  }
  document.getElementById("removeSolidBackground").checked = false;
  document.getElementById("backgroundTolerance").value = "24";
  document.getElementById("backgroundToleranceValue").textContent = "24";
  state.files = [...files];
  const form = new FormData();
  [...files].forEach(file => form.append("files", file));
  document.getElementById("fileList").innerHTML = state.files.map(file => `<div class="file-row"><div><strong>${escapeHtml(file.name)}</strong><br><small>${formatSize(file.size)}</small></div><span>${extension(file.name).toUpperCase()}</span></div>`).join("");
  try {
    const uploaded = await api("/api/upload", { method: "POST", body: form });
    state.currentUpload = uploaded.files[0];
    const source = state.currentUpload.extension;
    const detectedFormat = document.querySelector("#fileList .file-row > span");
    if (detectedFormat) detectedFormat.textContent = source.toUpperCase();
    document.getElementById("sourceFormat").value = source.toUpperCase();
    await loadTargets(source);
    state.preferredRoute = null;
    state.preferredArchiveTarget = null;
  } catch (error) { showToast(error.message); }
}

function extension(filename) {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".tar.gz") || lower.endsWith(".tgz")) return "tar.gz";
  return lower.split(".").pop();
}
function formatSize(size) { if (size < 1024) return `${size} B`; if (size < 1048576) return `${(size / 1024).toFixed(1)} KB`; return `${(size / 1048576).toFixed(1)} MB`; }

function favoritePairs() {
  try { return JSON.parse(localStorage.getItem("uc-favorites") || "[]"); }
  catch (_) { return []; }
}

function syncFavoriteToggle() {
  const button = document.getElementById("favoriteToggle");
  const source = state.currentUpload?.extension;
  const target = document.getElementById("targetFormat").value;
  const active = source && target;
  const saved = favoritePairs().some(pair => pair.source === source && pair.target === target);
  button.disabled = !active;
  button.textContent = saved ? "★ Saved format pair" : "☆ Save format pair";
}

function syncImageTools() {
  const panel = document.getElementById("backgroundTools");
  const removeBackground = document.getElementById("removeSolidBackground");
  const tolerance = document.getElementById("backgroundTolerance");
  const isImage = Boolean(state.currentUpload && categoryFormats.images.has(state.currentUpload.extension));
  const supportsTransparency = document.getElementById("targetFormat").value === "png";
  panel.classList.toggle("hidden", !isImage);
  if (!supportsTransparency) removeBackground.checked = false;
  removeBackground.disabled = !isImage || !supportsTransparency;
  tolerance.disabled = removeBackground.disabled || !removeBackground.checked;
  document.getElementById("backgroundHelp").textContent = supportsTransparency
    ? "Removes flat-color regions connected to the image edge."
    : "Choose PNG output to preserve transparency.";
}

function toggleFavorite(source, target) {
  const pairs = favoritePairs();
  const existing = pairs.findIndex(pair => pair.source === source && pair.target === target);
  if (existing >= 0) pairs.splice(existing, 1);
  else pairs.push({ source, target, addedAt: new Date().toISOString() });
  localStorage.setItem("uc-favorites", JSON.stringify(pairs));
  syncFavoriteToggle();
  if (!document.getElementById("favoritesView").classList.contains("hidden")) renderFavorites();
}

function renderFavorites() {
  const list = document.getElementById("favoriteList");
  const pairs = favoritePairs();
  if (!pairs.length) {
    list.innerHTML = '<div class="empty-state">No saved format pairs yet</div>';
    return;
  }
  list.innerHTML = pairs.map(pair => `<div class="favorite-row"><div class="favorite-mark">★</div><div><strong>${escapeHtml(pair.source.toUpperCase())} to ${escapeHtml(pair.target.toUpperCase())}</strong><small>Saved ${escapeHtml(new Date(pair.addedAt || Date.now()).toLocaleDateString())}</small></div><div class="history-actions"><button data-favorite-use="${escapeHtml(pair.source)}" data-favorite-target="${escapeHtml(pair.target)}">Use</button><button data-favorite-remove="${escapeHtml(pair.source)}" data-favorite-target="${escapeHtml(pair.target)}">Remove</button></div></div>`).join("");
}

async function loadEngines() {
  try {
    const [engineData, formatData] = await Promise.all([api("/api/engines"), api("/api/formats")]);
    const available = engineData.engines.filter(engine => engine.status === "available").length;
    const missing = engineData.engines.filter(engine => engine.status !== "available").length;
    document.getElementById("engineSummary").innerHTML = `<article><span>Ready</span><strong>${available}</strong></article><article><span>Registered routes</span><strong>${formatData.routes.length}</strong></article><article><span>Missing optional</span><strong>${missing}</strong></article><article><span>Package manager</span><strong>${escapeHtml(engineData.package_manager.status)}</strong></article>`;
    document.getElementById("engineList").innerHTML = engineData.engines.map(engine => {
      const version = engine.version ? `<small>${escapeHtml(engine.category)} · ${escapeHtml(engine.version)}</small>` : `<small>${escapeHtml(engine.category)}</small>`;
      const action = engine.installable
        ? `<button data-engine-install="${escapeHtml(engine.key)}" data-engine-name="${escapeHtml(engine.name)}" data-package-id="${escapeHtml(engine.package_id)}">Install</button>`
        : engine.status !== "available" && engine.install_url
          ? `<a href="${escapeHtml(engine.install_url)}" target="_blank" rel="noopener">Install guide</a>`
          : "";
      return `<div class="engine-row"><div class="engine-indicator ${engine.status === "available" ? "ready" : "missing"}"></div><div class="engine-name"><strong>${escapeHtml(engine.name)}</strong>${version}</div><span class="engine-state ${engine.status}">${escapeHtml(engine.status)}</span><div class="engine-actions">${action}</div></div>`;
    }).join("");
    state.engineRoutes = formatData.routes;
    renderEngineRoutes();
  } catch (error) { showToast(error.message); }
}

function renderEngineRoutes() {
  const query = document.getElementById("routeSearch").value.trim().toLowerCase();
  const routes = state.engineRoutes.filter(route => `${route.source} ${route.target} ${route.engine}`.toLowerCase().includes(query));
  document.getElementById("routeTable").innerHTML = `<div class="route-head"><span>Input</span><span>Output</span><span>Engine</span></div>${routes.map(route => `<div class="route-row"><span>${escapeHtml(route.source.toUpperCase())}</span><span>${escapeHtml(route.target.toUpperCase())}</span><span>${escapeHtml(route.engine)}</span></div>`).join("") || '<div class="empty-state">No matching routes</div>'}`;
}

function renderInstallJob(name, job) {
  const panel = document.getElementById("engineInstallPanel");
  const progressBar = document.getElementById("engineInstallProgressBar");
  panel.classList.remove("hidden");
  document.getElementById("engineInstallTitle").textContent = `Installing ${name}`;
  document.getElementById("engineInstallState").textContent = job.status;
  document.getElementById("engineInstallMessage").textContent = job.message || "Waiting for Windows Package Manager...";
  document.getElementById("engineInstallLog").textContent = job.logs?.length ? job.logs.slice(-16).join("\n") : "Waiting for installer output...";
  progressBar.style.width = Number.isFinite(job.progress) ? `${Math.max(0, Math.min(100, job.progress))}%` : "32%";
  progressBar.classList.toggle("indeterminate", job.status === "running" && !Number.isFinite(job.progress));
}

async function installEngine(key, name, packageId, button) {
  if (!confirm(`Install ${name} (${packageId}) with Windows Package Manager? This downloads software and may request Windows approval.`)) return;
  button.disabled = true;
  button.textContent = "Starting...";
  renderInstallJob(name, { status: "queued", progress: 0, message: "Starting Windows Package Manager...", logs: [] });
  try {
    const started = await api(`/api/engines/install/${encodeURIComponent(key)}`, { method: "POST", headers: { "X-UC-Install-Confirm": "yes" } });
    let result;
    do {
      await new Promise(resolve => setTimeout(resolve, 1000));
      result = await api(`/api/engines/install-jobs/${started.job_id}`);
      renderInstallJob(name, result);
    } while (["queued", "running"].includes(result.status));
    if (result.status === "succeeded") showToast(`${name} installation completed. Refreshing detection...`);
    else showToast(`${name} installation failed. See Engine status for details.`);
    await loadEngines();
    const refreshed = await api("/api/engines");
    const engine = refreshed.engines.find(item => item.key === key);
    if (engine?.status === "available") {
      document.getElementById("engineInstallMessage").textContent = `${name} is installed and detected.`;
    } else if (result.status === "succeeded") {
      document.getElementById("engineInstallMessage").textContent = `${name} installed. Restart Universal Converter if its executable is not yet visible.`;
    }
  } catch (error) {
    renderInstallJob(name, { status: "failed", message: error.message, logs: [] });
    showToast(error.message);
    button.disabled = false;
    button.textContent = "Install";
  }
}

function batchTargets(source, routes) {
  return [...new Set(routes.filter(route => route.source === source).map(route => route.target))].sort();
}

async function addBatchFiles(files) {
  if (!files.length) return;
  state.batchQueue.push(...[...files].map(file => ({ key: `${Date.now()}-${Math.random()}`, file, source: extension(file.name), target: "", status: "queued", resultId: null, error: "" })));
  renderBatchQueue();
}

async function renderBatchQueue() {
  const list = document.getElementById("batchQueue");
  const bulkTarget = document.getElementById("batchTargetAll");
  const selectedBulkTarget = bulkTarget.value;
  if (!state.batchQueue.length) {
    list.innerHTML = '<div class="empty-state">Queue is empty</div>';
    bulkTarget.innerHTML = '<option value="">Add files to choose output</option>';
    bulkTarget.disabled = true;
    document.getElementById("applyBatchTarget").disabled = true;
    document.getElementById("runBatch").disabled = true;
    return;
  }
  try {
    const formats = await api("/api/formats");
    const bulkTargets = [...new Set(state.batchQueue.flatMap(item => batchTargets(item.source, formats.routes)))].sort();
    bulkTarget.innerHTML = '<option value="">Choose output format</option>' + bulkTargets.map(target => `<option value="${escapeHtml(target)}">${escapeHtml(target.toUpperCase())}</option>`).join("");
    if (bulkTargets.includes(selectedBulkTarget)) bulkTarget.value = selectedBulkTarget;
    bulkTarget.disabled = state.batchRunning || !bulkTargets.length;
    const canApply = state.batchQueue.some(item => item.target !== bulkTarget.value && ["queued", "failed"].includes(item.status) && batchTargets(item.source, formats.routes).includes(bulkTarget.value));
    document.getElementById("applyBatchTarget").disabled = state.batchRunning || !canApply;
    list.innerHTML = state.batchQueue.map(item => {
      const options = batchTargets(item.source, formats.routes);
      const choices = options.map(target => `<option value="${escapeHtml(target)}" ${item.target === target ? "selected" : ""}>${escapeHtml(target.toUpperCase())}</option>`).join("");
      return `<div class="batch-row" data-batch-key="${item.key}"><div class="batch-file"><strong>${escapeHtml(item.file.name)}</strong><small>${formatSize(item.file.size)} · ${escapeHtml(item.source.toUpperCase())}</small></div><select data-batch-target ${options.length ? "" : "disabled"}><option value="">Choose output</option>${choices}</select><span class="batch-state ${item.status}">${escapeHtml(item.status)}${item.error ? `: ${escapeHtml(item.error)}` : ""}</span><div class="history-actions">${item.status === "failed" ? `<button data-batch-retry>Retry</button>` : ""}${item.status === "success" ? `<a href="/api/download/${item.resultId}" target="_blank" rel="noopener">Download</a>` : ""}<button data-batch-remove>Remove</button></div></div>`;
    }).join("");
    document.getElementById("runBatch").disabled = state.batchRunning || !state.batchQueue.some(item => item.target && ["queued", "failed"].includes(item.status));
    document.getElementById("clearBatch").disabled = state.batchRunning;
    document.getElementById("stopBatch").classList.toggle("hidden", !state.batchRunning);
  } catch (error) { showToast(error.message); }
}

async function runBatchQueue() {
  if (state.batchRunning) return;
  const pending = state.batchQueue.filter(item => item.target && ["queued", "failed"].includes(item.status));
  if (!pending.length) return;
  const progress = document.getElementById("batchProgress");
  const fill = document.getElementById("batchProgressFill");
  const message = document.getElementById("batchMessage");
  let workerCount = 1;
  try { workerCount = Math.max(1, Math.min(8, Number((await api("/api/settings")).worker_count) || 1)); } catch (_) { }
  state.batchRunning = true;
  state.stopBatch = false;
  progress.classList.remove("hidden");
  renderBatchQueue();
  let next = 0;
  let finished = 0;
  async function processNext() {
    if (state.stopBatch || next >= pending.length) return;
    const item = pending[next++];
    item.status = "uploading";
    item.error = "";
    message.textContent = `Processing ${finished + 1} of ${pending.length}: ${item.file.name}`;
    renderBatchQueue();
    try {
      const body = new FormData();
      body.append("files", item.file);
      const uploaded = await api("/api/upload", { method: "POST", body });
      item.status = "converting";
      renderBatchQueue();
      const form = new FormData();
      form.append("upload_id", uploaded.files[0].id);
      form.append("target", item.target);
      form.append("original_filename", item.file.name);
      form.append("settings", "{}");
      const result = await api("/api/convert", { method: "POST", body: form });
      item.status = "success";
      item.resultId = result.id;
    } catch (error) {
      item.status = "failed";
      item.error = error.message;
    }
    finished += 1;
    fill.style.width = `${Math.round(finished / pending.length * 100)}%`;
    renderBatchQueue();
    await processNext();
  }
  await Promise.all(Array.from({ length: Math.min(workerCount, pending.length) }, () => processNext()));
  state.batchRunning = false;
  const remaining = pending.length - finished;
  message.textContent = state.stopBatch ? `${finished} processed; ${remaining} left queued` : `${finished} queue item${finished === 1 ? "" : "s"} processed using ${Math.min(workerCount, pending.length)} worker${Math.min(workerCount, pending.length) === 1 ? "" : "s"}`;
  renderBatchQueue();
  loadDashboard();
}

async function convert() {
  if (!state.currentUpload) return;
  const target = document.getElementById("targetFormat").value;
  if (!target) { showToast("Choose a target format"); return; }
  const form = new FormData();
  form.append("upload_id", state.currentUpload.id);
  form.append("target", target);
  form.append("original_filename", state.currentUpload.filename);
  form.append("settings", JSON.stringify({
    quality: document.getElementById("quality").value,
    remove_solid_background: document.getElementById("removeSolidBackground").checked,
    background_tolerance: Number(document.getElementById("backgroundTolerance").value)
  }));
  const button = document.getElementById("convertButton");
  const progress = document.getElementById("progress");
  button.disabled = true;
  progress.classList.remove("hidden");
  document.getElementById("progressBar").style.width = "35%";
  document.getElementById("resultMessage").textContent = "Converting locally...";
  try {
    const result = await api("/api/convert", { method: "POST", body: form });
    state.resultId = result.id;
    document.getElementById("progressBar").style.width = "100%";
    document.getElementById("resultMessage").textContent = "Conversion completed";
    showPreview(result.id, target);
    showToast("Conversion completed");
    loadDashboard();
  } catch (error) {
    document.getElementById("progressBar").style.width = "0%";
    document.getElementById("resultMessage").textContent = error.message;
    showToast(error.message);
  } finally { button.disabled = false; }
}

async function showPreview(id, target) {
  state.resultId = Number(id);
  const panel = document.getElementById("previewPanel");
  const area = document.getElementById("previewArea");
  const actions = document.getElementById("downloadActions");
  panel.classList.remove("hidden");
  area.innerHTML = '<div class="empty-state">Loading preview...</div>';
  actions.innerHTML = `<a class="primary-button" style="display:inline-grid;place-items:center;text-decoration:none" href="/api/download/${id}" download>Download</a>`;
  try {
    const preview = await api(`/api/preview/${id}`);
    if (preview.kind === "text") {
      area.innerHTML = `<pre>${escapeHtml(preview.content)}</pre>${preview.truncated ? '<small>Preview truncated</small>' : ''}`;
    } else if (preview.kind === "html") {
      const frame = document.createElement("iframe");
      frame.className = "html-preview";
      frame.setAttribute("sandbox", "");
      frame.title = "Converted HTML preview";
      frame.srcdoc = preview.content;
      area.replaceChildren(frame);
    } else if (preview.kind === "table") {
      area.innerHTML = `<div class="table-preview">${preview.content}</div>${preview.truncated ? '<small>Preview truncated</small>' : ''}`;
    } else if (preview.kind === "archive") {
      area.innerHTML = `<pre>${escapeHtml(preview.content.join("\n"))}</pre>${preview.truncated ? '<small>Preview truncated</small>' : ''}`;
    } else if (preview.kind === "image") {
      const meta = preview.metadata || {};
      area.innerHTML = `<figure class="media-preview"><img src="/api/preview/${id}/file" alt="Converted output preview"><figcaption>${escapeHtml([meta.width && meta.height ? `${meta.width} x ${meta.height}` : '', formatSize(meta.size || 0)].filter(Boolean).join(' · '))}</figcaption></figure>`;
    } else if (preview.kind === "pdf") {
      area.innerHTML = `<iframe class="pdf-preview" src="/api/preview/${id}/file" title="PDF preview"></iframe>`;
    } else if (preview.kind === "video") {
      area.innerHTML = `<video class="media-player" src="/api/preview/${id}/file" controls preload="metadata"></video>`;
    } else if (preview.kind === "audio") {
      area.innerHTML = `<audio class="media-player" src="/api/preview/${id}/file" controls preload="metadata"></audio>`;
    } else if (preview.kind === "metadata") {
      area.innerHTML = `<pre>${escapeHtml(preview.content || '')}</pre>`;
    } else {
      const meta = preview.metadata || {};
      area.innerHTML = `<div class="fallback-preview"><strong>${escapeHtml((target || preview.target).toUpperCase())} output</strong><span>${escapeHtml(formatSize(meta.size || 0))}</span></div>`;
    }
  } catch (error) {
    area.textContent = error.message;
  }
}

async function loadHostedFiles() {
  try {
    const data = await api("/api/host/files");
    const list = document.getElementById("hostFileList");
    if (!data.files.length) {
      list.innerHTML = '<div class="empty-state">No hosted files</div>';
      return;
    }
    list.innerHTML = data.files.map(file => `<div class="host-file-row"><div class="host-file-icon">${escapeHtml(file.extension.toUpperCase())}</div><div class="host-file-name"><strong>${escapeHtml(file.filename)}</strong><small>${escapeHtml(formatSize(file.size))}</small></div><div class="host-file-actions"><button data-host-preview="${escapeHtml(file.filename)}" data-host-url="${escapeHtml(file.url)}">Preview</button><a href="${escapeHtml(file.url)}" target="_blank" rel="noopener">Open</a><button data-host-delete="${escapeHtml(file.filename)}">Delete</button></div></div>`).join("");
  } catch (error) { showToast(error.message); }
}

async function uploadHostedFiles(files) {
  if (!files.length) return;
  const form = new FormData();
  [...files].forEach(file => form.append("files", file));
  try {
    await api("/api/host/upload", { method: "POST", body: form });
    showToast("Files hosted locally");
    loadHostedFiles();
  } catch (error) { showToast(error.message); }
}

async function previewHostedFile(filename, url) {
  const panel = document.getElementById("hostPreviewPanel");
  const area = document.getElementById("hostPreviewArea");
  const extension = filename.split(".").pop().toLowerCase();
  state.hostPreviewFilename = filename;
  panel.classList.remove("hidden");
  document.getElementById("hostPreviewTitle").textContent = filename;
  document.getElementById("hostOpenFile").href = url;
  if (["png", "jpg", "jpeg", "gif", "webp", "bmp", "ico", "svg"].includes(extension)) {
    area.innerHTML = `<img src="${escapeHtml(url)}" alt="${escapeHtml(filename)} preview">`;
  } else if (["html", "htm"].includes(extension)) {
    area.innerHTML = `<iframe class="html-preview" sandbox src="${escapeHtml(url)}" title="${escapeHtml(filename)}"></iframe>`;
  } else if (["mp4", "webm", "mov", "mkv"].includes(extension)) {
    area.innerHTML = `<video class="media-player" src="${escapeHtml(url)}" controls preload="metadata"></video>`;
  } else if (["mp3", "wav", "flac", "ogg", "m4a", "opus"].includes(extension)) {
    area.innerHTML = `<audio class="media-player" src="${escapeHtml(url)}" controls preload="metadata"></audio>`;
  } else {
    try {
      const response = await fetch(url);
      const text = await response.text();
      area.innerHTML = `<pre>${escapeHtml(text.slice(0, 500000))}</pre>`;
    } catch (error) {
      area.textContent = error.message;
    }
  }
}

function closeHostedPreview() {
  document.getElementById("hostPreviewPanel").classList.add("hidden");
  document.getElementById("hostPreviewArea").replaceChildren();
  document.getElementById("hostPreviewTitle").textContent = "Preview";
  document.getElementById("hostOpenFile").removeAttribute("href");
  state.hostPreviewFilename = null;
}

async function loadHistory() {
  try {
    const data = await api("/api/history");
    const search = document.getElementById("historySearch").value.toLowerCase();
    const filter = document.getElementById("historyFilter").value;
    const category = document.getElementById("historyCategory").value;
    const items = data.items.filter(item => (!search || item.original_filename.toLowerCase().includes(search)) && (filter === "all" || item.status === filter) && (category === "all" || categoryForFormat(item.source_format) === category));
    const table = document.getElementById("historyTable");
    table.innerHTML = '<div class="history-row header"><span>File and details</span><span>Conversion</span><span>Status</span><span>Engine</span><span>Actions</span></div>' + (items.length ? items.map(item => `<div class="history-row"><span class="history-file"><strong>${escapeHtml(item.original_filename)}</strong><small>${formatSize(item.file_size || 0)} input · ${item.output_size ? formatSize(item.output_size) + " output · " : ""}${item.created_at ? new Date(item.created_at).toLocaleString() : ""}</small>${item.error ? `<small class="error-text">${escapeHtml(item.error)}</small>` : ""}</span><span>${item.source_format.toUpperCase()} → ${item.target_format.toUpperCase()}<small>${Number(item.conversion_time || 0).toFixed(2)} sec</small></span><span class="status-pill ${item.status === "failed" ? "failed" : ""}">${item.status}</span><span>${escapeHtml(item.engine)}</span><div class="history-actions"><button data-history-preview="${item.id}" data-history-target="${item.target_format}" ${item.status !== "success" ? "disabled" : ""}>Preview</button><button data-history-download="${item.id}" ${item.status !== "success" ? "disabled" : ""}>Download</button><button data-history-delete="${item.id}">Delete</button></div></div>`).join("") : '<div class="empty-state">No matching history</div>');
  } catch (error) { showToast(error.message); }
}

function applyPreferences() {
  const savedTheme = localStorage.getItem("uc-theme");
  const theme = ["light", "dark"].includes(savedTheme) ? savedTheme : "light";
  const accentOptions = [...document.getElementById("accentSelect").options].map(option => option.value);
  const savedAccent = localStorage.getItem("uc-accent");
  const accent = accentOptions.includes(savedAccent) ? savedAccent : accentOptions[0];
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.setProperty("--accent", accent);
  document.documentElement.style.setProperty("--accent-ink", "#171915");
  document.getElementById("themeSelect").value = theme;
  document.getElementById("accentSelect").value = accent;
}

function applyNavigationPreferences() {
  document.querySelectorAll(".nav-group").forEach(group => {
    const saved = localStorage.getItem(`uc-nav-${group.dataset.navGroup}`);
    if (saved !== null) group.open = saved === "open";
  });
}

function applySidebarPreference() {
  const hidden = localStorage.getItem("uc-sidebar-hidden") === "true";
  document.body.classList.toggle("sidebar-collapsed", hidden);
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("sidebarHidden").checked = hidden;
}

for (const button of document.querySelectorAll(".nav-item[data-view]")) {
  button.addEventListener("click", () => showView(button.dataset.view));
}
for (const group of document.querySelectorAll(".nav-group")) {
  group.addEventListener("toggle", () => localStorage.setItem(`uc-nav-${group.dataset.navGroup}`, group.open ? "open" : "closed"));
}
document.getElementById("newConversion").addEventListener("click", () => showView("converter"));
document.getElementById("viewHistory").addEventListener("click", () => showView("history"));
document.getElementById("settingsButton").addEventListener("click", () => showView("settings"));
document.getElementById("themeButton").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("uc-theme", next); applyPreferences();
});
function closeSidebar() {
  const sidebar = document.getElementById("sidebar");
  sidebar.classList.remove("open");
  if (!document.body.classList.contains("sidebar-collapsed")) {
    document.body.classList.add("sidebar-collapsed");
    localStorage.setItem("uc-sidebar-hidden", "true");
    document.getElementById("sidebarHidden").checked = true;
  }
}

document.getElementById("menuButton").addEventListener("click", () => {
  const sidebar = document.getElementById("sidebar");
  if (document.body.classList.contains("sidebar-collapsed")) {
    sidebar.classList.toggle("open");
  } else {
    closeSidebar();
  }
});
document.getElementById("sidebarCloseButton").addEventListener("click", closeSidebar);
document.getElementById("sidebarScrim").addEventListener("click", closeSidebar);
document.getElementById("sidebarHidden").addEventListener("change", event => {
  localStorage.setItem("uc-sidebar-hidden", String(event.target.checked));
  applySidebarPreference();
});
document.getElementById("chooseFiles").addEventListener("click", () => document.getElementById("fileInput").click());
document.getElementById("fileInput").addEventListener("change", event => handleFiles(event.target.files));
document.getElementById("convertButton").addEventListener("click", convert);
document.getElementById("clearFiles").addEventListener("click", () => { state.files = []; state.currentUpload = null; document.getElementById("fileList").innerHTML = ""; document.getElementById("sourceFormat").value = "Auto-detected"; document.getElementById("convertButton").disabled = true; document.getElementById("targetFormat").innerHTML = '<option value="">Select output</option>'; document.getElementById("previewPanel").classList.add("hidden"); document.getElementById("removeSolidBackground").checked = false; syncImageTools(); });

const dropZone = document.getElementById("dropZone");
["dragenter","dragover"].forEach(type => dropZone.addEventListener(type, event => { event.preventDefault(); dropZone.classList.add("dragging"); }));
["dragleave","drop"].forEach(type => dropZone.addEventListener(type, event => { event.preventDefault(); dropZone.classList.remove("dragging"); }));
dropZone.addEventListener("drop", event => handleFiles(event.dataTransfer.files));

document.querySelectorAll("[data-shortcut]").forEach(button => button.addEventListener("click", () => { showView("converter"); document.getElementById("converterTitle").textContent = `${button.textContent.trim()} Converter`; }));
document.getElementById("themeSelect").addEventListener("change", event => { localStorage.setItem("uc-theme", event.target.value); applyPreferences(); });
document.getElementById("accentSelect").addEventListener("change", event => { localStorage.setItem("uc-accent", event.target.value); applyPreferences(); });
document.getElementById("historySearch").addEventListener("input", loadHistory);
document.getElementById("historyFilter").addEventListener("change", loadHistory);
document.getElementById("historyCategory").addEventListener("change", loadHistory);
document.getElementById("targetFormat").addEventListener("change", event => {
  syncFavoriteToggle();
  document.getElementById("convertButton").disabled = !state.currentUpload || !event.target.value;
  syncImageTools();
});
document.getElementById("removeSolidBackground").addEventListener("change", syncImageTools);
document.getElementById("backgroundTolerance").addEventListener("input", event => {
  document.getElementById("backgroundToleranceValue").textContent = event.target.value;
});
document.getElementById("favoriteToggle").addEventListener("click", () => toggleFavorite(state.currentUpload?.extension, document.getElementById("targetFormat").value));
document.getElementById("clearFavorites").addEventListener("click", () => { localStorage.removeItem("uc-favorites"); renderFavorites(); syncFavoriteToggle(); showToast("Favorites cleared"); });
document.getElementById("favoriteList").addEventListener("click", event => {
  const remove = event.target.closest("[data-favorite-remove]");
  const use = event.target.closest("[data-favorite-use]");
  if (remove) toggleFavorite(remove.dataset.favoriteRemove, remove.dataset.favoriteTarget);
  if (use) {
    state.preferredRoute = { source: use.dataset.favoriteUse, target: use.dataset.favoriteTarget };
    showView("converter");
    showToast(`Choose a ${state.preferredRoute.source.toUpperCase()} file to use this format pair`);
  }
});
document.getElementById("refreshEngines").addEventListener("click", loadEngines);
document.getElementById("routeSearch").addEventListener("input", renderEngineRoutes);
document.getElementById("engineList").addEventListener("click", event => {
  const button = event.target.closest("[data-engine-install]");
  if (button) installEngine(button.dataset.engineInstall, button.dataset.engineName, button.dataset.packageId, button);
});
document.getElementById("dashboardEngines").addEventListener("click", () => showView("engines"));
document.getElementById("supportEngines").addEventListener("click", () => showView("engines"));
document.getElementById("copySupportEmail").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText("surjolivemailbox@gmail.com");
    showToast("Support email copied");
  } catch (error) {
    showToast("Clipboard access is unavailable in this browser");
  }
});
document.getElementById("categoryOverview").addEventListener("click", event => {
  const button = event.target.closest("[data-open-category]");
  if (button) showView(button.dataset.openCategory);
});
document.getElementById("batchChoose").addEventListener("click", () => document.getElementById("batchInput").click());
document.getElementById("batchInput").addEventListener("change", event => addBatchFiles(event.target.files));
document.getElementById("batchTargetAll").addEventListener("change", renderBatchQueue);
document.getElementById("applyBatchTarget").addEventListener("click", async () => {
  const target = document.getElementById("batchTargetAll").value;
  if (!target || state.batchRunning) return;
  try {
    const formats = await api("/api/formats");
    let applied = 0;
    for (const item of state.batchQueue) {
      if (["queued", "failed"].includes(item.status) && batchTargets(item.source, formats.routes).includes(target)) {
        item.target = target;
        item.status = "queued";
        item.error = "";
        applied += 1;
      }
    }
    await renderBatchQueue();
    showToast(`${target.toUpperCase()} applied to ${applied} compatible files`);
  } catch (error) { showToast(error.message); }
});
document.getElementById("runBatch").addEventListener("click", runBatchQueue);
document.getElementById("clearBatch").addEventListener("click", () => { if (state.batchRunning) return; state.batchQueue = []; document.getElementById("batchMessage").textContent = ""; document.getElementById("batchProgress").classList.add("hidden"); renderBatchQueue(); });
document.getElementById("stopBatch").addEventListener("click", () => { state.stopBatch = true; document.getElementById("batchMessage").textContent = "Finishing active files; remaining items will stay queued."; });
document.getElementById("batchQueue").addEventListener("change", event => {
  const row = event.target.closest("[data-batch-key]");
  if (!row || !event.target.matches("[data-batch-target]")) return;
  const item = state.batchQueue.find(entry => entry.key === row.dataset.batchKey);
  if (item) { item.target = event.target.value; renderBatchQueue(); }
});
document.getElementById("batchQueue").addEventListener("click", event => {
  const row = event.target.closest("[data-batch-key]");
  if (!row) return;
  const item = state.batchQueue.find(entry => entry.key === row.dataset.batchKey);
  if (event.target.closest("[data-batch-remove]")) state.batchQueue = state.batchQueue.filter(entry => entry !== item);
  if (event.target.closest("[data-batch-retry]") && item) { item.status = "queued"; item.error = ""; }
  renderBatchQueue();
});
const batchDrop = document.getElementById("batchDrop");
["dragenter", "dragover"].forEach(type => batchDrop.addEventListener(type, event => { event.preventDefault(); batchDrop.classList.add("dragging"); }));
["dragleave", "drop"].forEach(type => batchDrop.addEventListener(type, event => { event.preventDefault(); batchDrop.classList.remove("dragging"); }));
batchDrop.addEventListener("drop", event => addBatchFiles(event.dataTransfer.files));
document.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "o") { event.preventDefault(); showView("converter"); document.getElementById("fileInput").click(); }
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && !document.getElementById("converterView").classList.contains("hidden")) { event.preventDefault(); convert(); }
  if (event.key === "Escape") closeSidebar();
});
document.getElementById("historyTable").addEventListener("click", async event => {
  const download = event.target.closest("[data-history-download]");
  if (download) window.location.href = `/api/download/${download.dataset.historyDownload}`;
  const preview = event.target.closest("[data-history-preview]");
  if (preview) {
    showView("converter");
    showPreview(preview.dataset.historyPreview, preview.dataset.historyTarget);
  }
  const deletion = event.target.closest("[data-history-delete]");
  if (deletion) {
    const id = Number(deletion.dataset.historyDelete);
    if (!confirm("Delete this conversion and its output file?")) return;
    try {
      await api(`/api/conversion/${id}`, { method: "DELETE" });
      if (state.resultId === id) {
        document.getElementById("previewPanel").classList.add("hidden");
        document.getElementById("previewArea").replaceChildren();
        document.getElementById("downloadActions").replaceChildren();
        state.resultId = null;
      }
      await loadHistory();
      loadDashboard();
      showToast("Conversion and output deleted");
    } catch (error) { showToast(error.message); }
  }
});
document.getElementById("hostChooseFiles").addEventListener("click", () => document.getElementById("hostFileInput").click());
document.getElementById("hostFileInput").addEventListener("change", event => uploadHostedFiles(event.target.files));
document.getElementById("hostFileList").addEventListener("click", async event => {
  const preview = event.target.closest("[data-host-preview]");
  if (preview) previewHostedFile(preview.dataset.hostPreview, preview.dataset.hostUrl);
  const deletion = event.target.closest("[data-host-delete]");
  if (deletion) {
    const filename = deletion.dataset.hostDelete;
    if (!confirm(`Delete ${filename}?`)) return;
    try {
      await api(`/api/host/files/${encodeURIComponent(filename)}`, { method: "DELETE" });
      if (state.hostPreviewFilename === filename) closeHostedPreview();
      await loadHostedFiles();
      showToast(`${filename} deleted`);
    } catch (error) { showToast(error.message); }
  }
});
document.getElementById("clearHistory").addEventListener("click", async () => {
  if (!confirm("Clear all conversion history and generated outputs?")) return;
  try {
    await api("/api/history", { method: "DELETE" });
    document.getElementById("previewPanel").classList.add("hidden");
    document.getElementById("previewArea").replaceChildren();
    document.getElementById("downloadActions").replaceChildren();
    state.resultId = null;
    await loadHistory();
    loadDashboard();
    showToast("History and generated outputs cleared");
  } catch (error) { showToast(error.message); }
});

async function loadSettings() {
  try {
    const settings = await api("/api/settings");
    document.getElementById("sizeSelect").value = String(settings.max_upload_size);
    document.getElementById("workerCount").value = String(settings.worker_count);
    document.getElementById("cleanupDays").value = String(settings.cleanup_days);
    document.getElementById("cleanupEnabled").checked = settings.cleanup_enabled;
    document.getElementById("apiKeyEnabled").checked = settings.api_key;
  } catch (error) { showToast(error.message); }
}

async function saveSettings() {
  const requireKey = document.getElementById("apiKeyEnabled").checked;
  const apiKey = document.getElementById("apiKeyInput").value.trim();
  if (requireKey && !apiKey) {
    showToast("Enter a local API key or disable API key protection");
    return;
  }
  try {
    await api("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      max_upload_size: Number(document.getElementById("sizeSelect").value),
      worker_count: Number(document.getElementById("workerCount").value),
      cleanup_days: Number(document.getElementById("cleanupDays").value),
      cleanup_enabled: document.getElementById("cleanupEnabled").checked,
      api_key: requireKey ? apiKey : ""
    }) });
    showToast("Settings saved");
  } catch (error) { showToast(error.message); }
}

async function exportHistory(format) {
  try {
    const result = await api(`/api/history/export?format=${format}`);
    const blob = new Blob([result.content], { type: format === "csv" ? "text/csv" : "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = result.filename;
    link.click();
    URL.revokeObjectURL(url);
  } catch (error) { showToast(error.message); }
}

document.getElementById("saveSettings").addEventListener("click", saveSettings);
document.getElementById("runCleanup").addEventListener("click", async () => {
  try { const result = await api("/api/settings/cleanup", { method: "POST" }); showToast(`${result.removed} temporary files removed`); } catch (error) { showToast(error.message); }
});
document.getElementById("runDiagnostics").addEventListener("click", async () => {
  try { const result = await api("/api/settings/diagnostics"); document.getElementById("diagnosticsOutput").textContent = JSON.stringify(result, null, 2); } catch (error) { showToast(error.message); }
});
document.getElementById("exportCsv").addEventListener("click", () => exportHistory("csv"));
document.getElementById("exportJson").addEventListener("click", () => exportHistory("json"));

applyPreferences();
applyNavigationPreferences();
applySidebarPreference();
const lastView = localStorage.getItem("uc-last-view");
if (lastView && [...document.querySelectorAll(".nav-item[data-view]")].some(button => button.dataset.view === lastView)) showView(lastView);
loadSettings();
loadDashboard();
