(function () {
  const { fmtNum, apiGet, toApiTradeDate, initTradeDateCalendar } = window.DcBoard;
  const {
    DEFAULT_SORT,
    fmtPctCell,
    fmtYi,
    cellClass,
    sortItems,
    renderTableHead,
    bindSortHeaders,
    renderTableBody,
    toolbarText,
  } = window.DcSectorTable;

  const elDate = document.getElementById("trade-date");
  const typeChips = document.getElementById("content-type-chips");
  const elBoardSearch = document.getElementById("board-search");
  const elBoardDropdown = document.getElementById("board-dropdown");
  const elBoardSelected = document.getElementById("board-selected");
  const elBoardPicker = document.getElementById("board-picker");
  const elAddSearch = document.getElementById("board-add-search");
  const elAddDropdown = document.getElementById("board-add-dropdown");
  const elFilterHint = document.getElementById("filter-hint");
  const elSectorHeadRow = document.getElementById("sector-head-row");
  const elSectorBody = document.getElementById("sector-body");
  const elSectorEmpty = document.getElementById("sector-empty");
  const elSectorUpdated = document.getElementById("sector-updated");
  const elPageError = document.getElementById("page-error");
  const btnQuery = document.getElementById("btn-query");
  const btnResetBoards = document.getElementById("btn-reset-boards");
  const elMembersCard = document.getElementById("members-card");
  const elMembersTitle = document.getElementById("members-title");
  const elMembersBody = document.getElementById("members-body");
  const elMembersEmpty = document.getElementById("members-empty");
  const btnCloseMembers = document.getElementById("btn-close-members");

  let contentType = "行业";
  let allBoards = [];
  const selectedBoards = new Map();
  let boardFavCodes = new Set();
  let tableRows = [];
  let boardSearchTimer = null;
  let addSearchTimer = null;
  const sortState = { sortKey: DEFAULT_SORT.key, sortDir: DEFAULT_SORT.dir };

  function tdParam() {
    return elDate.value ? toApiTradeDate(elDate.value) : "";
  }

  function showError(msg) {
    elPageError.textContent = msg;
    elPageError.classList.remove("hidden");
  }

  function clearError() {
    elPageError.classList.add("hidden");
  }

  async function apiPost(path, body) {
    const res = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "请求失败");
    return data;
  }

  async function apiDelete(path) {
    const res = await fetch(path, { method: "DELETE", credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "请求失败");
    return data;
  }

  function boardLabel(b) {
    return `[${b.content_type || contentType}] ${b.industry_name} (${b.industry_code})`;
  }

  function selectedBoardCodes() {
    return Array.from(selectedBoards.keys());
  }

  function matchBoard(board, q) {
    const text = `${board.industry_name} ${board.industry_code} ${board.content_type || ""}`.toLowerCase();
    const tokens = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!tokens.length) return true;
    return tokens.every((t) => text.includes(t));
  }

  function renderSelectedTags() {
    if (!selectedBoards.size) {
      elBoardSelected.innerHTML = '<span class="board-placeholder">未选择（展示全部自选板块）</span>';
      return;
    }
    elBoardSelected.innerHTML = Array.from(selectedBoards.values())
      .map(
        (b) =>
          `<span class="board-tag" data-code="${b.industry_code}">${boardLabel(b)}<button type="button" aria-label="移除">×</button></span>`
      )
      .join("");
  }

  function hideDropdown(el) {
    el.classList.add("hidden");
  }

  function renderDropdown(el, matches, onPick) {
    if (!matches.length) {
      el.innerHTML = '<div class="board-option board-option--empty">无匹配板块</div>';
      el.classList.remove("hidden");
      return;
    }
    el.innerHTML = matches
      .slice(0, 50)
      .map(
        (b) =>
          `<button type="button" class="board-option" data-code="${b.industry_code}">${boardLabel(b)}</button>`
      )
      .join("");
    el.classList.remove("hidden");
    el.querySelectorAll(".board-option[data-code]").forEach((btn) => {
      btn.addEventListener("click", () => onPick(btn.dataset.code));
    });
  }

  async function loadFavoriteBoardMeta() {
    const data = await apiGet("/api/v1/favorites/boards");
    boardFavCodes = new Set(data.items.map((x) => x.industry_code));
    allBoards = data.items.map((x) => ({
      industry_code: x.industry_code,
      industry_name: x.industry_name || x.industry_code,
      content_type: x.content_type || contentType,
    }));
    const keep = new Map();
    selectedBoards.forEach((b, code) => {
      if (allBoards.some((x) => x.industry_code === code)) keep.set(code, b);
    });
    selectedBoards.clear();
    keep.forEach((b, code) => selectedBoards.set(code, b));
    renderSelectedTags();
    if (elFilterHint) {
      elFilterHint.textContent = `共 ${allBoards.length} 个自选板块；筛选后点「查询」刷新表格`;
    }
  }

  function addFilterBoard(code) {
    const board = allBoards.find((b) => b.industry_code === code);
    if (!board || selectedBoards.has(code)) return;
    selectedBoards.set(code, board);
    renderSelectedTags();
    elBoardSearch.value = "";
    hideDropdown(elBoardDropdown);
  }

  function buildTableUrl() {
    const params = new URLSearchParams();
    const td = tdParam();
    if (td) params.set("trade_date", td);
    params.set("content_type", contentType);
    const codes = selectedBoardCodes();
    if (codes.length) params.set("industry_codes", codes.join(","));
    return `/api/v1/favorites/boards/table?${params}`;
  }

  function applySortAndRender(meta) {
    const sorted = sortItems(tableRows, sortState.sortKey, sortState.sortDir);
    renderTableHead(elSectorHeadRow, sortState.sortKey, sortState.sortDir);
    bindSortHeaders(elSectorHeadRow.closest("thead"), sortState, () => applySortAndRender(meta));
    renderTableBody(elSectorBody, sorted, { boardFavCodes });
    elSectorUpdated.textContent = toolbarText(meta, sortState.sortKey, sortState.sortDir, sorted.length);
    bindSectorActions();
  }

  function renderSectorTable(data) {
    tableRows = data.items || [];
    if (!tableRows.length) {
      elSectorBody.innerHTML = "";
      elSectorEmpty.classList.remove("hidden");
      elSectorUpdated.textContent = `交易日 ${data.trade_date} · ${data.content_type} · 0 条`;
      return;
    }
    elSectorEmpty.classList.add("hidden");
    applySortAndRender(data);
  }

  function bindSectorActions() {
    elSectorBody.querySelectorAll("[data-action=members]").forEach((btn) => {
      btn.addEventListener("click", () => loadMembers(btn.dataset.code, btn.dataset.name));
    });
    elSectorBody.querySelectorAll("[data-action=fav-board]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        removeBoardFav(btn.dataset.code).then(() => queryTable()).catch((err) => showError(err.message));
      });
    });
  }

  async function loadMembers(code, name) {
    clearError();
    try {
      const td = tdParam();
      const q = td ? `?trade_date=${td}` : "";
      const data = await apiGet(`/api/v1/sectors/${encodeURIComponent(code)}/members${q}`);
      elMembersTitle.textContent = `${name || data.industry_name || code} · 成分股（${data.trade_date}）`;
      if (!data.items.length) {
        elMembersBody.innerHTML = "";
        elMembersEmpty.classList.remove("hidden");
      } else {
        elMembersEmpty.classList.add("hidden");
        elMembersBody.innerHTML = data.items
          .map(
            (row) => `
          <tr>
            <td>${row.ts_code || "—"}</td>
            <td>${row.stock_name || "—"}</td>
            <td class="${cellClass(row.pct_chg)}">${fmtPctCell(row.pct_chg)}</td>
            <td>${row.close != null ? fmtNum(row.close, 2) : "—"}</td>
            <td>${row.amount_yi != null ? fmtYi(row.amount_yi) : "—"}</td>
            <td>${row.turnover_rate != null ? fmtNum(row.turnover_rate, 2) + "%" : "—"}</td>
            <td>${row.pe_ttm != null ? fmtNum(row.pe_ttm, 2) : "—"}</td>
            <td class="${cellClass(row.net_mf_yi)}">${row.net_mf_yi != null ? fmtYi(row.net_mf_yi) : "—"}</td>
          </tr>`
          )
          .join("");
      }
      elMembersCard.classList.remove("hidden");
      elMembersCard.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      showError(err.message);
    }
  }

  async function queryTable() {
    clearError();
    try {
      const data = await apiGet(buildTableUrl());
      renderSectorTable(data);
    } catch (err) {
      showError(err.message);
    }
  }

  async function removeBoardFav(code) {
    await apiDelete(`/api/v1/favorites/boards/${encodeURIComponent(code)}`);
    await loadFavoriteBoardMeta();
  }

  async function addBoardFav(item) {
    await apiPost("/api/v1/favorites/boards", {
      industry_code: item.industry_code,
      industry_name: item.industry_name || null,
      content_type: item.content_type || null,
    });
    elAddSearch.value = "";
    hideDropdown(elAddDropdown);
    await loadFavoriteBoardMeta();
    await queryTable();
  }

  function onBoardFilterInput() {
    const q = elBoardSearch.value;
    if (!q.trim()) {
      hideDropdown(elBoardDropdown);
      return;
    }
    clearTimeout(boardSearchTimer);
    boardSearchTimer = setTimeout(() => {
      const matches = allBoards.filter(
        (b) => !selectedBoards.has(b.industry_code) && matchBoard(b, q)
      );
      renderDropdown(elBoardDropdown, matches, addFilterBoard);
    }, 200);
  }

  function onAddBoardInput() {
    const q = elAddSearch.value.trim();
    if (!q) {
      hideDropdown(elAddDropdown);
      return;
    }
    clearTimeout(addSearchTimer);
    addSearchTimer = setTimeout(async () => {
      try {
        const td = tdParam();
        const params = new URLSearchParams({ keyword: q });
        if (td) params.set("trade_date", td);
        const data = await apiGet(`/api/v1/sectors/lookup/board?${params}`);
        const items = (data.items || []).filter((b) => !boardFavCodes.has(b.industry_code));
        renderDropdown(elAddDropdown, items, async (code) => {
          const item = (data.items || []).find((b) => b.industry_code === code);
          if (item) await addBoardFav(item);
        });
      } catch (err) {
        showError(err.message);
      }
    }, 250);
  }

  if (typeChips) {
    typeChips.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      typeChips.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      contentType = btn.dataset.value || "行业";
    });
  }

  btnQuery.addEventListener("click", queryTable);
  btnResetBoards.addEventListener("click", () => {
    selectedBoards.clear();
    elBoardSearch.value = "";
    hideDropdown(elBoardDropdown);
    renderSelectedTags();
    queryTable();
  });
  btnCloseMembers.addEventListener("click", () => elMembersCard.classList.add("hidden"));
  elBoardSearch.addEventListener("input", onBoardFilterInput);
  elBoardSearch.addEventListener("focus", onBoardFilterInput);
  elAddSearch.addEventListener("input", onAddBoardInput);
  elBoardSelected.addEventListener("click", (e) => {
    const tag = e.target.closest(".board-tag");
    if (!tag || e.target.tagName !== "BUTTON") return;
    selectedBoards.delete(tag.dataset.code);
    renderSelectedTags();
  });
  document.addEventListener("click", (e) => {
    if (elBoardPicker && !elBoardPicker.contains(e.target)) hideDropdown(elBoardDropdown);
    if (elAddSearch && !elAddSearch.parentElement.contains(e.target)) hideDropdown(elAddDropdown);
  });

  (async function init() {
    try {
      await initTradeDateCalendar(elDate, "/api/v1/sectors/trade-dates?limit=90");
      await loadFavoriteBoardMeta();
      await queryTable();
    } catch (err) {
      showError(err.message);
    }
  })();
})();
