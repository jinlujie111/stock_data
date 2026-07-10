(function () {
  const { klineLink } = window.DcBoard || {};

  const elDate = document.getElementById("trade-date");
  const elTypes = document.getElementById("content-types");
  const elWindow = document.getElementById("window");
  const elThead = document.getElementById("vp-thead");
  const elBody = document.getElementById("vp-body");
  const elEmpty = document.getElementById("vp-empty");
  const elError = document.getElementById("page-error");
  const elDetailCard = document.getElementById("detail-card");
  const elDetailTitle = document.getElementById("detail-title");
  const elDetailMetrics = document.getElementById("detail-metrics");
  const elDetailStocks = document.getElementById("detail-stocks");
  const elBoardSelected = document.getElementById("board-selected");
  const elBoardSearch = document.getElementById("board-search");
  const elBoardDropdown = document.getElementById("board-dropdown");
  const elBoardPicker = document.getElementById("board-picker");
  const btnQuery = document.getElementById("btn-query");
  const btnResetBoards = document.getElementById("btn-reset-boards");
  let activeTab = "rank";

  const selectedBoards = new Map();
  const boardSearchResults = new Map();
  let boardSearchTimer = null;

  const STATUS_LABEL = {
    mainline_burst: "主线爆发",
    trend_up: "趋势上升",
    range_bound: "震荡",
    weak: "弱势",
    ebbing: "退潮",
  };

  const SIGNAL_LABEL = {
    main_rise: "主升",
    ebbing: "退潮",
    none: "无",
    launch: "启动",
    distribution: "派发",
  };

  const PATTERN_LABEL = {
    trend_confirm: "趋势确认",
    weak_rise: "缩量上涨",
    distribution: "出货信号",
    consolidation: "低迷筑底",
  };

  function labelSignal(v) {
    if (!v || v === "none") return "—";
    return SIGNAL_LABEL[v] || v;
  }

  function labelPattern(v) {
    if (!v) return "—";
    return PATTERN_LABEL[v] || v;
  }

  function fmt(v, d) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(d == null ? 2 : d);
  }

  function pct(v) {
    if (v === null || v === undefined) return "—";
    return (Number(v) * 100).toFixed(1) + "%";
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

  function boardLabel(item) {
    return `[${item.content_type}] ${item.industry_name} (${item.industry_code})`;
  }

  function renderSelectedBoards() {
    if (!selectedBoards.size) {
      elBoardSelected.innerHTML = '<span class="board-placeholder">未选择板块（展示全部）</span>';
      return;
    }
    elBoardSelected.innerHTML = "";
    selectedBoards.forEach((item, code) => {
      const wrap = document.createElement("span");
      wrap.className = "board-tag";
      wrap.innerHTML = `${boardLabel(item)}<button type="button" data-code="${code}">×</button>`;
      elBoardSelected.appendChild(wrap);
    });
    elBoardSelected.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        selectedBoards.delete(btn.dataset.code);
        renderSelectedBoards();
      });
    });
  }

  function hideDropdown() {
    elBoardDropdown.classList.add("hidden");
  }

  function addBoard(item) {
    if (!item || !item.industry_code) return;
    selectedBoards.set(item.industry_code, item);
    renderSelectedBoards();
    elBoardSearch.value = "";
    hideDropdown();
  }

  async function searchBoards(keyword) {
    if (!keyword || !keyword.trim()) {
      elBoardDropdown.innerHTML = "";
      hideDropdown();
      return;
    }
    const data = await apiGet(
      `/api/v1/vp/boards/search?trade_date=${encodeURIComponent(elDate.value)}` +
        `&content_types=${encodeURIComponent(elTypes.value)}` +
        `&keyword=${encodeURIComponent(keyword.trim())}&limit=20`
    );
    const items = data.items || [];
    boardSearchResults.clear();
    if (!items.length) {
      elBoardDropdown.innerHTML = "";
      hideDropdown();
      return;
    }
    items.forEach((item) => boardSearchResults.set(item.industry_code, item));
    elBoardDropdown.innerHTML = items
      .map(
        (item) =>
          `<button type="button" class="board-option" data-code="${item.industry_code}">` +
          `${boardLabel(item)}</button>`
      )
      .join("");
    elBoardDropdown.classList.remove("hidden");
  }

  function queryParams() {
    const codes = Array.from(selectedBoards.keys());
    return {
      td: elDate.value,
      types: elTypes.value,
      w: elWindow.value,
      codes: codes.length ? codes.join(",") : "",
    };
  }

  async function loadDates() {
    const data = await apiGet("/api/v1/vp/trade-dates?limit=60");
    elDate.innerHTML = "";
    const dates = data.dates || [];
    if (!dates.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "暂无数据";
      opt.disabled = true;
      elDate.appendChild(opt);
      showError("VP 评分表暂无数据，请先在服务器执行 run_vp_batch");
      return;
    }
    dates.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d;
      opt.textContent = d;
      elDate.appendChild(opt);
    });
    if (data.latest) elDate.value = data.latest;
  }

  function renderRank(items) {
    elThead.innerHTML =
      "<tr><th>#</th><th>板块</th><th>类型</th><th>VP分</th><th>状态</th><th>信号</th>" +
      "<th>行业量比</th><th>上涨占比</th><th>突破占比</th><th>连续放量</th><th>K线分析</th><th>操作</th></tr>";
    elBody.innerHTML = "";
    if (!items.length) {
      elEmpty.classList.remove("hidden");
      return;
    }
    elEmpty.classList.add("hidden");
    items.forEach((row, idx) => {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${row.rank_vp || idx + 1}</td>` +
        `<td>${row.industry_name || row.industry_code}</td>` +
        `<td>${row.content_type || "—"}</td>` +
        `<td>${fmt(row.vp_score, 1)}</td>` +
        `<td>${STATUS_LABEL[row.vp_status] || row.vp_status || "—"}</td>` +
        `<td>${labelSignal(row.signal_type)}</td>` +
        `<td>${fmt(row.industry_vol_ratio_20, 2)}</td>` +
        `<td>${pct(row.rising_ratio)}</td>` +
        `<td>${pct(row.breakout_ratio)}</td>` +
        `<td>${row.amount_streak_days ?? "—"}</td>` +
        `<td>${klineLink ? klineLink("board", row.industry_code, elDate.value) : "—"}</td>` +
        `<td><button type="button" class="btn btn-link btn-detail" data-code="${row.industry_code}">详情</button></td>`;
      elBody.appendChild(tr);
    });
    elBody.querySelectorAll(".btn-detail").forEach((btn) => {
      btn.addEventListener("click", () => loadDetail(btn.dataset.code));
    });
  }

  function renderSignals(items) {
    elThead.innerHTML =
      "<tr><th>板块</th><th>类型</th><th>VP分</th><th>状态</th><th>信号</th><th>行业量比</th><th>连续放量</th><th>K线分析</th></tr>";
    elBody.innerHTML = "";
    if (!items.length) {
      elEmpty.classList.remove("hidden");
      return;
    }
    elEmpty.classList.add("hidden");
    items.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${row.industry_name || row.industry_code}</td>` +
        `<td>${row.content_type || "—"}</td>` +
        `<td>${fmt(row.vp_score, 1)}</td>` +
        `<td>${STATUS_LABEL[row.vp_status] || row.vp_status || "—"}</td>` +
        `<td>${labelSignal(row.signal_type)}</td>` +
        `<td>${fmt(row.industry_vol_ratio_20, 2)}</td>` +
        `<td>${row.amount_streak_days ?? "—"}</td>` +
        `<td>${klineLink ? klineLink("board", row.industry_code, elDate.value) : "—"}</td>`;
      elBody.appendChild(tr);
    });
  }

  async function loadRank() {
    clearError();
    const { td, types, w, codes } = queryParams();
    let url =
      `/api/v1/vp/industries/rank?trade_date=${encodeURIComponent(td)}` +
      `&content_types=${encodeURIComponent(types)}&window=${w}&top=50`;
    if (codes) url += `&industry_codes=${encodeURIComponent(codes)}`;
    const data = await apiGet(url);
    renderRank(data.items || []);
  }

  async function loadSignals() {
    clearError();
    const { td, w, codes } = queryParams();
    let url = `/api/v1/vp/signals?trade_date=${encodeURIComponent(td)}&window=${w}&top=50`;
    if (codes) url += `&industry_codes=${encodeURIComponent(codes)}`;
    const data = await apiGet(url);
    renderSignals(data.items || []);
  }

  async function loadDetail(code) {
    clearError();
    const { td, w } = queryParams();
    const data = await apiGet(
      `/api/v1/vp/industries/${encodeURIComponent(code)}?trade_date=${encodeURIComponent(td)}&window=${w}`
    );
    const s = data.score || {};
    elDetailTitle.textContent = `${s.industry_name || code} · VP ${fmt(s.vp_score, 1)}`;
    elDetailMetrics.innerHTML = [
      ["VP 综合分", fmt(s.vp_score, 1)],
      ["状态", STATUS_LABEL[s.vp_status] || s.vp_status],
      ["信号", labelSignal(s.signal_type)],
      ["行业量比", fmt(s.industry_vol_ratio_20, 2)],
      ["上涨占比", pct(s.rising_ratio)],
      ["突破占比", pct(s.breakout_ratio)],
      ["连续放量", s.amount_streak_days],
      ["成分数", s.member_cnt],
    ]
      .map(
        ([k, v]) =>
          `<div class="metric-item"><span class="metric-label">${k}</span><span class="metric-value">${v ?? "—"}</span></div>`
      )
      .join("");

    const stocks = await apiGet(
      `/api/v1/vp/industries/${encodeURIComponent(code)}/stocks?trade_date=${encodeURIComponent(td)}&window=${w}&limit=30`
    );
    elDetailStocks.innerHTML = "";
    (stocks.items || []).forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${row.ts_code}</td>` +
        `<td>${row.stock_name || "—"}</td>` +
        `<td>${fmt(row.pct_chg, 2)}</td>` +
        `<td>${fmt(row.vol_ratio_20, 2)}</td>` +
        `<td>${row.vol_streak_days ?? "—"}</td>` +
        `<td>${row.is_breakout_60 ? "是" : "—"}</td>` +
        `<td>${labelPattern(row.vp_pattern)}</td>` +
        `<td>${fmt(row.vp_pattern_score, 0)}</td>` +
        `<td>${klineLink ? klineLink("stock", row.ts_code, td) : "—"}</td>`;
      elDetailStocks.appendChild(tr);
    });
    elDetailCard.classList.remove("hidden");
  }

  async function refresh() {
    try {
      if (activeTab === "signals") await loadSignals();
      else await loadRank();
    } catch (e) {
      showError(e.message || String(e));
    }
  }

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      activeTab = tab.dataset.tab;
      refresh();
    });
  });

  elBoardSearch.addEventListener("input", () => {
    clearTimeout(boardSearchTimer);
    boardSearchTimer = setTimeout(() => {
      searchBoards(elBoardSearch.value).catch((e) => showError(e.message || String(e)));
    }, 180);
  });
  elBoardSearch.addEventListener("focus", () => {
    if (elBoardSearch.value.trim()) {
      searchBoards(elBoardSearch.value).catch((e) => showError(e.message || String(e)));
    }
  });
  elBoardDropdown.addEventListener("mousedown", (e) => {
    e.preventDefault();
  });
  elBoardDropdown.addEventListener("click", (e) => {
    const btn = e.target.closest(".board-option[data-code]");
    if (!btn) return;
    const item = boardSearchResults.get(btn.dataset.code);
    if (item) addBoard(item);
  });
  document.addEventListener("click", (e) => {
    if (!elBoardPicker.contains(e.target)) hideDropdown();
  });

  btnResetBoards.addEventListener("click", () => {
    selectedBoards.clear();
    elBoardSearch.value = "";
    hideDropdown();
    renderSelectedBoards();
    refresh();
  });

  btnQuery.addEventListener("click", refresh);

  renderSelectedBoards();
  loadDates()
    .then(refresh)
    .catch((e) => showError(e.message || String(e)));
})();
