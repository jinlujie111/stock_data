(function () {
  const cfg = window.__DC_PAGE__;
  const slug = cfg.slug;
  const columns = cfg.columns;
  const defaultSortKey = cfg.default_sort_key || "dc_rank";
  const defaultSortDir = cfg.default_sort_dir || "asc";
  const chartDefaults = cfg.chart_default_boards || [];

  const CHART_COLORS = [
    "#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6",
    "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#6366f1",
  ];

  const elDate = document.getElementById("trade-date");
  const elSearch = document.getElementById("board-search");
  const elDropdown = document.getElementById("board-dropdown");
  const elSelected = document.getElementById("board-selected");
  const elPicker = document.getElementById("board-picker");
  const elChartSearch = document.getElementById("chart-board-search");
  const elChartDropdown = document.getElementById("chart-board-dropdown");
  const elChartSelected = document.getElementById("chart-board-selected");
  const elChartPicker = document.getElementById("chart-board-picker");
  const elHead = document.getElementById("table-head");
  const elBody = document.getElementById("table-body");
  const elEmpty = document.getElementById("table-empty");
  const elError = document.getElementById("table-error");
  const chipGroup = document.getElementById("content-type-chips");
  const elChartError = document.getElementById("chart-error");

  let selectedContentTypes = [];
  let allBoards = [];
  let tableRows = [];
  let sortKey = defaultSortKey;
  let sortDir = defaultSortDir;
  let chartDefaultsApplied = false;
  const selectedBoards = new Map();
  const chartSelectedBoards = new Map();
  const charts = { yi: null, rate: null, rank: null };

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

  function chartSelectedBoardCodes() {
    return Array.from(chartSelectedBoards.keys());
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

  function resolveBoardByKeyword(keyword) {
    const kw = keyword.trim();
    if (!kw) return null;
    const exact = allBoards.find((b) => b.industry_name === kw || b.industry_code === kw);
    if (exact) return exact;
    const matches = allBoards.filter(
      (b) =>
        b.industry_name.includes(kw) ||
        kw.includes(b.industry_name) ||
        (b.industry_code && b.industry_code.toLowerCase().includes(kw.toLowerCase()))
    );
    if (!matches.length) return null;
    return matches.sort((a, b) => a.industry_name.length - b.industry_name.length)[0];
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

  function renderChartSelectedTags() {
    renderBoardTags(
      chartSelectedBoards,
      elChartSelected,
      `未选择板块（默认：${chartDefaults.join("、")}）`
    );
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

  function onChartSearchInput() {
    const q = elChartSearch.value;
    if (!q.trim()) {
      hideDropdown(elChartDropdown);
      return;
    }
    const matches = allBoards.filter(
      (b) => !chartSelectedBoards.has(b.industry_code) && matchBoard(b, q)
    );
    renderDropdown(elChartDropdown, matches);
  }

  function addTableBoard(code) {
    const board = allBoards.find((b) => b.industry_code === code);
    if (!board) return;
    selectedBoards.set(code, board);
    renderSelectedTags();
    elSearch.value = "";
    hideDropdown(elDropdown);
  }

  function addChartBoard(code) {
    const board = allBoards.find((b) => b.industry_code === code);
    if (!board) return;
    chartSelectedBoards.set(code, board);
    renderChartSelectedTags();
    elChartSearch.value = "";
    hideDropdown(elChartDropdown);
  }

  function applyDefaultChartBoards() {
    chartSelectedBoards.clear();
    chartDefaults.forEach((name) => {
      const board = resolveBoardByKeyword(name);
      if (board) chartSelectedBoards.set(board.industry_code, board);
    });
    renderChartSelectedTags();
  }

  function syncChartBoards() {
    const keep = new Map();
    chartSelectedBoards.forEach((b, code) => {
      const fresh = allBoards.find((x) => x.industry_code === code);
      if (fresh) keep.set(code, fresh);
    });
    chartSelectedBoards.clear();
    keep.forEach((b, code) => chartSelectedBoards.set(code, b));
    if (!chartSelectedBoards.size && !chartDefaultsApplied) {
      applyDefaultChartBoards();
      chartDefaultsApplied = true;
    }
    renderChartSelectedTags();
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

  function showChartError(msg) {
    elChartError.textContent = msg;
    elChartError.classList.remove("hidden");
  }

  function clearChartError() {
    elChartError.classList.add("hidden");
  }

  function renderHead() {
    elHead.innerHTML = columns
      .map((c) => {
        if (!c.sortable) return `<th>${c.label}</th>`;
        const active = c.key === sortKey;
        const arrow = active ? (sortDir === "asc" ? " ▲" : " ▼") : "";
        return (
          `<th class="sortable-th" data-key="${c.key}" title="点击排序">` +
          `${c.label}${arrow}</th>`
        );
      })
      .join("");
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
          "<tr>" + columns.map((c) => renderCell(row, c)).join("") + "</tr>"
      )
      .join("");
  }

  function applySort() {
    tableRows = sortRows(tableRows);
    renderHead();
    renderRows(tableRows);
  }

  async function loadTradeDates() {
    const data = await apiGet(`/api/dc/meta/trade-dates?slug=${encodeURIComponent(slug)}`);
    elDate.innerHTML = data.dates.map((d) => `<option value="${d}">${d}</option>`).join("");
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

    const keepTable = new Map();
    selectedBoards.forEach((b, code) => {
      if (allBoards.some((x) => x.industry_code === code)) keepTable.set(code, b);
    });
    selectedBoards.clear();
    keepTable.forEach((b, code) => selectedBoards.set(code, b));
    renderSelectedTags();

    syncChartBoards();
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

  function collectValues(series, valueKey) {
    return series
      .flatMap((s) => s.points.map((p) => p[valueKey]))
      .filter((v) => v !== null && v !== undefined && !Number.isNaN(Number(v)))
      .map(Number);
  }

  function yScaleOptions(chartKey, series, valueKey) {
    const vals = collectValues(series, valueKey);
    const base = {
      ticks: {
        color: "#8b9cb3",
        maxTicksLimit: 6,
        font: { size: 11 },
      },
      grid: { color: "rgba(45,58,79,0.35)" },
      border: { display: false },
    };
    if (!vals.length) return base;

    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const span = max - min;
    const pad = span > 0 ? span * 0.08 : Math.max(Math.abs(max), 1) * 0.08;

    if (chartKey === "rank") {
      return {
        ...base,
        reverse: true,
        min: Math.max(1, Math.floor(min - pad)),
        max: Math.ceil(max + pad),
        ticks: {
          ...base.ticks,
          stepSize: Math.max(1, Math.ceil((max - min) / 5)),
        },
      };
    }

    return {
      ...base,
      min: min - pad,
      max: max + pad,
      ticks: {
        ...base.ticks,
        callback: (v) => {
          const n = Number(v);
          if (chartKey === "rate") return n.toFixed(1) + "%";
          if (chartKey === "yi") return n.toFixed(2);
          return n;
        },
      },
    };
  }

  function buildChart(canvasId, chartKey, series, dates, valueKey) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    if (charts[chartKey]) {
      charts[chartKey].destroy();
    }
    const datasets = series.map((s, i) => ({
      label: s.industry_name,
      data: s.points.map((p) => p[valueKey]),
      borderColor: CHART_COLORS[i % CHART_COLORS.length],
      backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + "33",
      tension: 0.25,
      pointRadius: 2,
      spanGaps: true,
    }));
    charts[chartKey] = new Chart(canvas, {
      type: "line",
      data: { labels: dates, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom", labels: { color: "#8b9cb3", boxWidth: 12 } },
          title: { display: false },
        },
        scales: {
          x: {
            ticks: {
              color: "#8b9cb3",
              maxRotation: 45,
              minRotation: 0,
              maxTicksLimit: 10,
              font: { size: 11 },
            },
            grid: { color: "rgba(45,58,79,0.35)" },
            border: { display: false },
          },
          y: yScaleOptions(chartKey, series, valueKey),
        },
      },
    });
  }

  async function loadCharts() {
    clearChartError();
    const td = elDate.value;
    if (!td) return;
    const codes = chartSelectedBoardCodes();
    let url = `/api/dc/fund-flow/trends?trade_date=${encodeURIComponent(td)}&days=30`;
    if (codes.length) {
      url += `&industry_codes=${encodeURIComponent(codes.join(","))}`;
    } else {
      url += `&board_keywords=${encodeURIComponent(chartDefaults.join(","))}`;
    }
    const data = await apiGet(url);
    if (!data.series || !data.series.length) {
      showChartError("暂无趋势数据，请点选板块或恢复默认后重试");
      return;
    }
    const dates = data.dates;
    buildChart("chart-net-yi", "yi", data.series, dates, "net_amount_yi");
    buildChart("chart-net-rate", "rate", data.series, dates, "net_amount_rate");
    buildChart("chart-rank", "rank", data.series, dates, "dc_rank");
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
    loadBoards().catch((err) => showError(err.message));
  });

  document.getElementById("btn-query").addEventListener("click", () => {
    loadData().catch((err) => showError(err.message));
  });

  document.getElementById("btn-reset-boards").addEventListener("click", () => {
    selectedBoards.clear();
    elSearch.value = "";
    hideDropdown(elDropdown);
    renderSelectedTags();
  });

  document.getElementById("btn-chart-refresh").addEventListener("click", () => {
    loadCharts().catch((err) => showChartError(err.message));
  });

  document.getElementById("btn-reset-chart-boards").addEventListener("click", () => {
    chartDefaultsApplied = true;
    applyDefaultChartBoards();
    loadCharts().catch((err) => showChartError(err.message));
  });

  elDate.addEventListener("change", () => {
    chartDefaultsApplied = false;
    loadBoards()
      .then(() => loadData())
      .then(() => loadCharts())
      .catch((err) => showError(err.message));
  });

  elSearch.addEventListener("input", onTableSearchInput);
  elSearch.addEventListener("focus", onTableSearchInput);

  elChartSearch.addEventListener("input", onChartSearchInput);
  elChartSearch.addEventListener("focus", onChartSearchInput);

  elDropdown.addEventListener("click", (e) => {
    const btn = e.target.closest(".board-option[data-code]");
    if (!btn) return;
    addTableBoard(btn.dataset.code);
  });

  elChartDropdown.addEventListener("click", (e) => {
    const btn = e.target.closest(".board-option[data-code]");
    if (!btn) return;
    addChartBoard(btn.dataset.code);
  });

  elSelected.addEventListener("click", (e) => {
    const tag = e.target.closest(".board-tag");
    if (!tag) return;
    if (e.target.tagName === "BUTTON") {
      selectedBoards.delete(tag.dataset.code);
      renderSelectedTags();
    }
  });

  elChartSelected.addEventListener("click", (e) => {
    const tag = e.target.closest(".board-tag");
    if (!tag) return;
    if (e.target.tagName === "BUTTON") {
      chartSelectedBoards.delete(tag.dataset.code);
      renderChartSelectedTags();
    }
  });

  document.addEventListener("click", (e) => {
    if (!elPicker.contains(e.target)) hideDropdown(elDropdown);
    if (!elChartPicker.contains(e.target)) hideDropdown(elChartDropdown);
  });

  renderHead();
  renderSelectedTags();
  renderChartSelectedTags();
  loadTradeDates()
    .then(() => loadBoards())
    .then(() => loadData())
    .then(() => loadCharts())
    .catch((err) => showError(err.message));
})();
