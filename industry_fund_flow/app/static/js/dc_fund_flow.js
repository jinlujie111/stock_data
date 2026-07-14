(function () {
  const { apiGet, initTradeDateCalendar, klineLink, funnelBoardLinks } = window.DcBoard;
  const cfg = window.__DC_PAGE__;
  const slug = cfg.slug;
  const columns = cfg.columns;
  const defaultSortKey = cfg.default_sort_key || "dc_rank";
  const defaultSortDir = cfg.default_sort_dir || "asc";

  const elDate = document.getElementById("trade-date");
  const elSearch = document.getElementById("board-search");
  const elDropdown = document.getElementById("board-dropdown");
  const elSelected = document.getElementById("board-selected");
  const elPicker = document.getElementById("board-picker");
  const elHead = document.getElementById("table-head");
  const elBody = document.getElementById("table-body");
  const elEmpty = document.getElementById("table-empty");
  const elError = document.getElementById("table-error");
  const chipGroup = document.getElementById("content-type-chips");
  const elBoardTop5Inflow = document.getElementById("board-top5-inflow");
  const elBoardTop5Outflow = document.getElementById("board-top5-outflow");
  const elBoardTop5Empty = document.getElementById("board-top5-empty");
  const elBoardTop5Error = document.getElementById("board-top5-error");
  const elBoardTop5Updated = document.getElementById("board-top5-updated");
  const elStockTop10Body = document.getElementById("stock-top10-body");
  const elStockTop10Empty = document.getElementById("stock-top10-empty");
  const elStockTop10Error = document.getElementById("stock-top10-error");
  const elStockTop10Updated = document.getElementById("stock-top10-updated");
  const stockFlowTabs = document.getElementById("stock-flow-tabs");

  let selectedContentTypes = [];
  let stockFlowDirection = "in";
  let allBoards = [];
  let tableRows = [];
  let sortKey = defaultSortKey;
  let sortDir = defaultSortDir;
  const selectedBoards = new Map();

  function fmtCell(val, fmt) {
    if (val === null || val === undefined || val === "") return "—";
    const n = Number(val);
    switch (fmt) {
      case "yi":
        if (Number.isNaN(n)) return val;
        return (n / 10000).toFixed(2) + "亿";
      case "yi_accel":
        if (Number.isNaN(n)) return val;
        return (n / 1e8).toFixed(2) + "亿";
      case "pct2":
        if (Number.isNaN(n)) return val;
        return n.toFixed(2) + "%";
      case "strength4":
        if (Number.isNaN(n)) return val;
        return n.toFixed(4);
      case "days":
        if (Number.isNaN(n)) return val;
        return String(Math.trunc(n)) + "天";
      case "int":
        if (Number.isNaN(n)) return val;
        return Math.trunc(n).toLocaleString("zh-CN");
      case "bool":
        return val === 1 || val === true ? "是" : "否";
      default:
        return val;
    }
  }

  function pctChangeClass(col, val) {
    if (col.key !== "pct_change" && col.key !== "pct_chg") return "";
    const n = Number(val);
    if (Number.isNaN(n) || n === 0) return "";
    return n > 0 ? "cell-rise" : "cell-fall";
  }

  function pctClass(val) {
    const n = Number(val);
    if (Number.isNaN(n) || n === 0) return "";
    return n > 0 ? "cell-rise" : "cell-fall";
  }

  function fmtPct(val) {
    const n = Number(val);
    if (Number.isNaN(n)) return "—";
    const sign = n > 0 ? "+" : "";
    return sign + n.toFixed(2) + "%";
  }

  function fmtYi(val) {
    const n = Number(val);
    if (Number.isNaN(n)) return "—";
    return n.toFixed(2) + "亿";
  }

  function fmtSnapshotTime(tradeDate) {
    if (!tradeDate) return "";
    const parts = tradeDate.split("-");
    if (parts.length !== 3) return tradeDate;
    return `${parts[1]}-${parts[2]} 15:05`;
  }

  function renderCell(row, col) {
    const cls = pctChangeClass(col, row[col.key]);
    const text = fmtCell(row[col.key], col.fmt);
    return cls ? `<td class="${cls}">${text}</td>` : `<td>${text}</td>`;
  }

  function sortValue(row, key, fmt) {
    const v = row[key];
    if (v === null || v === undefined || v === "") return null;
    if (fmt === "yi") return Number(v) / 10000;
    if (fmt === "yi_accel") return Number(v) / 1e8;
    if (["pct2", "strength4", "days", "int"].includes(fmt)) return Number(v);
    return String(v);
  }

  function sortRows(rows) {
    const col = columns.find((c) => c.key === sortKey);
    const fmt = col ? col.fmt : "text";
    const dir = sortDir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = sortValue(a, sortKey, fmt);
      const vb = sortValue(b, sortKey, fmt);
      if (va === null && vb === null) return 0;
      if (va === null) return 1;
      if (vb === null) return -1;
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
      return String(va).localeCompare(String(vb), "zh-CN") * dir;
    });
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

  function renderBoardTags(selectedMap, containerEl, emptyText) {
    if (!selectedMap.size) {
      containerEl.innerHTML = `<span class="board-placeholder">${emptyText}</span>`;
      return;
    }
    containerEl.innerHTML = Array.from(selectedMap.values())
      .map(
        (b) =>
          `<span class="board-tag" data-code="${b.industry_code}">` +
          `${boardLabel(b)}<button type="button" aria-label="移除">×</button></span>`
      )
      .join("");
  }

  function renderSelectedTags() {
    renderBoardTags(selectedBoards, elSelected, "未选择板块（展示全部）");
  }

  function renderDropdown(dropdownEl, matches) {
    if (!matches.length) {
      dropdownEl.innerHTML = '<div class="board-option board-option--empty">无匹配板块</div>';
      dropdownEl.classList.remove("hidden");
      return;
    }
    dropdownEl.innerHTML = matches
      .slice(0, 50)
      .map(
        (b) =>
          `<button type="button" class="board-option" data-code="${b.industry_code}">` +
          `${boardLabel(b)}</button>`
      )
      .join("");
    dropdownEl.classList.remove("hidden");
  }

  function hideDropdown(dropdownEl) {
    dropdownEl.classList.add("hidden");
  }

  function onTableSearchInput() {
    const q = elSearch.value;
    if (!q.trim()) {
      hideDropdown(elDropdown);
      return;
    }
    const matches = allBoards.filter((b) => !selectedBoards.has(b.industry_code) && matchBoard(b, q));
    renderDropdown(elDropdown, matches);
  }

  function addTableBoard(code) {
    const board = allBoards.find((b) => b.industry_code === code);
    if (!board) return;
    selectedBoards.set(code, board);
    renderSelectedTags();
    elSearch.value = "";
    hideDropdown(elDropdown);
  }

  function showError(msg) {
    elError.textContent = msg;
    elError.classList.remove("hidden");
  }

  function clearError() {
    elError.classList.add("hidden");
  }

  function showBoardTop5Error(msg) {
    elBoardTop5Error.textContent = msg;
    elBoardTop5Error.classList.remove("hidden");
  }

  function clearBoardTop5Error() {
    elBoardTop5Error.classList.add("hidden");
  }

  function showStockTop10Error(msg) {
    elStockTop10Error.textContent = msg;
    elStockTop10Error.classList.remove("hidden");
  }

  function clearStockTop10Error() {
    elStockTop10Error.classList.add("hidden");
  }

  function renderBoardTop5Item(item, mode) {
    const pctCls = pctClass(item.pct_change);
    const amtCls = mode === "in" ? "cell-rise" : "cell-fall";
    const amt = item.net_amount_yi_abs != null ? item.net_amount_yi_abs : item.net_amount_yi;
    const kline = klineLink("board", item.industry_code, elDate.value);
    return (
      `<div class="board-top5-item">` +
      `<span class="board-top5-name" title="${item.industry_name || ""}">${item.industry_name || "—"}</span>` +
      `<span class="board-top5-kline">${kline}</span>` +
      `<span class="board-top5-pct ${pctCls}">${fmtPct(item.pct_change)}</span>` +
      `<span class="board-top5-amt ${amtCls}">${fmtYi(amt)}</span>` +
      `</div>`
    );
  }

  function renderBoardTop5(data) {
    const hasData = (data.inflow && data.inflow.length) || (data.outflow && data.outflow.length);
    elBoardTop5Updated.textContent = data.trade_date
      ? `更新于 ${fmtSnapshotTime(data.trade_date)}`
      : "";
    if (!hasData) {
      elBoardTop5Inflow.innerHTML = '<div class="board-top5-empty-hint">暂无数据</div>';
      elBoardTop5Outflow.innerHTML = '<div class="board-top5-empty-hint">暂无数据</div>';
      elBoardTop5Empty.classList.remove("hidden");
      return;
    }
    elBoardTop5Empty.classList.add("hidden");
    elBoardTop5Inflow.innerHTML = (data.inflow || []).map((item) => renderBoardTop5Item(item, "in")).join("");
    elBoardTop5Outflow.innerHTML = (data.outflow || []).map((item) => renderBoardTop5Item(item, "out")).join("");
  }

  function renderStockTop10(data) {
    elStockTop10Updated.textContent = data.trade_date
      ? `更新于 ${fmtSnapshotTime(data.trade_date)}`
      : "";
    const items = data.items || [];
    if (!items.length) {
      elStockTop10Body.innerHTML = "";
      elStockTop10Empty.classList.remove("hidden");
      return;
    }
    elStockTop10Empty.classList.add("hidden");
    const isIn = data.direction !== "out";
    elStockTop10Body.innerHTML = items
      .map((row) => {
        const pctCls = pctClass(row.pct_chg);
        const netCls = isIn ? "cell-rise" : "cell-fall";
        const netVal = row.net_mf_yi_abs != null ? row.net_mf_yi_abs : row.net_mf_yi;
        return (
          "<tr>" +
          `<td>${row.stock_name || row.ts_code || "—"}</td>` +
          `<td class="${netCls}">${fmtYi(netVal)}</td>` +
          `<td class="${pctCls}">${fmtPct(row.pct_chg)}</td>` +
          `<td>${fmtYi(row.amount_yi)}</td>` +
          `<td>${row.amount_ratio != null ? Number(row.amount_ratio).toFixed(2) + "%" : "—"}</td>` +
          `<td>${klineLink("stock", row.ts_code, elDate.value)}</td>` +
          "</tr>"
        );
      })
      .join("");
  }

  async function loadBoardTop5() {
    clearBoardTop5Error();
    const td = elDate.value;
    if (!td) return;
    const ct = getContentTypesParam();
    let url = `/api/dc/fund-flow/board-top5?trade_date=${encodeURIComponent(td)}`;
    if (ct) url += `&content_types=${encodeURIComponent(ct)}`;
    const data = await apiGet(url);
    renderBoardTop5(data);
  }

  async function loadStockTop10() {
    clearStockTop10Error();
    const td = elDate.value;
    if (!td) return;
    const url =
      `/api/dc/fund-flow/stock-top10?trade_date=${encodeURIComponent(td)}` +
      `&direction=${encodeURIComponent(stockFlowDirection)}`;
    const data = await apiGet(url);
    renderStockTop10(data);
  }

  async function loadSnapshots() {
    const results = await Promise.allSettled([loadBoardTop5(), loadStockTop10()]);
    results.forEach((r, i) => {
      if (r.status === "rejected") {
        const msg = r.reason?.message || String(r.reason);
        if (i === 0) showBoardTop5Error(msg);
        else showStockTop10Error(msg);
      }
    });
  }

  function refreshPageData() {
    clearError();
    return loadBoards().then(() =>
      Promise.all([
        loadData().catch((err) => showError(err.message)),
        loadSnapshots(),
      ])
    );
  }

  function renderHead() {
    elHead.innerHTML =
      columns
        .map((c) => {
          if (!c.sortable) return `<th>${c.label}</th>`;
          const active = c.key === sortKey;
          const arrow = active ? (sortDir === "asc" ? " ▲" : " ▼") : "";
          return (
            `<th class="sortable-th" data-key="${c.key}" title="点击排序">` +
            `${c.label}${arrow}</th>`
          );
        })
        .join("") + `<th>下一步</th>`;
  }

  function boardNextCell(row) {
    const code = row.industry_code;
    if (!code || !funnelBoardLinks) return "<td>—</td>";
    return `<td>${funnelBoardLinks(code, row.industry_name, elDate.value, { primary: "vp" })}</td>`;
  }

  function renderRows(items) {
    if (!items.length) {
      elBody.innerHTML = "";
      elEmpty.classList.remove("hidden");
      return;
    }
    elEmpty.classList.add("hidden");
    elBody.innerHTML = items
      .map((row) => "<tr>" + columns.map((c) => renderCell(row, c)).join("") + boardNextCell(row) + "</tr>")
      .join("");
  }

  function applySort() {
    tableRows = sortRows(tableRows);
    renderHead();
    renderRows(tableRows);
  }

  async function loadTradeDates() {
    await initTradeDateCalendar(
      elDate,
      `/api/dc/meta/trade-dates?slug=${encodeURIComponent(slug)}&limit=90`
    );
  }

  async function loadBoards() {
    const td = elDate.value;
    if (!td) return;
    const ct = getContentTypesParam();
    let url = `/api/dc/meta/boards?slug=${encodeURIComponent(slug)}&trade_date=${encodeURIComponent(td)}`;
    if (ct) url += `&content_types=${encodeURIComponent(ct)}`;
    const data = await apiGet(url);
    allBoards = data.boards;

    const keepTable = new Map();
    selectedBoards.forEach((b, code) => {
      if (allBoards.some((x) => x.industry_code === code)) keepTable.set(code, b);
    });
    selectedBoards.clear();
    keepTable.forEach((b, code) => selectedBoards.set(code, b));
    renderSelectedTags();
  }

  async function loadData() {
    clearError();
    const td = elDate.value;
    const ct = getContentTypesParam();
    const codes = selectedBoardCodes();
    let url = `/api/dc/${encodeURIComponent(slug)}?trade_date=${encodeURIComponent(td)}`;
    if (ct) url += `&content_types=${encodeURIComponent(ct)}`;
    if (codes.length) url += `&industry_codes=${encodeURIComponent(codes.join(","))}`;
    const data = await apiGet(url);
    tableRows = data.items;
    applySort();
  }

  elHead.addEventListener("click", (e) => {
    const th = e.target.closest(".sortable-th");
    if (!th) return;
    const key = th.dataset.key;
    if (sortKey === key) {
      sortDir = sortDir === "asc" ? "desc" : "asc";
    } else {
      sortKey = key;
      sortDir = "asc";
    }
    applySort();
  });

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
    loadBoards()
      .then(() => loadSnapshots())
      .catch((err) => showError(err.message));
  });

  if (stockFlowTabs) {
    stockFlowTabs.addEventListener("click", (e) => {
      const btn = e.target.closest(".tab[data-dir]");
      if (!btn) return;
      stockFlowDirection = btn.dataset.dir;
      stockFlowTabs.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      btn.classList.add("active");
      loadStockTop10().catch((err) => showStockTop10Error(err.message));
    });
  }

  document.getElementById("btn-query").addEventListener("click", () => {
    refreshPageData();
  });

  document.getElementById("btn-reset-boards").addEventListener("click", () => {
    selectedBoards.clear();
    elSearch.value = "";
    hideDropdown(elDropdown);
    renderSelectedTags();
  });

  elDate.addEventListener("change", () => {
    refreshPageData().catch((err) => showError(err.message));
  });

  elSearch.addEventListener("input", onTableSearchInput);
  elSearch.addEventListener("focus", onTableSearchInput);

  elDropdown.addEventListener("click", (e) => {
    const btn = e.target.closest(".board-option[data-code]");
    if (!btn) return;
    addTableBoard(btn.dataset.code);
  });

  elSelected.addEventListener("click", (e) => {
    const tag = e.target.closest(".board-tag");
    if (!tag) return;
    if (e.target.tagName === "BUTTON") {
      selectedBoards.delete(tag.dataset.code);
      renderSelectedTags();
    }
  });

  document.addEventListener("click", (e) => {
    if (!elPicker.contains(e.target)) hideDropdown(elDropdown);
  });

  renderHead();
  renderSelectedTags();
  loadTradeDates()
    .then(() => refreshPageData())
    .catch((err) => showError(err.message));
})();
