(function () {
  const board = window.DcBoard || {};
  const kline = window.DcKline || {};
  const { funnelBoardLinks, stockKlineLink, consumeFunnelParams, pickBoard } = board;
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
  const elDetailStocksHead = document.getElementById("detail-stocks-head");
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
  let stockSortKey = "vol_ratio_20";
  let stockSortDir = "desc";

  const STOCK_COLUMNS = [
    { key: "ts_code", label: "代码", sortable: false },
    { key: "stock_name", label: "名称", sortable: false },
    { key: "pct_chg", label: "涨跌幅%", sortable: true },
    { key: "vol_ratio_20", label: "量比", sortable: true },
    { key: "vol_streak_days", label: "连续放量", sortable: true },
    { key: "is_breakout_strict", label: "严格突破", sortable: true },
    { key: "vp_pattern", label: "量价形态", sortable: true },
    { key: "vp_pattern_score", label: "形态分", sortable: true },
    { key: "circ_mv", label: "市值", sortable: true },
  ];

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
    // 量价 signal_type 是状态标签(regime)，不是买卖点；买卖事件见 /dc/timing-signals
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

  /** VP 指标配色（榜单与详情共用） */
  function scoreTier(n) {
    const v = Number(n);
    if (Number.isNaN(v)) return "";
    if (v >= 80) return "vp-l5";
    if (v >= 60) return "vp-l4";
    if (v >= 40) return "vp-l3";
    if (v >= 20) return "vp-l2";
    return "vp-l1";
  }

  function statusTone(key) {
    return (
      {
        mainline_burst: "vp-st-mainline",
        trend_up: "vp-st-trend",
        range_bound: "vp-st-range",
        weak: "vp-st-weak",
        ebbing: "vp-st-ebbing",
      }[key] || ""
    );
  }

  function signalTone(key) {
    return (
      {
        main_rise: "vp-sig-rise",
        launch: "vp-sig-launch",
        distribution: "vp-sig-dist",
        ebbing: "vp-sig-ebbing",
        none: "vp-sig-none",
      }[key] || "vp-sig-none"
    );
  }

  function volRatioTone(n) {
    const v = Number(n);
    if (Number.isNaN(v)) return "";
    if (v >= 1.8) return "vp-l5";
    if (v >= 1.3) return "vp-l4";
    if (v >= 1.0) return "vp-l3";
    if (v >= 0.8) return "vp-l2";
    return "vp-l1";
  }

  function ratioPctTone(n) {
    const v = Number(n);
    if (Number.isNaN(v)) return "";
    const pctVal = v <= 1 ? v * 100 : v;
    if (pctVal >= 80) return "vp-l5";
    if (pctVal >= 65) return "vp-l4";
    if (pctVal >= 50) return "vp-l3";
    if (pctVal >= 35) return "vp-l2";
    return "vp-l1";
  }

  function breakoutPctTone(n) {
    const v = Number(n);
    if (Number.isNaN(v)) return "";
    const pctVal = v <= 1 ? v * 100 : v;
    if (pctVal >= 25) return "vp-l5";
    if (pctVal >= 15) return "vp-l4";
    if (pctVal >= 8) return "vp-l3";
    if (pctVal >= 3) return "vp-l2";
    return "vp-l1";
  }

  function continuityTone(n) {
    const v = Number(n);
    if (Number.isNaN(v)) return "";
    if (v >= 25) return "vp-l5";
    if (v >= 15) return "vp-l4";
    if (v >= 8) return "vp-l3";
    if (v >= 3) return "vp-l2";
    return "vp-l1";
  }

  function trendRetTone(n) {
    const v = Number(n);
    if (Number.isNaN(v)) return "";
    if (v >= 15) return "vp-l5";
    if (v >= 8) return "vp-l4";
    if (v >= 3) return "vp-l3";
    if (v >= 0) return "vp-l2";
    return "vp-l1";
  }

  function leaderTone(n) {
    const v = Number(n);
    if (Number.isNaN(v)) return "";
    if (v >= 3) return "vp-l5";
    if (v >= 2.2) return "vp-l4";
    if (v >= 1.5) return "vp-l3";
    if (v >= 1) return "vp-l2";
    return "vp-l1";
  }

  function rankTone(rank) {
    const r = Number(rank);
    if (Number.isNaN(r)) return "";
    if (r <= 3) return "vp-l5";
    if (r <= 10) return "vp-l4";
    if (r <= 20) return "vp-l3";
    if (r <= 35) return "vp-l2";
    return "vp-l1";
  }

  function streakDaysTone(d) {
    const v = Number(d);
    if (Number.isNaN(v)) return "";
    if (v >= 6) return "vp-l5";
    if (v >= 4) return "vp-l4";
    if (v >= 2) return "vp-l3";
    if (v >= 1) return "vp-l2";
    return "vp-l1";
  }

  function vpVal(text, tone, badge) {
    if (!tone) return text ?? "—";
    const cls = badge ? `vp-val vp-badge ${tone}` : `vp-val ${tone}`;
    return `<span class="${cls}">${text ?? "—"}</span>`;
  }

  function metricItems(pairs) {
    return pairs
      .map(([k, v, tone, badge]) => {
        const valCls = tone ? `metric-value ${tone}${badge ? " metric-value--badge" : ""}` : "metric-value";
        return (
          `<div class="metric-item"><span class="metric-label">${k}</span>` +
          `<span class="${valCls}">${v ?? "—"}</span></div>`
        );
      })
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
      ["VP 综合分", fmt(s.vp_score, 1), scoreTier(s.vp_score)],
      ["排名", s.rank_vp != null ? "#" + s.rank_vp : "—", rankTone(s.rank_vp)],
      ["状态", STATUS_LABEL[s.vp_status] || s.vp_status, statusTone(s.vp_status), true],
      ["量价标签", labelSignal(s.signal_type), signalTone(s.signal_type), true],
      ["行业量比", fmt(s.industry_vol_ratio_20, 2), volRatioTone(s.industry_vol_ratio_20)],
      ["上涨占比", pct(s.rising_ratio), ratioPctTone(s.rising_ratio)],
      ["突破占比", pct(s.breakout_ratio), breakoutPctTone(s.breakout_ratio)],
      ["连续放量强度", fmt(s.continuity_strength, 2), continuityTone(s.continuity_strength)],
      ["连续放量天数", s.amount_streak_days ?? "—", streakDaysTone(s.amount_streak_days)],
      ["20日趋势", retPct(s.trend_return_20d), trendRetTone(s.trend_return_20d)],
      ["龙头强度", fmt(s.leader_strength, 2), leaderTone(s.leader_strength)],
      ["成分数", s.member_cnt],
    ];
    const subs = [
      ["子分·连续", fmt(s.score_continuity, 1), scoreTier(s.score_continuity)],
      ["子分·量比", fmt(s.score_vol, 1), scoreTier(s.score_vol)],
      ["子分·趋势", fmt(s.score_trend, 1), scoreTier(s.score_trend)],
      ["子分·上涨", fmt(s.score_breadth, 1), scoreTier(s.score_breadth)],
      ["子分·突破", fmt(s.score_breakout, 1), scoreTier(s.score_breakout)],
      ["子分·龙头", fmt(s.score_leader, 1), scoreTier(s.score_leader)],
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

  function fmtMvYi(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return "—";
    return n.toFixed(2) + "亿";
  }

  function pctChgClass(v) {
    const n = Number(v);
    if (Number.isNaN(n)) return "";
    if (n > 0) return "cell-rise";
    if (n < 0) return "cell-fall";
    return "";
  }

  function volRatioClass(v) {
    const n = Number(v);
    if (Number.isNaN(n)) return "";
    if (n > 1) return "cell-rise";
    if (n < 1) return "cell-fall";
    return "";
  }

  function fmtPctSigned(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return "—";
    return (n > 0 ? "+" : "") + n.toFixed(2) + "%";
  }

  function renderStockHead() {
    if (!elDetailStocksHead) return;
    elDetailStocksHead.innerHTML =
      "<tr>" +
      STOCK_COLUMNS.map((col) => {
        if (!col.sortable) return `<th>${col.label}</th>`;
        const active = col.key === stockSortKey;
        const arrow = active ? (stockSortDir === "asc" ? " ▲" : " ▼") : "";
        return `<th class="sortable-th" data-sort="${col.key}" title="点击排序">${col.label}${arrow}</th>`;
      }).join("") +
      "<th>下一步</th></tr>";
  }

  function renderStockRows(items) {
    if (!elDetailStocks) return;
    elDetailStocks.innerHTML = "";
    const boardCode = detailIndustryCode || "";
    const boardName = (elDetailTitle && elDetailTitle.textContent.split("·")[0].trim()) || "";
    (items || []).forEach((row) => {
      const tr = document.createElement("tr");
      const pctCls = pctChgClass(row.pct_chg);
      const volCls = volRatioClass(row.vol_ratio_20);
      const next =
        stockKlineLink
          ? stockKlineLink(row.ts_code, row.stock_name, elDate.value, boardCode, boardName)
          : "—";
      tr.innerHTML =
        `<td>${row.ts_code}</td>` +
        `<td>${row.stock_name || "—"}</td>` +
        `<td class="${pctCls}">${fmtPctSigned(row.pct_chg)}</td>` +
        `<td class="${volCls}">${fmt(row.vol_ratio_20, 2)}</td>` +
        `<td>${vpVal(row.vol_streak_days ?? "—", streakDaysTone(row.vol_streak_days))}</td>` +
        `<td>${row.is_breakout_strict ? vpVal("是", "vp-l5", true) : "—"}</td>` +
        `<td>${vpVal(labelPattern(row.vp_pattern), patternTone(row.vp_pattern), true)}</td>` +
        `<td>${vpVal(fmt(row.vp_pattern_score, 0), scoreTier(row.vp_pattern_score))}</td>` +
        `<td>${fmtMvYi(row.circ_mv_yi)}</td>` +
        `<td>${next}</td>`;
      elDetailStocks.appendChild(tr);
    });
  }

  function patternTone(key) {
    return (
      {
        trend_confirm: "vp-st-mainline",
        weak_rise: "vp-st-trend",
        consolidation: "vp-st-range",
        distribution: "vp-st-ebbing",
      }[key] || "vp-sig-none"
    );
  }

  async function loadDetailStocks(code) {
    if (!code) return;
    const { td, w } = queryParams();
    const stocks = await apiGet(
      `/api/v1/vp/industries/${encodeURIComponent(code)}/stocks?trade_date=${encodeURIComponent(td)}` +
        `&window=${w}&limit=50&sort=${encodeURIComponent(stockSortKey)}&order=${encodeURIComponent(stockSortDir)}`
    );
    renderStockHead();
    renderStockRows(stocks.items || []);
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
      "<tr><th>#</th><th>板块</th><th>类型</th><th>VP分</th><th>状态</th><th>量价标签</th>" +
      "<th>行业量比</th><th>上涨占比</th><th>突破占比</th><th>连续强度</th><th>20日趋势</th><th>龙头</th><th>下一步</th><th>操作</th></tr>";
    elBody.innerHTML = "";
    if (!items.length) {
      showTableEmpty(EMPTY_MSG_RANK);
      return;
    }
    hideTableEmpty();
    items.forEach((row, idx) => {
      const tr = document.createElement("tr");
      if (row.industry_code === detailIndustryCode) tr.classList.add("vp-row-active");
      const statusText = STATUS_LABEL[row.vp_status] || row.vp_status || "—";
      const signalText = labelSignal(row.signal_type);
      const nextHtml = funnelBoardLinks
        ? funnelBoardLinks(row.industry_code, row.industry_name, elDate.value, { primary: "stock" })
        : "—";
      tr.innerHTML =
        `<td>${row.rank_vp || idx + 1}</td>` +
        `<td>${row.industry_name || row.industry_code}</td>` +
        `<td>${row.content_type || "—"}</td>` +
        `<td>${vpVal(fmt(row.vp_score, 1), scoreTier(row.vp_score))}</td>` +
        `<td>${vpVal(statusText, statusTone(row.vp_status), true)}</td>` +
        `<td>${vpVal(signalText, signalTone(row.signal_type), true)}</td>` +
        `<td>${vpVal(fmt(row.industry_vol_ratio_20, 2), volRatioTone(row.industry_vol_ratio_20))}</td>` +
        `<td>${vpVal(pct(row.rising_ratio), ratioPctTone(row.rising_ratio))}</td>` +
        `<td>${vpVal(pct(row.breakout_ratio), breakoutPctTone(row.breakout_ratio))}</td>` +
        `<td>${vpVal(fmt(row.continuity_strength, 2), continuityTone(row.continuity_strength))}</td>` +
        `<td>${vpVal(retPct(row.trend_return_20d), trendRetTone(row.trend_return_20d))}</td>` +
        `<td>${vpVal(fmt(row.leader_strength, 2), leaderTone(row.leader_strength))}</td>` +
        `<td>${nextHtml}</td>` +
        `<td><button type="button" class="btn-vp-detail${row.industry_code === detailIndustryCode ? " is-active" : ""}" data-code="${row.industry_code}" data-name="${row.industry_name || ""}">数据分析</button></td>`;
      elBody.appendChild(tr);
    });
    elBody.querySelectorAll(".btn-vp-detail").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (pickBoard) pickBoard(btn.dataset.code, btn.dataset.name, elDate.value);
        loadDetail(btn.dataset.code);
      });
    });
  }

  function markActiveDetailRow(code) {
    elBody.querySelectorAll("tr").forEach((tr) => tr.classList.remove("vp-row-active"));
    elBody.querySelectorAll(".btn-vp-detail").forEach((btn) => btn.classList.remove("is-active"));
    if (!code) return;
    const btn = elBody.querySelector(`.btn-vp-detail[data-code="${CSS.escape(code)}"]`);
    if (btn) {
      btn.classList.add("is-active");
      const tr = btn.closest("tr");
      if (tr) tr.classList.add("vp-row-active");
    }
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
    markActiveDetailRow(code);
    elDetailCard.classList.remove("hidden");
    prepareKlineRangeForAnalysis(60);
    showKlineStatus("加载 K 线…", "kline-loading");

    const { td, w } = queryParams();
    const data = await apiGet(
      `/api/v1/vp/industries/${encodeURIComponent(code)}?trade_date=${encodeURIComponent(td)}&window=${w}`
    );
    const s = data.score || {};
    if (pickBoard) pickBoard(code, s.industry_name || code, td);
    elDetailTitle.textContent = `${s.industry_name || code} · VP ${fmt(s.vp_score, 1)}`;
    renderDetailMetrics(s);

    try {
      await loadVpKline(code);
    } catch (e) {
      const msg = "K 线加载失败: " + (e.message || String(e));
      showKlineStatus(msg, "table-empty kline-error");
      showError(msg);
    }

    try {
      await loadDetailStocks(code);
    } catch (e) {
      showError("成分股加载失败: " + (e.message || String(e)));
    }
    scrollToVpKline();
  }

  if (elDetailStocksHead) {
    elDetailStocksHead.addEventListener("click", (e) => {
      const th = e.target.closest(".sortable-th[data-sort]");
      if (!th || !detailIndustryCode) return;
      const key = th.dataset.sort;
      if (stockSortKey === key) {
        stockSortDir = stockSortDir === "desc" ? "asc" : "desc";
      } else {
        stockSortKey = key;
        stockSortDir = "desc";
      }
      loadDetailStocks(detailIndustryCode).catch((err) =>
        showError("成分股加载失败: " + (err.message || String(err)))
      );
    });
  }

  renderStockHead();

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
    .then(async () => {
      const funnel = consumeFunnelParams ? consumeFunnelParams({ dateEl: elDate }) : null;
      if (funnel && funnel.industry_code) {
        selectedBoards.set(funnel.industry_code, {
          industry_code: funnel.industry_code,
          industry_name: funnel.industry_name || funnel.industry_code,
          content_type: "",
        });
        renderSelectedBoards();
      }
      await refresh();
      if (funnel && funnel.industry_code) {
        await loadDetail(funnel.industry_code);
      }
    })
    .catch((e) => showError(e.message || String(e)));
})();
