(function () {
  const elDate = document.getElementById("trade-date");
  const chipGroup = document.getElementById("content-type-chips");
  const elBoardSearch = document.getElementById("board-search");
  const elBoardDropdown = document.getElementById("board-dropdown");
  const elBoardSelected = document.getElementById("board-selected");
  const elBoardPicker = document.getElementById("board-picker");
  const elFilterHint = document.getElementById("filter-hint");
  const elLeadersBody = document.getElementById("leaders-body");
  const elLeadersEmpty = document.getElementById("leaders-empty");
  const elLeadersUpdated = document.getElementById("leaders-updated");
  const elPageError = document.getElementById("page-error");
  const elDetailCard = document.getElementById("detail-card");
  const elDetailTitle = document.getElementById("detail-title");
  const elSummary = document.getElementById("summary-text");
  const elScoresBody = document.getElementById("scores-body");
  const detailSortableHeaders = Array.from(document.querySelectorAll("#scores-table .sortable-th"));
  const btnQuery = document.getElementById("btn-query");
  const btnClose = document.getElementById("btn-close-detail");
  const btnResetBoards = document.getElementById("btn-reset-boards");

  let selectedTypes = ["行业", "概念"];
  let allBoards = [];
  const selectedBoards = new Map();
  let currentIndustryCode = "";
  let detailSort = "composite";
  let detailOrder = "desc";
  let boardSearchTimer = null;

  function fmtNum(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(1);
  }

  async function apiGet(path) {
    const res = await fetch(path, { credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "请求失败");
    return data;
  }

  function showError(msg) {
    elPageError.textContent = msg;
    elPageError.classList.remove("hidden");
  }

  function clearError() {
    elPageError.classList.add("hidden");
  }

  function getContentTypesParam() {
    return selectedTypes.length ? selectedTypes.join(",") : "行业,概念";
  }

  function boardLabel(b) {
    return `[${b.content_type}] ${b.industry_name} (${b.industry_code})`;
  }

  function selectedBoardCodes() {
    return Array.from(selectedBoards.keys());
  }

  function matchBoard(board, q) {
    const text = `${board.industry_name} ${board.industry_code} ${board.content_type}`.toLowerCase();
    const tokens = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!tokens.length) return true;
    return tokens.every((t) => text.includes(t));
  }

  function renderSelectedTags() {
    if (!selectedBoards.size) {
      elBoardSelected.innerHTML = '<span class="board-placeholder">未选择板块（展示全部）</span>';
      return;
    }
    elBoardSelected.innerHTML = Array.from(selectedBoards.values())
      .map(
        (b) =>
          `<span class="board-tag" data-code="${b.industry_code}">` +
          `${boardLabel(b)}<button type="button" aria-label="移除">×</button></span>`
      )
      .join("");
  }

  function updateFilterHint() {
    if (!elFilterHint) return;
    const typeHint = getContentTypesParam().replace(",", "、");
    elFilterHint.textContent = `共 ${allBoards.length} 个板块可选；输入名称或代码模糊匹配后点选；未选板块表示全部（类型：${typeHint}）`;
  }

  function hideDropdown() {
    elBoardDropdown.classList.add("hidden");
  }

  function renderDropdown(matches) {
    if (!matches.length) {
      elBoardDropdown.innerHTML = '<div class="board-option board-option--empty">无匹配板块</div>';
      elBoardDropdown.classList.remove("hidden");
      return;
    }
    elBoardDropdown.innerHTML = matches
      .slice(0, 50)
      .map(
        (b) =>
          `<button type="button" class="board-option" data-code="${b.industry_code}">` +
          `${boardLabel(b)}</button>`
      )
      .join("");
    elBoardDropdown.classList.remove("hidden");
  }

  async function fetchBoards(keyword) {
    const td = elDate.value;
    if (!td) return [];
    const params = new URLSearchParams({
      trade_date: td,
      content_types: getContentTypesParam(),
    });
    const kw = (keyword || "").trim();
    if (kw) params.set("keyword", kw);
    const data = await apiGet(`/api/v1/dragon/boards?${params}`);
    return data.items || [];
  }

  function onBoardSearchInput() {
    const q = elBoardSearch.value;
    if (!q.trim()) {
      hideDropdown();
      return;
    }
    clearTimeout(boardSearchTimer);
    boardSearchTimer = setTimeout(async () => {
      try {
        const remote = await fetchBoards(q);
        const pool = remote.length ? remote : allBoards;
        const matches = pool.filter(
          (b) => !selectedBoards.has(b.industry_code) && matchBoard(b, q)
        );
        renderDropdown(matches);
      } catch (e) {
        const matches = allBoards.filter(
          (b) => !selectedBoards.has(b.industry_code) && matchBoard(b, q)
        );
        renderDropdown(matches);
        if (!matches.length) showError(e.message || String(e));
      }
    }, 200);
  }

  function addBoard(code) {
    const board = allBoards.find((b) => b.industry_code === code);
    if (!board) return;
    selectedBoards.set(code, board);
    renderSelectedTags();
    elBoardSearch.value = "";
    hideDropdown();
    refresh();
  }

  async function loadBoardOptions() {
    allBoards = await fetchBoards("");
    const keep = new Map();
    selectedBoards.forEach((b, code) => {
      if (allBoards.some((x) => x.industry_code === code)) keep.set(code, b);
    });
    selectedBoards.clear();
    keep.forEach((b, code) => selectedBoards.set(code, b));
    renderSelectedTags();
    updateFilterHint();
  }

  function bindChips() {
    chipGroup.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const val = chip.dataset.value;
        if (chip.classList.contains("active")) {
          chip.classList.remove("active");
          selectedTypes = selectedTypes.filter((t) => t !== val);
        } else {
          chip.classList.add("active");
          if (!selectedTypes.includes(val)) selectedTypes.push(val);
        }
        if (!selectedTypes.length) {
          selectedTypes = ["行业", "概念"];
          chipGroup.querySelectorAll(".chip").forEach((c) => {
            if (["行业", "概念"].includes(c.dataset.value)) c.classList.add("active");
          });
        }
        loadBoardOptions()
          .then(() => refresh())
          .catch((e) => showError(e.message || String(e)));
      });
    });
  }

  async function loadTradeDates() {
    const data = await apiGet("/api/v1/dragon/trade-dates");
    elDate.innerHTML = "";
    (data.dates || []).forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d;
      opt.textContent = d;
      elDate.appendChild(opt);
    });
    if (data.latest) elDate.value = data.latest;
  }

  async function loadLeaders() {
    clearError();
    const td = elDate.value;
    const params = new URLSearchParams({
      trade_date: td,
      content_types: getContentTypesParam(),
      top: "10",
    });
    const boardCodes = selectedBoardCodes();
    if (boardCodes.length) params.set("industry_codes", boardCodes.join(","));
    const data = await apiGet(`/api/v1/dragon/leaders?${params}`);
    elLeadersUpdated.textContent = `数据日期：${data.trade_date || td}`;
    const items = data.items || [];
    if (!items.length) {
      elLeadersBody.innerHTML = "";
      elLeadersEmpty.classList.remove("hidden");
      return;
    }
    elLeadersEmpty.classList.add("hidden");
    elLeadersBody.innerHTML = items
      .map(
        (r) =>
          `<tr>` +
          `<td>${r.content_type || "—"}</td>` +
          `<td>${r.industry_name || r.industry_code}</td>` +
          `<td>${r.leader_composite_name || "—"}</td>` +
          `<td>${fmtNum(r.score_composite)}</td>` +
          `<td>${r.leader_fund_name || "—"}</td>` +
          `<td>${r.leader_trend_name || "—"}</td>` +
          `<td><button type="button" class="btn btn-ghost btn-drill" data-code="${r.industry_code}">下钻</button></td>` +
          `</tr>`
      )
      .join("");
    elLeadersBody.querySelectorAll(".btn-drill").forEach((btn) => {
      btn.addEventListener("click", () => openDetail(btn.dataset.code));
    });
  }

  function markDetailSortHeaders() {
    detailSortableHeaders.forEach((th) => {
      const key = th.dataset.sort;
      const arrow = key === detailSort ? (detailOrder === "asc" ? " ▲" : " ▼") : "";
      const base = th.textContent.replace(/\s[▲▼]$/, "");
      th.textContent = `${base}${arrow}`;
    });
  }

  async function openDetail(industryCode) {
    clearError();
    currentIndustryCode = industryCode;
    const td = elDate.value;
    const [summary, scores] = await Promise.all([
      apiGet(`/api/v1/dragon/boards/${encodeURIComponent(industryCode)}/summary?trade_date=${td}`),
      apiGet(
        `/api/v1/dragon/boards/${encodeURIComponent(industryCode)}/scores?trade_date=${td}` +
          `&top=10&sort=${encodeURIComponent(detailSort)}&order=${encodeURIComponent(detailOrder)}`
      ),
    ]);
    elDetailTitle.textContent = `${summary.industry_name || industryCode} · 成分股评分`;
    elSummary.textContent = summary.summary_text || "";
    const items = scores.items || [];
    markDetailSortHeaders();
    elScoresBody.innerHTML = items
      .map(
        (r) =>
          `<tr${r.is_composite_leader ? ' class="row-leader"' : ""}>` +
          `<td>${r.stock_name || r.ts_code}</td>` +
          `<td>${r.ts_code || "—"}</td>` +
          `<td>${fmtNum(r.score_composite)}</td>` +
          `<td>${fmtNum(r.score_fund)}</td>` +
          `<td>${fmtNum(r.score_trend)}</td>` +
          `<td>${fmtNum(r.score_inst)}</td>` +
          `<td>${r.rank_composite ?? "—"}</td>` +
          `</tr>`
      )
      .join("");
    elDetailCard.classList.remove("hidden");
    elDetailCard.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function refresh() {
    try {
      await loadLeaders();
    } catch (e) {
      showError(e.message || String(e));
    }
  }

  btnQuery.addEventListener("click", refresh);
  btnClose.addEventListener("click", () => elDetailCard.classList.add("hidden"));
  btnResetBoards.addEventListener("click", () => {
    selectedBoards.clear();
    elBoardSearch.value = "";
    hideDropdown();
    renderSelectedTags();
    refresh();
  });
  elBoardSearch.addEventListener("input", onBoardSearchInput);
  elBoardSearch.addEventListener("focus", onBoardSearchInput);
  elBoardDropdown.addEventListener("click", async (e) => {
    const btn = e.target.closest(".board-option[data-code]");
    if (!btn) return;
    const code = btn.dataset.code;
    if (!allBoards.some((b) => b.industry_code === code)) {
      try {
        const found = await fetchBoards(code);
        const board = found.find((b) => b.industry_code === code);
        if (board) allBoards.push(board);
      } catch (err) {
        showError(err.message || String(err));
        return;
      }
    }
    addBoard(code);
  });
  elBoardSelected.addEventListener("click", (e) => {
    const tag = e.target.closest(".board-tag");
    if (!tag) return;
    if (e.target.tagName === "BUTTON") {
      selectedBoards.delete(tag.dataset.code);
      renderSelectedTags();
      refresh();
    }
  });
  detailSortableHeaders.forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (!key) return;
      if (detailSort === key) {
        detailOrder = detailOrder === "asc" ? "desc" : "asc";
      } else {
        detailSort = key;
        detailOrder = "desc";
      }
      if (currentIndustryCode) {
        openDetail(currentIndustryCode).catch((e) => showError(e.message || String(e)));
      }
    });
  });
  elDate.addEventListener("change", () => {
    loadBoardOptions()
      .then(() => refresh())
      .catch((e) => showError(e.message || String(e)));
  });
  document.addEventListener("click", (e) => {
    if (!elBoardPicker.contains(e.target)) hideDropdown();
  });

  bindChips();
  renderSelectedTags();
  loadTradeDates()
    .then(() => loadBoardOptions())
    .then(refresh)
    .catch((e) => showError(e.message || String(e)));
})();
