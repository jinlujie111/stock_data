(function () {
  const cfg = window.__DC_PAGE__;
  const slug = cfg.slug;
  const columns = cfg.columns;
  const sortHint = cfg.sort_hint || "";
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
  const elHead = document.getElementById("table-head");
  const elBody = document.getElementById("table-body");
  const elSummary = document.getElementById("result-summary");
  const elEmpty = document.getElementById("table-empty");
  const elError = document.getElementById("table-error");
  const elHint = document.getElementById("filter-hint");
  const chipGroup = document.getElementById("content-type-chips");
  const elChartInput = document.getElementById("chart-board-input");
  const elChartError = document.getElementById("chart-error");

  let selectedContentTypes = [];
  let allBoards = [];
  let tableRows = [];
  let sortKey = defaultSortKey;
  let sortDir = defaultSortDir;
  const selectedBoards = new Map();
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
          "<tr>" +
          columns.map((c) => `<td>${fmtCell(row[c.key], c.fmt)}</td>`).join("") +
          "</tr>"
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
    tableRows = data.items;
    applySort();
    const boardHint = codes.length ? `，已选 ${codes.length} 个板块` : "，全部板块";
    const typeHint = ct ? `，类型：${ct}` : "，类型：全部";
    elSummary.textContent = `${data.trade_date} · 共 ${data.total} 条${typeHint}${boardHint}`;
  }

  function chartBoardKeywords() {
    const raw = (elChartInput.value || "").trim();
    if (!raw) return chartDefaults.join(",");
    return raw;
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
    const keywords = chartBoardKeywords();
    let url =
      `/api/dc/fund-flow/trends?trade_date=${encodeURIComponent(td)}&days=30` +
      `&board_keywords=${encodeURIComponent(keywords)}`;
    const data = await apiGet(url);
    if (!data.series || !data.series.length) {
      showChartError("暂无趋势数据，请检查板块关键词或交易日");
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
    hideDropdown();
    renderSelectedTags();
  });

  document.getElementById("btn-chart-refresh").addEventListener("click", () => {
    loadCharts().catch((err) => showChartError(err.message));
  });

  elDate.addEventListener("change", () => {
    loadBoards()
      .then(() => loadData())
      .then(() => loadCharts())
      .catch((err) => showError(err.message));
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

  elChartInput.placeholder = "默认：" + chartDefaults.join("、");

  renderHead();
  renderSelectedTags();
  loadTradeDates()
    .then(() => loadBoards())
    .then(() => loadData())
    .then(() => loadCharts())
    .catch((err) => showError(err.message));
})();
