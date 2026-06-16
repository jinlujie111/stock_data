(function () {
  const elDate = document.getElementById("trade-date");
  const chipGroup = document.getElementById("content-type-chips");
  const elBoardSearch = document.getElementById("board-search");
  const elBoardDropdown = document.getElementById("board-dropdown");
  const elBoardSelected = document.getElementById("board-selected");
  const elBoardPicker = document.getElementById("board-picker");
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

  function fmtNum(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(1);
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

  function onBoardSearchInput() {
    const q = elBoardSearch.value;
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
    elBoardSearch.value = "";
    hideDropdown();
  }

  async function loadBoardOptions() {
    const td = elDate.value;
    if (!td) return;
    const params = new URLSearchParams({
      trade_date: td,
      content_types: getContentTypesParam(),
    });
    const res = await fetch(`/api/v1/dragon/boards?${params}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "加载板块失败");
    allBoards = data.items || [];
    const keep = new Map();
    selectedBoards.forEach((b, code) => {
      if (allBoards.some((x) => x.industry_code === code)) keep.set(code, b);
    });
    selectedBoards.clear();
    keep.forEach((b, code) => selectedBoards.set(code, b));
    renderSelectedTags();
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
        loadBoardOptions().catch((e) => showError(e.message || String(e)));
      });
    });
  }

  async function loadTradeDates() {
    const res = await fetch("/api/v1/dragon/trade-dates");
    if (!res.ok) throw new Error("加载交易日失败");
    const data = await res.json();
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
    const res = await fetch(`/api/v1/dragon/leaders?${params}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "加载龙头榜失败");
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
    const [sumRes, scoreRes] = await Promise.all([
      fetch(`/api/v1/dragon/boards/${encodeURIComponent(industryCode)}/summary?trade_date=${td}`),
      fetch(
        `/api/v1/dragon/boards/${encodeURIComponent(industryCode)}/scores?trade_date=${td}` +
          `&top=10&sort=${encodeURIComponent(detailSort)}&order=${encodeURIComponent(detailOrder)}`
      ),
    ]);
    const summary = await sumRes.json();
    const scores = await scoreRes.json();
    if (!sumRes.ok) throw new Error(summary.detail || "加载摘要失败");
    if (!scoreRes.ok) throw new Error(scores.detail || "加载评分明细失败");
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
  });
  elBoardSearch.addEventListener("input", onBoardSearchInput);
  elBoardSearch.addEventListener("focus", onBoardSearchInput);
  elBoardDropdown.addEventListener("click", (e) => {
    const btn = e.target.closest(".board-option[data-code]");
    if (!btn) return;
    addBoard(btn.dataset.code);
  });
  elBoardSelected.addEventListener("click", (e) => {
    const tag = e.target.closest(".board-tag");
    if (!tag) return;
    if (e.target.tagName === "BUTTON") {
      selectedBoards.delete(tag.dataset.code);
      renderSelectedTags();
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
