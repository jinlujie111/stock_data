(function () {
  const { fmtNum, apiGet, toApiTradeDate, initTradeDateCalendar, klineLink } = window.DcBoard;
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
  const elAddPicker = document.getElementById("board-add-picker");
  const elAddSearch = document.getElementById("board-add-search");
  const elAddDropdown = document.getElementById("board-add-dropdown");
  const elFilterHint = document.getElementById("filter-hint");
  const elSectorHeadRow = document.getElementById("sector-head-row");
  const elSectorBody = document.getElementById("sector-body");
  const elSectorEmpty = document.getElementById("sector-empty");
  const elSectorUpdated = document.getElementById("sector-updated");
  const elPageError = document.getElementById("page-error");
  const btnQuery = document.getElementById("btn-query");
  const elMembersCard = document.getElementById("members-card");
  const elMembersTitle = document.getElementById("members-title");
  const elMembersBody = document.getElementById("members-body");
  const elMembersEmpty = document.getElementById("members-empty");
  const btnCloseMembers = document.getElementById("btn-close-members");

  let boardFavCodes = new Set();
  let tableRows = [];
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
    return `[${b.content_type || "—"}] ${b.industry_name} (${b.industry_code})`;
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
    if (elFilterHint) {
      elFilterHint.textContent = `共 ${data.items.length} 个自选板块`;
    }
  }

  function buildTableUrl() {
    const params = new URLSearchParams();
    const td = tdParam();
    if (td) params.set("trade_date", td);
    return `/api/v1/favorites/boards/table?${params}`;
  }

  function applySortAndRender(meta) {
    const sorted = sortItems(tableRows, sortState.sortKey, sortState.sortDir);
    renderTableHead(elSectorHeadRow, sortState.sortKey, sortState.sortDir);
    bindSortHeaders(elSectorHeadRow.closest("thead"), sortState, () => applySortAndRender(meta));
    renderTableBody(elSectorBody, sorted, { boardFavCodes, tradeDate: elDate.value });
    elSectorUpdated.textContent = toolbarText(meta, sortState.sortKey, sortState.sortDir, sorted.length);
    bindSectorActions();
  }

  function renderSectorTable(data) {
    tableRows = data.items || [];
    if (!tableRows.length) {
      elSectorBody.innerHTML = "";
      elSectorEmpty.classList.remove("hidden");
      elSectorUpdated.textContent = `交易日 ${data.trade_date} · 0 条`;
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
            <td>${klineLink("stock", row.ts_code, elDate.value)}</td>
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

  btnQuery.addEventListener("click", queryTable);
  btnCloseMembers.addEventListener("click", () => elMembersCard.classList.add("hidden"));
  elAddSearch.addEventListener("input", onAddBoardInput);
  elDate.addEventListener("change", () => queryTable());
  document.addEventListener("click", (e) => {
    if (elAddPicker && !elAddPicker.contains(e.target)) hideDropdown(elAddDropdown);
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
