(function () {
  const cfg = window.__DC_PAGE__;
  const slug = cfg.slug;
  const columns = cfg.columns;

  const elDate = document.getElementById("trade-date");
  const elBoards = document.getElementById("board-select");
  const elHead = document.getElementById("table-head");
  const elBody = document.getElementById("table-body");
  const elSummary = document.getElementById("result-summary");
  const elEmpty = document.getElementById("table-empty");
  const elError = document.getElementById("table-error");
  const elHint = document.getElementById("filter-hint");
  const chipGroup = document.getElementById("content-type-chips");

  let selectedContentTypes = [];

  function fmtCell(val, fmt) {
    if (val === null || val === undefined || val === "") return "—";
    if (fmt === "bool") return val === 1 || val === true ? "是" : "否";
    if (fmt === "int") return Number(val).toLocaleString("zh-CN");
    if (fmt === "pct" || fmt === "num") {
      const n = Number(val);
      if (Number.isNaN(n)) return val;
      return n.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
    }
    return val;
  }

  function selectedBoardCodes() {
    return Array.from(elBoards.selectedOptions).map((o) => o.value);
  }

  function getContentTypesParam() {
    return selectedContentTypes.length ? selectedContentTypes.join(",") : "";
  }

  async function apiGet(path) {
    const res = await fetch(path, { credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "请求失败");
    return data;
  }

  function showError(msg) {
    elError.textContent = msg;
    elError.classList.remove("hidden");
  }

  function clearError() {
    elError.classList.add("hidden");
  }

  function renderHead() {
    elHead.innerHTML = columns.map((c) => `<th>${c.label}</th>`).join("");
  }

  function renderRows(items) {
    if (!items.length) {
      elBody.innerHTML = "";
      elEmpty.classList.remove("hidden");
      return;
    }
    elEmpty.classList.add("hidden");
    elBody.innerHTML = items
      .map(
        (row) =>
          "<tr>" +
          columns.map((c) => `<td>${fmtCell(row[c.key], c.fmt)}</td>`).join("") +
          "</tr>"
      )
      .join("");
  }

  async function loadTradeDates() {
    const data = await apiGet(`/api/dc/meta/trade-dates?slug=${encodeURIComponent(slug)}`);
    elDate.innerHTML = data.dates
      .map((d) => `<option value="${d}">${d}</option>`)
      .join("");
    if (data.latest && !data.dates.includes(data.latest)) {
      elDate.insertAdjacentHTML("afterbegin", `<option value="${data.latest}">${data.latest}</option>`);
    }
    if (data.latest) elDate.value = data.latest;
  }

  async function loadBoards() {
    const td = elDate.value;
    if (!td) return;
    const ct = getContentTypesParam();
    let url = `/api/dc/meta/boards?slug=${encodeURIComponent(slug)}&trade_date=${encodeURIComponent(td)}`;
    if (ct) url += `&content_types=${encodeURIComponent(ct)}`;
    const data = await apiGet(url);
    const prev = new Set(selectedBoardCodes());
    elBoards.innerHTML = data.boards
      .map(
        (b) =>
          `<option value="${b.industry_code}"${prev.has(b.industry_code) ? " selected" : ""}>` +
          `[${b.content_type}] ${b.industry_name} (${b.industry_code})` +
          `</option>`
      )
      .join("");
    elHint.textContent = `共 ${data.boards.length} 个板块可选；不选表示全部`;
  }

  async function loadData() {
    clearError();
    elSummary.textContent = "查询中…";
    const td = elDate.value;
    const ct = getContentTypesParam();
    const codes = selectedBoardCodes();
    let url = `/api/dc/${encodeURIComponent(slug)}?trade_date=${encodeURIComponent(td)}`;
    if (ct) url += `&content_types=${encodeURIComponent(ct)}`;
    if (codes.length) url += `&industry_codes=${encodeURIComponent(codes.join(","))}`;
    const data = await apiGet(url);
    renderRows(data.items);
    const boardHint = codes.length ? `，已选 ${codes.length} 个板块` : "，全部板块";
    const typeHint = ct ? `，类型：${ct}` : "，类型：全部";
    elSummary.textContent = `${data.trade_date} · 共 ${data.total} 条${typeHint}${boardHint}`;
  }

  chipGroup.addEventListener("click", (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    const val = btn.dataset.value;
    if (!val) {
      chipGroup.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      selectedContentTypes = [];
    } else {
      chipGroup.querySelector('[data-value=""]').classList.remove("active");
      btn.classList.toggle("active");
      selectedContentTypes = Array.from(chipGroup.querySelectorAll(".chip.active"))
        .map((c) => c.dataset.value)
        .filter(Boolean);
      if (!selectedContentTypes.length) {
        chipGroup.querySelector('[data-value=""]').classList.add("active");
      }
    }
    loadBoards().catch((err) => showError(err.message));
  });

  document.getElementById("btn-query").addEventListener("click", () => {
    loadData().catch((err) => showError(err.message));
  });

  document.getElementById("btn-reset-boards").addEventListener("click", () => {
    Array.from(elBoards.options).forEach((o) => (o.selected = false));
  });

  elDate.addEventListener("change", () => {
    loadBoards().then(() => loadData()).catch((err) => showError(err.message));
  });

  renderHead();
  loadTradeDates()
    .then(() => loadBoards())
    .then(() => loadData())
    .catch((err) => showError(err.message));
})();
