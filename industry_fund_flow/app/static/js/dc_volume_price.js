(function () {
  const board = window.DcBoard || {};
  const kline = window.DcKline || {};
  const { normalizeIsoDate, toApiTradeDate } = board;

  const elDate = document.getElementById("trade-date");
  const elKlineStart = document.getElementById("kline-start");
  const elKlineEnd = document.getElementById("kline-end");
  const elKlinePresets = document.getElementById("kline-range-presets");
  const btnKlineRefresh = document.getElementById("btn-kline-refresh");
  const elVpKlineChart = document.getElementById("vp-kline-chart");
  const elTypes = document.getElementById("content-types");
  const elWindow = document.getElementById("window");
  const elRankSort = document.getElementById("rank-sort");
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

  const selectedBoards = new Map();
  const boardSearchResults = new Map();
  let boardSearchTimer = null;
  let detailIndustryCode = "";
  let vpChartInstance = null;
  let vpTradeDates = [];
  let klineRangeDays = 60;

  const EMPTY_MSG_RANK = "暂无数据，请先运行 run_vp_batch";

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

  function retPct(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return "—";
    return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
  }

  function metricItems(pairs) {
    return pairs
      .map(
        ([k, v]) =>
          `<div class="metric-item"><span class="metric-label">${k}</span><span class="metric-value">${v ?? "—"}</span></div>`
      )
      .join("");
  }

  function metricGridRows(pairs, perRow) {
    const chunks = [];
    for (let i = 0; i < pairs.length; i += perRow) {
      chunks.push(pairs.slice(i, i + perRow));
    }
    return (
      `<div class="vp-metric-rows">` +
      chunks
        .map(
          (chunk) =>
            `<div class="metric-grid metric-grid--vp-row metric-grid--vp-fixed">${metricItems(chunk)}</div>`
        )
        .join("") +
      `</div>`
    );
  }

  function renderDetailMetrics(s) {
    const raw = [
      ["VP 综合分", fmt(s.vp_score, 1)],
      ["排名", s.rank_vp != null ? "#" + s.rank_vp : "—"],
      ["状态", STATUS_LABEL[s.vp_status] || s.vp_status],
      ["信号", labelSignal(s.signal_type)],
      ["行业量比", fmt(s.industry_vol_ratio_20, 2)],
      ["上涨占比", pct(s.rising_ratio)],
      ["突破占比", pct(s.breakout_ratio)],
      ["连续放量强度", fmt(s.continuity_strength, 2)],
      ["连续放量天数", s.amount_streak_days ?? "—"],
      ["20日趋势", retPct(s.trend_return_20d)],
      ["龙头强度", fmt(s.leader_strength, 2)],
      ["成分数", s.member_cnt],
    ];
    const subs = [
      ["子分·连续", fmt(s.score_continuity, 1)],
      ["子分·量比", fmt(s.score_vol, 1)],
      ["子分·趋势", fmt(s.score_trend, 1)],
      ["子分·上涨", fmt(s.score_breadth, 1)],
      ["子分·突破", fmt(s.score_breakout, 1)],
      ["子分·龙头", fmt(s.score_leader, 1)],
    ];
    elDetailMetrics.innerHTML =
      `<div class="vp-metric-block"><div class="vp-metric-block-title">原始指标</div>` +
      metricGridRows(raw, 6) +
      `</div>` +
      `<div class="vp-metric-block"><div class="vp-metric-block-title">六维子分</div>` +
      `<div class="metric-grid metric-grid--vp-row metric-grid--vp-fixed">${metricItems(subs)}</div></div>`;
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

  function showKlineStatus(html, className) {
    if (!elVpKlineChart) return;
    if (vpChartInstance && !vpChartInstance.isDisposed()) {
      vpChartInstance.dispose();
      vpChartInstance = null;
    }
    elVpKlineChart.innerHTML = `<div class="${className || "kline-status"}">${html}</div>`;
  }

  function syncKlineDateBounds() {
    if (!vpTradeDates.length) return;
    const maxIso = vpTradeDates[vpTradeDates.length - 1];
    const minIso = vpTradeDates[0];
    if (elKlineEnd) {
      elKlineEnd.max = maxIso;
      if (elKlineEnd.value && elKlineEnd.value > maxIso) elKlineEnd.value = maxIso;
    }
    if (elKlineStart) {
      elKlineStart.max = maxIso;
      elKlineStart.min = minIso;
      if (elKlineStart.value && elKlineStart.value > maxIso) elKlineStart.value = maxIso;
    }
  }

  function showTableEmpty(msg) {
    elEmpty.textContent = msg;
    elEmpty.classList.remove("hidden");
  }

  function hideTableEmpty() {
    elEmpty.classList.add("hidden");
  }

  function boardLabel(item) {
    return `[${item.content_type}] ${item.industry_name} (${item.industry_code})`;
  }

  function renderSelectedBoards() {
    if (!selectedBoards.size) {
      elBoardSelected.innerHTML = "";
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
    const data = await apiGet("/api/v1/vp/trade-dates?limit=365");
    vpTradeDates = (data.dates || []).slice().sort();
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
    syncKlineDateBounds();
  }

  function isoFromTradeDate(raw) {
    if (!raw) return "";
    if (normalizeIsoDate) return normalizeIsoDate(raw);
    const s = String(raw).trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    if (/^\d{8}$/.test(s)) return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
    return s;
  }

  function apiDateFromIso(iso) {
    if (!iso) return "";
    if (toApiTradeDate) return toApiTradeDate(iso);
    return String(iso).replace(/-/g, "");
  }

  function setKlineRangeByDays(days) {
    klineRangeDays = days;
    const endIso = isoFromTradeDate(elKlineEnd && elKlineEnd.value ? elKlineEnd.value : elDate.value);
    if (!endIso || !vpTradeDates.length) return;
    const sorted = vpTradeDates.slice().sort();
    let endIdx = sorted.indexOf(endIso);
    if (endIdx < 0) {
      for (let i = sorted.length - 1; i >= 0; i--) {
        if (sorted[i] <= endIso) {
          endIdx = i;
          break;
        }
      }
    }
    if (endIdx < 0) endIdx = sorted.length - 1;
    const startIdx = Math.max(0, endIdx - days + 1);
    if (elKlineEnd) elKlineEnd.value = sorted[endIdx];
    if (elKlineStart) elKlineStart.value = sorted[startIdx];
    if (elKlinePresets) {
      elKlinePresets.querySelectorAll(".chip").forEach((c) => {
        c.classList.toggle("active", Number(c.dataset.days) === days);
      });
    }
  }

  function initKlineRangeDefaults() {
    const endIso = isoFromTradeDate(elDate.value);
    if (elKlineEnd) elKlineEnd.value = endIso;
    setKlineRangeByDays(klineRangeDays);
  }

  /** 打开数据分析时：结束日=当前查询日，区间固定为近 60 个交易日并立即拉 K 线 */
  function prepareKlineRangeForAnalysis(days) {
    const rangeDays = days == null ? 60 : days;
    const endIso = isoFromTradeDate(elDate.value);
    if (elKlineEnd) elKlineEnd.value = endIso;
    setKlineRangeByDays(rangeDays);
  }

  function scrollToVpKline() {
    const section = document.querySelector(".vp-kline-section");
    if (section) section.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function loadVpKline(code) {
    if (!code || !elVpKlineChart) return;
    if (typeof echarts === "undefined") {
      showKlineStatus("ECharts 未加载，请检查网络或刷新页面", "table-empty kline-error");
      throw new Error("ECharts 未加载");
    }
    if (!kline.renderVpKlineChart) {
      showKlineStatus(
        "K 线组件未加载，请 Ctrl+F5 硬刷新；若仍无效请确认服务器已部署最新 industry_fund_flow 代码",
        "table-empty kline-error"
      );
      throw new Error("dc_kline_chart.js 未加载 renderVpKlineChart");
    }
    showKlineStatus("加载 K 线…", "kline-loading");
    const startIso = elKlineStart ? elKlineStart.value : "";
    const endIso = elKlineEnd ? elKlineEnd.value : isoFromTradeDate(elDate.value);
    const startQ = startIso ? `&start_date=${encodeURIComponent(apiDateFromIso(startIso))}` : "";
    const endQ = endIso ? `&trade_date=${encodeURIComponent(apiDateFromIso(endIso))}` : "";
    const daysQ = startIso ? "" : `&days=${klineRangeDays}`;
    const data = await apiGet(
      `/api/v1/vp/industries/${encodeURIComponent(code)}/kline?window=${encodeURIComponent(elWindow.value)}${endQ}${startQ}${daysQ}`
    );
    if (data.start_date && elKlineStart) elKlineStart.value = isoFromTradeDate(data.start_date);
    if (data.end_date && elKlineEnd) elKlineEnd.value = isoFromTradeDate(data.end_date);
    if (data.latest_bar_date && elKlineEnd) elKlineEnd.max = isoFromTradeDate(data.latest_bar_date);
    vpChartInstance = kline.renderVpKlineChart(elVpKlineChart, data, {
      existingChart: vpChartInstance,
    });
  }

  function renderRank(items) {
    elThead.innerHTML =
      "<tr><th>#</th><th>板块</th><th>类型</th><th>VP分</th><th>状态</th><th>信号</th>" +
      "<th>行业量比</th><th>上涨占比</th><th>突破占比</th><th>连续强度</th><th>20日趋势</th><th>龙头</th><th>操作</th></tr>";
    elBody.innerHTML = "";
    if (!items.length) {
      showTableEmpty(EMPTY_MSG_RANK);
      return;
    }
    hideTableEmpty();
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
        `<td>${fmt(row.continuity_strength, 2)}</td>` +
        `<td>${retPct(row.trend_return_20d)}</td>` +
        `<td>${fmt(row.leader_strength, 2)}</td>` +
        `<td><button type="button" class="btn btn-link btn-detail" data-code="${row.industry_code}">数据分析</button></td>`;
      elBody.appendChild(tr);
    });
    elBody.querySelectorAll(".btn-detail").forEach((btn) => {
      btn.addEventListener("click", () => loadDetail(btn.dataset.code));
    });
  }

  async function loadRank() {
    clearError();
    const { td, types, w, codes } = queryParams();
    const sort = elRankSort ? elRankSort.value : "vp_score";
    let url =
      `/api/v1/vp/industries/rank?trade_date=${encodeURIComponent(td)}` +
      `&content_types=${encodeURIComponent(types)}&window=${w}&top=50&sort=${encodeURIComponent(sort)}`;
    if (codes) url += `&industry_codes=${encodeURIComponent(codes)}`;
    const data = await apiGet(url);
    renderRank(data.items || []);
  }

  async function refresh() {
    try {
      await loadRank();
    } catch (e) {
      showError(e.message || String(e));
    }
  }

  if (elRankSort) {
    elRankSort.addEventListener("change", refresh);
  }

  async function loadDetail(code) {
    clearError();
    detailIndustryCode = code;
    elDetailCard.classList.remove("hidden");
    prepareKlineRangeForAnalysis(60);
    showKlineStatus("加载 K 线…", "kline-loading");

    const { td, w } = queryParams();
    const data = await apiGet(
      `/api/v1/vp/industries/${encodeURIComponent(code)}?trade_date=${encodeURIComponent(td)}&window=${w}`
    );
    const s = data.score || {};
    elDetailTitle.textContent = `${s.industry_name || code} · VP ${fmt(s.vp_score, 1)}`;
    renderDetailMetrics(s);

    try {
      await loadVpKline(code);
    } catch (e) {
      const msg = "K 线加载失败: " + (e.message || String(e));
      showKlineStatus(msg, "table-empty kline-error");
      showError(msg);
    }

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
        `<td>${row.is_breakout_strict ? "是" : "—"}</td>` +
        `<td>${labelPattern(row.vp_pattern)}</td>` +
        `<td>${fmt(row.vp_pattern_score, 0)}</td>`;
      elDetailStocks.appendChild(tr);
    });
    scrollToVpKline();
  }

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

  if (elKlinePresets) {
    elKlinePresets.addEventListener("click", (e) => {
      const chip = e.target.closest(".chip[data-days]");
      if (!chip) return;
      setKlineRangeByDays(Number(chip.dataset.days) || 60);
      if (detailIndustryCode) {
        loadVpKline(detailIndustryCode).catch((err) => {
          const msg = err.message || String(err);
          showKlineStatus(msg, "table-empty kline-error");
          showError(msg);
        });
      }
    });
  }

  if (btnKlineRefresh) {
    btnKlineRefresh.addEventListener("click", () => {
      if (!detailIndustryCode) {
        showError("请先在榜单中点击「数据分析」选择板块");
        return;
      }
      loadVpKline(detailIndustryCode).catch((err) => {
        const msg = err.message || String(err);
        showKlineStatus(msg, "table-empty kline-error");
        showError(msg);
      });
    });
  }

  renderSelectedBoards();
  loadDates()
    .then(refresh)
    .catch((e) => showError(e.message || String(e)));
})();
