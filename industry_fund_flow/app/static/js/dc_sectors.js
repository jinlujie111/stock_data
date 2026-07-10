(function () {
  const board = window.DcBoard;
  if (!board) return;

  const { fmtNum, apiGet, toApiTradeDate, initTradeDateCalendar, klineLink } = board;

  function sectorTable() {
    return window.DcSectorTable;
  }

  function requireSectorTable() {
    const st = sectorTable();
    if (!st) throw new Error("表格脚本未加载，请强制刷新页面（Ctrl+F5）");
    return st;
  }

  const elDate = document.getElementById("trade-date");
  const typeChips = document.getElementById("content-type-chips");
  const elBoardSearch = document.getElementById("board-search");
  const elBoardDropdown = document.getElementById("board-dropdown");
  const elBoardSelected = document.getElementById("board-selected");
  const elBoardPicker = document.getElementById("board-picker");
  const elSectorHeadRow = document.getElementById("sector-head-row");
  const elSectorBody = document.getElementById("sector-body");
  const elSectorEmpty = document.getElementById("sector-empty");
  const elSectorUpdated = document.getElementById("sector-updated");
  const elPageError = document.getElementById("page-error");
  const elFilterHint = document.getElementById("filter-hint");
  const btnQuery = document.getElementById("btn-query");
  const elMembersCard = document.getElementById("members-card");
  const elMembersTitle = document.getElementById("members-title");
  const elMembersBody = document.getElementById("members-body");
  const elMembersEmpty = document.getElementById("members-empty");
  const btnCloseMembers = document.getElementById("btn-close-members");
  const btnResetBoards = document.getElementById("btn-reset-boards");

  let contentType = "行业";
  let boardFavCodes = new Set();
  let stockFavCodes = new Set();
  let tableRows = [];
  let allBoards = [];
  const selectedBoards = new Map();
  let boardSearchTimer = null;
  const sortState = { sortKey: "pct_change", sortDir: "desc" };

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

  if (typeChips) {
    typeChips.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      typeChips.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      contentType = btn.dataset.value || "行业";
      loadBoardOptions().catch(() => {});
    });
  }

  function boardLabel(b) {
    return `[${b.content_type}] ${b.industry_name} (${b.industry_code})`;
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

  function selectedBoardCodes() {
    return Array.from(selectedBoards.keys());
  }

  function hideDropdown() {
    elBoardDropdown.classList.add("hidden");
  }

  function matchBoard(board, q) {
    const text = `${board.industry_name} ${board.industry_code} ${board.content_type}`.toLowerCase();
    const tokens = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!tokens.length) return true;
    return tokens.every((t) => text.includes(t));
  }

  function renderDropdown(matches) {
    if (!matches.length) {
      elBoardDropdown.innerHTML = '<div class="board-option">无匹配板块</div>';
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
    const params = new URLSearchParams();
    const td = tdParam();
    if (td) params.set("trade_date", td);
    params.set("content_types", contentType);
    const kw = (keyword || "").trim();
    if (kw) params.set("keyword", kw);
    const data = await apiGet(`/api/v1/dragon/boards?${params}`);
    return data.items || [];
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
  }

  function addBoard(code) {
    const board = allBoards.find((b) => b.industry_code === code);
    if (!board) return;
    selectedBoards.set(code, board);
    renderSelectedTags();
    elBoardSearch.value = "";
    hideDropdown();
  }

  function buildListUrl() {
    const params = new URLSearchParams();
    const td = tdParam();
    if (td) params.set("trade_date", td);
    params.set("content_type", contentType);
    const codes = selectedBoardCodes();
    if (codes.length) params.set("industry_codes", codes.join(","));
    return `/api/v1/sectors/list?${params}`;
  }

  function applySortAndRender(meta) {
    const st = requireSectorTable();
    const sorted = st.sortItems(tableRows, sortState.sortKey, sortState.sortDir);
    st.renderTableHead(elSectorHeadRow, sortState.sortKey, sortState.sortDir);
    st.bindSortHeaders(elSectorHeadRow.closest("thead"), sortState, () => {
      applySortAndRender(meta);
    });
    st.renderTableBody(elSectorBody, sorted, { boardFavCodes, tradeDate: elDate.value });
    elSectorUpdated.textContent = st.toolbarText(meta, sortState.sortKey, sortState.sortDir, sorted.length);
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
        toggleBoardFav(btn.dataset.code, btn.dataset.name, btn.dataset.ct, btn);
      });
    });
  }

  async function loadMembers(code, name) {
    clearError();
    const st = requireSectorTable();
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
          .map((row) => {
            const isFav = stockFavCodes.has(row.ts_code);
            return `
          <tr>
            <td>${row.ts_code || "—"}</td>
            <td>${row.stock_name || "—"}</td>
            <td class="${st.cellClass(row.pct_chg)}">${st.fmtPctCell(row.pct_chg)}</td>
            <td>${row.close != null ? fmtNum(row.close, 2) : "—"}</td>
            <td>${row.amount_yi != null ? st.fmtYi(row.amount_yi) : "—"}</td>
            <td>${row.turnover_rate != null ? fmtNum(row.turnover_rate, 2) + "%" : "—"}</td>
            <td>${row.pe_ttm != null ? fmtNum(row.pe_ttm, 2) : "—"}</td>
            <td class="${st.cellClass(row.net_mf_yi)}">${row.net_mf_yi != null ? st.fmtYi(row.net_mf_yi) : "—"}</td>
            <td><button type="button" class="star-btn${isFav ? " is-fav" : ""}" data-ts="${row.ts_code}" data-name="${row.stock_name || ""}">★</button></td>
            <td>${klineLink("stock", row.ts_code, elDate.value)}</td>
          </tr>`;
          })
          .join("");
        elMembersBody.querySelectorAll(".star-btn").forEach((btn) => {
          btn.addEventListener("click", () => toggleStockFav(btn.dataset.ts, btn.dataset.name, btn));
        });
      }
      elMembersCard.classList.remove("hidden");
      elMembersCard.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      showError(err.message);
    }
  }

  async function querySectors() {
    clearError();
    elFilterHint.textContent = "查询中…";
    try {
      const data = await apiGet(buildListUrl());
      renderSectorTable(data);
      elFilterHint.textContent = "";
    } catch (err) {
      elFilterHint.textContent = "";
      showError(err.message);
    }
  }

  async function refreshFavCodes() {
    try {
      const td = tdParam();
      const q = td ? `?trade_date=${td}` : "";
      const [boards, stocks] = await Promise.all([
        apiGet(`/api/v1/favorites/boards${q}`),
        apiGet(`/api/v1/favorites/stocks${td ? `?trade_date=${td}` : ""}`),
      ]);
      boardFavCodes = new Set(boards.items.map((x) => x.industry_code));
      stockFavCodes = new Set(stocks.items.map((x) => x.ts_code));
    } catch (_) {
      /* 自选接口失败不影响板块列表 */
    }
  }

  async function addBoardFav(code, name, ct) {
    await apiPost("/api/v1/favorites/boards", {
      industry_code: code,
      industry_name: name || null,
      content_type: ct || null,
    });
    await refreshFavCodes();
  }

  async function removeBoardFav(code) {
    await apiDelete(`/api/v1/favorites/boards/${encodeURIComponent(code)}`);
    await refreshFavCodes();
  }

  async function toggleBoardFav(code, name, ct, btn) {
    try {
      if (boardFavCodes.has(code)) {
        await removeBoardFav(code);
        if (btn) btn.classList.remove("is-fav");
      } else {
        await addBoardFav(code, name, ct);
        if (btn) btn.classList.add("is-fav");
      }
    } catch (err) {
      showError(err.message);
    }
  }

  async function addStockFav(tsCode, name) {
    await apiPost("/api/v1/favorites/stocks", { ts_code: tsCode, stock_name: name || null });
    await refreshFavCodes();
  }

  async function removeStockFav(tsCode) {
    await apiDelete(`/api/v1/favorites/stocks/${encodeURIComponent(tsCode)}`);
    await refreshFavCodes();
  }

  async function toggleStockFav(tsCode, name, btn) {
    try {
      if (stockFavCodes.has(tsCode)) {
        await removeStockFav(tsCode);
        if (btn) btn.classList.remove("is-fav");
      } else {
        await addStockFav(tsCode, name);
        if (btn) btn.classList.add("is-fav");
      }
    } catch (err) {
      showError(err.message);
    }
  }

  btnQuery.addEventListener("click", async () => {
    await refreshFavCodes();
    await querySectors();
  });
  btnCloseMembers.addEventListener("click", () => elMembersCard.classList.add("hidden"));
  elBoardSearch.addEventListener("input", () => {
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
        const matches = pool.filter((b) => !selectedBoards.has(b.industry_code) && matchBoard(b, q));
        renderDropdown(matches);
      } catch (err) {
        showError(err.message);
      }
    }, 200);
  });
  elBoardSearch.addEventListener("focus", () => {
    if (elBoardSearch.value.trim()) elBoardSearch.dispatchEvent(new Event("input"));
  });
  elBoardSearch.addEventListener("keydown", (e) => {
    if (e.key === "Enter") btnQuery.click();
  });
  elBoardDropdown.addEventListener("click", async (e) => {
    const btn = e.target.closest(".board-option[data-code]");
    if (!btn) return;
    const code = btn.dataset.code;
    if (!allBoards.some((b) => b.industry_code === code)) {
      const found = await fetchBoards(code);
      const board = found.find((b) => b.industry_code === code);
      if (board) allBoards.push(board);
    }
    addBoard(code);
  });
  elBoardSelected.addEventListener("click", (e) => {
    const tag = e.target.closest(".board-tag");
    if (!tag) return;
    if (e.target.tagName === "BUTTON") {
      selectedBoards.delete(tag.dataset.code);
      renderSelectedTags();
    }
  });
  btnResetBoards.addEventListener("click", () => {
    selectedBoards.clear();
    elBoardSearch.value = "";
    hideDropdown();
    renderSelectedTags();
    querySectors();
  });
  document.addEventListener("click", (e) => {
    if (!elBoardPicker.contains(e.target)) hideDropdown();
  });

  (async function init() {
    try {
      if (!sectorTable()) {
        showError("表格脚本未加载，请强制刷新页面（Ctrl+F5）");
        return;
      }
      sortState.sortKey = sectorTable().DEFAULT_SORT.key;
      sortState.sortDir = sectorTable().DEFAULT_SORT.dir;
      await initTradeDateCalendar(elDate, "/api/v1/sectors/trade-dates?limit=90");
      await loadBoardOptions();
      await querySectors();
      refreshFavCodes();
    } catch (err) {
      showError(err.message);
      try {
        await querySectors();
      } catch (_) {
        /* ignore */
      }
    }
  })();
})();
