(function () {
  const { fmtNum, apiGet, toApiTradeDate, initTradeDateCalendar } = window.DcBoard;

  const elDate = document.getElementById("trade-date");
  const typeChips = document.getElementById("content-type-chips");
  const elBoardSearch = document.getElementById("board-search");
  const elBoardDropdown = document.getElementById("board-dropdown");
  const elBoardSelected = document.getElementById("board-selected");
  const elBoardPicker = document.getElementById("board-picker");
  const elStockPicker = document.getElementById("stock-picker");
  const elAddSearch = document.getElementById("stock-add-search");
  const elAddDropdown = document.getElementById("stock-add-dropdown");
  const elFilterHint = document.getElementById("filter-hint");
  const elStockBody = document.getElementById("stock-body");
  const elStockEmpty = document.getElementById("stock-empty");
  const elStockUpdated = document.getElementById("stock-updated");
  const elPageError = document.getElementById("page-error");
  const btnQuery = document.getElementById("btn-query");
  const btnResetBoards = document.getElementById("btn-reset-boards");

  let contentType = "行业";
  let allBoards = [];
  const selectedBoards = new Map();
  const memberCache = new Map();
  let stockFavCodes = new Set();
  let boardSearchTimer = null;
  let stockSearchTimer = null;

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

  function cellClass(v) {
    const n = Number(v);
    if (Number.isNaN(n) || v === null || v === "") return "";
    return n > 0 ? "cell-rise" : n < 0 ? "cell-fall" : "";
  }

  function fmtPctCell(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    const pct = Math.abs(n) <= 1 && Math.abs(n) !== 0 ? n * 100 : n;
    return pct.toFixed(2) + "%";
  }

  function fmtYi(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(2) + "亿";
  }

  function fmtWan(v, unit) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(2) + (unit || "万手");
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
    if (board.content_type && board.content_type !== contentType) return false;
    const text = `${board.industry_name} ${board.industry_code} ${board.content_type || ""}`.toLowerCase();
    const tokens = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!tokens.length) return true;
    return tokens.every((t) => text.includes(t));
  }

  function matchStock(stock, q) {
    const text = `${stock.stock_name || ""} ${stock.ts_code || ""}`.toLowerCase();
    const tokens = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!tokens.length) return true;
    return tokens.every((t) => text.includes(t));
  }

  function renderSelectedTags() {
    if (!selectedBoards.size) {
      elBoardSelected.innerHTML = '<span class="board-placeholder">未选择板块（添加股票时搜索全市场）</span>';
      updateFilterHint();
      return;
    }
    elBoardSelected.innerHTML = Array.from(selectedBoards.values())
      .map(
        (b) =>
          `<span class="board-tag" data-code="${b.industry_code}">${boardLabel(b)}<button type="button" aria-label="移除">×</button></span>`
      )
      .join("");
    updateFilterHint();
  }

  function updateFilterHint() {
    if (!elFilterHint) return;
    const n = selectedBoards.size;
    if (!n) {
      elFilterHint.textContent = `当前类型：${contentType} · 自选板块 ${allBoards.length} 个 · 未选板块时股票搜索全市场`;
      return;
    }
    elFilterHint.textContent = `当前类型：${contentType} · 已选 ${n} 个板块，股票搜索仅在这些板块成分股内匹配`;
  }

  async function loadFavoriteBoards() {
    const data = await apiGet("/api/v1/favorites/boards");
    allBoards = (data.items || []).map((x) => ({
      industry_code: x.industry_code,
      industry_name: x.industry_name || x.industry_code,
      content_type: x.content_type || contentType,
    }));
    updateFilterHint();
  }

  function hideDropdown(el) {
    el.classList.add("hidden");
  }

  function renderBoardDropdown(matches, onPick) {
    if (!matches.length) {
      elBoardDropdown.innerHTML = '<div class="board-option board-option--empty">无匹配板块</div>';
      elBoardDropdown.classList.remove("hidden");
      return;
    }
    elBoardDropdown.innerHTML = matches
      .slice(0, 50)
      .map(
        (b) =>
          `<button type="button" class="board-option" data-code="${b.industry_code}">${boardLabel(b)}</button>`
      )
      .join("");
    elBoardDropdown.classList.remove("hidden");
    elBoardDropdown.querySelectorAll(".board-option[data-code]").forEach((btn) => {
      btn.addEventListener("click", () => onPick(btn.dataset.code));
    });
  }

  function renderStockDropdown(items) {
    if (!items.length) {
      elAddDropdown.innerHTML = '<div class="board-option board-option--empty">无匹配或未添加的新股票</div>';
      elAddDropdown.classList.remove("hidden");
      return;
    }
    elAddDropdown.innerHTML = items
      .slice(0, 50)
      .map(
        (s) =>
          `<button type="button" class="board-option" data-code="${s.ts_code}">${s.stock_name || s.ts_code} (${s.ts_code})</button>`
      )
      .join("");
    elAddDropdown.classList.remove("hidden");
    elAddDropdown.querySelectorAll(".board-option[data-code]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = items.find((s) => s.ts_code === btn.dataset.code);
        if (item) addStockFav(item).catch((err) => showError(err.message));
      });
    });
  }

  function clearMemberCache() {
    memberCache.clear();
  }

  function addFilterBoard(code, board) {
    if (!board || selectedBoards.has(code)) return;
    selectedBoards.set(code, board);
    renderSelectedTags();
    elBoardSearch.value = "";
    hideDropdown(elBoardDropdown);
    clearMemberCache();
  }

  async function fetchBoardLookup(keyword) {
    const td = tdParam();
    const params = new URLSearchParams({ keyword });
    if (td) params.set("trade_date", td);
    const data = await apiGet(`/api/v1/sectors/lookup/board?${params}`);
    return (data.items || []).filter(
      (b) => (!b.content_type || b.content_type === contentType) && !selectedBoards.has(b.industry_code)
    );
  }

  async function fetchMembersForBoard(code) {
    if (memberCache.has(code)) return memberCache.get(code);
    const td = tdParam();
    const q = td ? `?trade_date=${td}` : "";
    const data = await apiGet(`/api/v1/sectors/${encodeURIComponent(code)}/members${q}`);
    const items = data.items || [];
    memberCache.set(code, items);
    return items;
  }

  async function getMemberPool() {
    const codes = selectedBoardCodes();
    if (!codes.length) return [];
    const seen = new Set();
    const merged = [];
    for (const code of codes) {
      const items = await fetchMembersForBoard(code);
      for (const m of items) {
        if (!m.ts_code || seen.has(m.ts_code)) continue;
        seen.add(m.ts_code);
        merged.push(m);
      }
    }
    return merged;
  }

  function onBoardSearchInput() {
    const q = elBoardSearch.value;
    if (!q.trim()) {
      hideDropdown(elBoardDropdown);
      return;
    }
    clearTimeout(boardSearchTimer);
    boardSearchTimer = setTimeout(async () => {
      try {
        let filtered = allBoards.filter(
          (b) => !selectedBoards.has(b.industry_code) && matchBoard(b, q)
        );
        if (filtered.length < 20) {
          const remote = await fetchBoardLookup(q.trim());
          const seen = new Set(filtered.map((b) => b.industry_code));
          for (const b of remote) {
            if (!seen.has(b.industry_code) && matchBoard(b, q)) {
              filtered.push(b);
              seen.add(b.industry_code);
            }
          }
        }
        renderBoardDropdown(filtered, (code) => {
          const board = filtered.find((b) => b.industry_code === code);
          if (board) addFilterBoard(code, board);
        });
      } catch (err) {
        showError(err.message);
      }
    }, 200);
  }

  function renderStockTable(data) {
    const items = data.items || [];
    stockFavCodes = new Set(items.map((x) => x.ts_code));
    elStockUpdated.textContent = `交易日 ${data.trade_date || "—"} · ${items.length} 条`;
    if (!items.length) {
      elStockBody.innerHTML = "";
      elStockEmpty.classList.remove("hidden");
      return;
    }
    elStockEmpty.classList.add("hidden");
    elStockBody.innerHTML = items
      .map(
        (row) => `
      <tr>
        <td>${row.ts_code || "—"}</td>
        <td>${row.stock_name || "—"}</td>
        <td>${row.close != null ? fmtNum(row.close, 2) : "—"}</td>
        <td>${row.total_mv_yi != null ? fmtYi(row.total_mv_yi) : "—"}</td>
        <td>${row.vol_wan != null ? fmtWan(row.vol_wan) : "—"}</td>
        <td>${row.amount_yi != null ? fmtYi(row.amount_yi) : "—"}</td>
        <td class="${cellClass(row.net_mf_today_yi)}">${row.net_mf_today_yi != null ? fmtYi(row.net_mf_today_yi) : "—"}</td>
        <td class="${cellClass(row.net_mf_5d_yi)}">${row.net_mf_5d_yi != null ? fmtYi(row.net_mf_5d_yi) : "—"}</td>
        <td class="${cellClass(row.net_mf_20d_yi)}">${row.net_mf_20d_yi != null ? fmtYi(row.net_mf_20d_yi) : "—"}</td>
        <td class="${cellClass(row.ytd_pct)}">${row.ytd_pct != null ? fmtPctCell(row.ytd_pct) : "—"}</td>
        <td><button type="button" class="btn btn-ghost btn-sm" data-del="${row.ts_code}">移除</button></td>
      </tr>`
      )
      .join("");
    elStockBody.querySelectorAll("[data-del]").forEach((btn) => {
      btn.addEventListener("click", () =>
        removeStockFav(btn.dataset.del).catch((err) => showError(err.message))
      );
    });
  }

  async function loadStocks() {
    clearError();
    const td = tdParam();
    const q = td ? `?trade_date=${td}` : "";
    const data = await apiGet(`/api/v1/favorites/stocks${q}`);
    renderStockTable(data);
  }

  async function addStockFav(item) {
    await apiPost("/api/v1/favorites/stocks", {
      ts_code: item.ts_code,
      stock_name: item.stock_name || null,
    });
    elAddSearch.value = "";
    hideDropdown(elAddDropdown);
    await loadStocks();
  }

  async function removeStockFav(tsCode) {
    await apiDelete(`/api/v1/favorites/stocks/${encodeURIComponent(tsCode)}`);
    await loadStocks();
  }

  function onAddStockInput() {
    const q = elAddSearch.value.trim();
    if (!q) {
      hideDropdown(elAddDropdown);
      return;
    }
    clearTimeout(stockSearchTimer);
    stockSearchTimer = setTimeout(async () => {
      try {
        clearError();
        const codes = selectedBoardCodes();
        let items;
        if (codes.length) {
          const pool = await getMemberPool();
          items = pool.filter((m) => matchStock(m, q) && !stockFavCodes.has(m.ts_code));
        } else {
          const td = tdParam();
          const params = new URLSearchParams({ keyword: q });
          if (td) params.set("trade_date", td);
          const data = await apiGet(`/api/v1/sectors/lookup/stock?${params}`);
          items = (data.items || []).filter((s) => !stockFavCodes.has(s.ts_code));
        }
        renderStockDropdown(items);
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
      selectedBoards.clear();
      clearMemberCache();
      renderSelectedTags();
    });
  }

  btnQuery.addEventListener("click", () => {
    clearMemberCache();
    loadStocks().catch((err) => showError(err.message));
  });
  btnResetBoards.addEventListener("click", () => {
    selectedBoards.clear();
    elBoardSearch.value = "";
    hideDropdown(elBoardDropdown);
    clearMemberCache();
    renderSelectedTags();
  });
  elBoardSearch.addEventListener("input", onBoardSearchInput);
  elBoardSearch.addEventListener("focus", onBoardSearchInput);
  elAddSearch.addEventListener("input", onAddStockInput);
  elBoardSelected.addEventListener("click", (e) => {
    const tag = e.target.closest(".board-tag");
    if (!tag || e.target.tagName !== "BUTTON") return;
    selectedBoards.delete(tag.dataset.code);
    memberCache.delete(tag.dataset.code);
    renderSelectedTags();
  });
  elDate.addEventListener("change", () => clearMemberCache());
  document.addEventListener("click", (e) => {
    if (elBoardPicker && !elBoardPicker.contains(e.target)) hideDropdown(elBoardDropdown);
    if (elStockPicker && !elStockPicker.contains(e.target)) hideDropdown(elAddDropdown);
  });

  (async function init() {
    try {
      await initTradeDateCalendar(elDate, "/api/v1/sectors/trade-dates?limit=90");
      await loadFavoriteBoards();
      renderSelectedTags();
      await loadStocks();
    } catch (err) {
      showError(err.message);
    }
  })();
})();
