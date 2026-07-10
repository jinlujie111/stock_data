(function () {
  const cfg = window.__DC_PAGE__;
  const slug = cfg.slug;
  const columns = cfg.columns;
  const sortHint = cfg.sort_hint || "";

  const elDate = document.getElementById("trade-date");
  const elSearch = document.getElementById("board-search");
  const elDropdown = document.getElementById("board-dropdown");
  const elSelected = document.getElementById("board-selected");
  const elPicker = document.getElementById("board-picker");
  const elHead = document.getElementById("table-head");
  const elBody = document.getElementById("table-body");
  const elSummary = document.getElementById("result-summary");
  const elEmpty = document.getElementById("table-empty");
  const elError = document.getElementById("table-error");
  const elHint = document.getElementById("filter-hint");
  const chipGroup = document.getElementById("content-type-chips");

  let selectedContentTypes = [];
  let allBoards = [];
  /** @type {Map<string, {industry_code: string, industry_name: string, content_type: string}>} */
  const selectedBoards = new Map();

  function fmtCell(val, fmt) {
    if (val === null || val === undefined || val === "") return "—";
    if (fmt === "bool") return val === 1 || val === true ? "是" : "否";
    if (fmt === "int") return Number(val).toLocaleString("zh-CN");
    if (fmt === "pct" || fmt === "pct2" || fmt === "num") {
      const n = Number(val);
      if (Number.isNaN(n)) return val;
      if (fmt === "pct2") return n.toFixed(2) + "%";
      return n.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
    }
    return val;
  }

  function pctChangeClass(col, val) {
    if (col.key !== "pct_change") return "";
    const n = Number(val);
    if (Number.isNaN(n) || n === 0) return "";
    return n > 0 ? "cell-rise" : "cell-fall";
  }

  function renderCell(row, col) {
    const cls = pctChangeClass(col, row[col.key]);
    const text = fmtCell(row[col.key], col.fmt);
    return cls ? `<td class="${cls}">${text}</td>` : `<td>${text}</td>`;
  }

  function selectedBoardCodes() {
    return Array.from(selectedBoards.keys());
  }

  function getContentTypesParam() {
    return selectedContentTypes.length ? selectedContentTypes.join(",") : "";
  }

  function boardLabel(b) {
    return `[${b.content_type}] ${b.industry_name} (${b.industry_code})`;
  }

  function matchBoard(board, q) {
    const text = `${board.industry_name} ${board.industry_code} ${board.content_type}`.toLowerCase();
    const tokens = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!tokens.length) return true;
    return tokens.every((t) => text.includes(t));
  }

  function renderSelectedTags() {
    if (!selectedBoards.size) {
      elSelected.innerHTML = '<span class="board-placeholder">未选择板块（展示全部）</span>';
      return;
    }
    elSelected.innerHTML = Array.from(selectedBoards.values())
      .map(
        (b) =>
          `<span class="board-tag" data-code="${b.industry_code}">` +
          `${boardLabel(b)}<button type="button" aria-label="移除">×</button></span>`
      )
      .join("");
  }

  function renderDropdown(matches) {
    if (!matches.length) {
      elDropdown.innerHTML = '<div class="board-option board-option--empty">无匹配板块</div>';
      elDropdown.classList.remove("hidden");
      return;
    }
    elDropdown.innerHTML = matches
      .slice(0, 50)
      .map(
        (b) =>
          `<button type="button" class="board-option" data-code="${b.industry_code}">` +
          `${boardLabel(b)}</button>`
      )
      .join("");
    elDropdown.classList.remove("hidden");
  }

  function hideDropdown() {
    elDropdown.classList.add("hidden");
  }

  function onSearchInput() {
    const q = elSearch.value;
    if (!q.trim()) {
      hideDropdown();
      return;
    }
    const matches = allBoards.filter((b) => !selectedBoards.has(b.industry_code) && matchBoard(b, q));
    renderDropdown(matches);
  }

  function addBoard(code) {
    const board = allBoards.find((b) => b.industry_code === code);
    if (!board) return;
    selectedBoards.set(code, board);
    renderSelectedTags();
    elSearch.value = "";
    hideDropdown();
  }

  function removeBoard(code) {
    selectedBoards.delete(code);
    renderSelectedTags();
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
    elHead.innerHTML =
      columns.map((c) => `<th>${c.label}</th>`).join("") + `<th>K线分析</th>`;
  }

  function boardKlineCell(row) {
    const code = row.industry_code;
    if (!code) return "<td>—</td>";
    const link = window.DcBoard && window.DcBoard.klineLink;
    if (!link) return "<td>—</td>";
    return `<td>${link("board", code, elDate.value)}</td>`;
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
          columns.map((c) => renderCell(row, c)).join("") +
          boardKlineCell(row) +
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
    allBoards = data.boards;
    const keep = new Map();
    selectedBoards.forEach((b, code) => {
      if (allBoards.some((x) => x.industry_code === code)) keep.set(code, b);
    });
    selectedBoards.clear();
    keep.forEach((b, code) => selectedBoards.set(code, b));
    renderSelectedTags();
    const sortPart = sortHint ? `；${sortHint}` : "";
    elHint.textContent = `共 ${allBoards.length} 个板块；未选板块表示全部${sortPart}`;
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
    selectedBoards.clear();
    elSearch.value = "";
    hideDropdown();
    renderSelectedTags();
  });

  elDate.addEventListener("change", () => {
    loadBoards().then(() => loadData()).catch((err) => showError(err.message));
  });

  elSearch.addEventListener("input", onSearchInput);
  elSearch.addEventListener("focus", onSearchInput);

  elDropdown.addEventListener("click", (e) => {
    const btn = e.target.closest(".board-option[data-code]");
    if (!btn) return;
    addBoard(btn.dataset.code);
  });

  elSelected.addEventListener("click", (e) => {
    const tag = e.target.closest(".board-tag");
    if (!tag) return;
    if (e.target.tagName === "BUTTON") removeBoard(tag.dataset.code);
  });

  document.addEventListener("click", (e) => {
    if (!elPicker.contains(e.target)) hideDropdown();
  });

  renderHead();
  renderSelectedTags();
  loadTradeDates()
    .then(() => loadBoards())
    .then(() => loadData())
    .catch((err) => showError(err.message));
})();
