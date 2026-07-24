(function () {
  const board = window.DcBoard || {};
  const {
    apiGet,
    toApiTradeDate,
    normalizeIsoDate,
    setDecisionCtx,
  } = board;

  const elStart = document.getElementById("start-date");
  const elEnd = document.getElementById("end-date");
  const elPresets = document.getElementById("range-presets");
  const elSearch = document.getElementById("board-search");
  const elDropdown = document.getElementById("board-dropdown");
  const btnLoad = document.getElementById("btn-load");
  const elHeader = document.getElementById("timing-header");
  const elChart = document.getElementById("timing-kline-chart");
  const elEmpty = document.getElementById("timing-empty");
  const elError = document.getElementById("page-error");
  const elVolChips = document.getElementById("vol-mode-chips");

  let selectedCode = "";
  let selectedName = "";
  let rangeDays = 60;
  let volMode = "vol"; // vol | amount
  let chartInst = null;
  let lastPayload = null;
  let searchTimer = null;
  let tradeDates = []; // ISO desc

  function showError(msg) {
    if (!elError) return;
    if (!msg) {
      elError.classList.add("hidden");
      elError.textContent = "";
      return;
    }
    elError.textContent = msg;
    elError.classList.remove("hidden");
  }

  function fmt(n, d) {
    if (n == null || n === "") return "—";
    const x = Number(n);
    if (Number.isNaN(x)) return "—";
    return x.toFixed(d == null ? 1 : d);
  }

  function labelSignal(s) {
    if (s === "buy") return "买入";
    if (s === "sell") return "卖出";
    return "观望";
  }

  function labelState(s) {
    if (s === "long") return "持有";
    if (s === "watch") return "观望";
    if (s === "flat") return "空仓";
    return s || "—";
  }

  function shiftIsoByDays(iso, delta) {
    const d = new Date(iso + "T00:00:00");
    d.setDate(d.getDate() + delta);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  /** 用交易日列表推算：结束日前 n 个交易日（不足则取最早） */
  function startFromTradeDays(endIso, n) {
    if (!tradeDates.length) return shiftIsoByDays(endIso, -Math.round(n * 1.5));
    const idx = tradeDates.indexOf(endIso);
    const endIdx = idx >= 0 ? idx : 0;
    const startIdx = Math.min(tradeDates.length - 1, endIdx + Math.max(0, n - 1));
    return tradeDates[startIdx] || endIso;
  }

  function applyPreset(days) {
    rangeDays = days;
    if (!elEnd.value) return;
    elStart.value = startFromTradeDays(elEnd.value, days);
    if (elPresets) {
      elPresets.querySelectorAll(".chip").forEach((c) => {
        c.classList.toggle("active", Number(c.dataset.days) === days);
      });
    }
  }

  async function loadTradeDates() {
    const data = await apiGet("/api/v1/timing/trade-dates?limit=183");
    tradeDates = (data.dates || [])
      .map((d) => normalizeIsoDate(d))
      .filter(Boolean);
    const latest = normalizeIsoDate(data.latest) || tradeDates[0] || "";
    if (latest && elEnd) elEnd.value = latest;
    applyPreset(60);
    return data;
  }

  function hideDropdown() {
    if (elDropdown) elDropdown.classList.add("hidden");
  }

  function showDropdown(items) {
    if (!elDropdown) return;
    if (!items.length) {
      elDropdown.innerHTML = '<div class="board-dropdown-item muted">无匹配结果</div>';
    } else {
      elDropdown.innerHTML = items
        .map((it) => {
          const code = it.industry_code || "";
          const name = it.industry_name || "";
          const ct = it.content_type || "";
          const score = it.score != null ? ` · Score ${fmt(it.score)}` : "";
          return `<button type="button" class="board-dropdown-item" data-code="${code}" data-name="${name}">[${ct}] ${name} (${code})${score}</button>`;
        })
        .join("");
    }
    elDropdown.classList.remove("hidden");
  }

  async function searchBoards(keyword) {
    const td = elEnd.value ? toApiTradeDate(elEnd.value) : "";
    const q = encodeURIComponent(keyword);
    const tdQ = td ? `&trade_date=${td}` : "";
    try {
      const data = await apiGet(
        `/api/v1/timing/boards/search?keyword=${q}&content_types=${encodeURIComponent("行业,概念")}&limit=40${tdQ}`
      );
      if ((data.items || []).length) {
        showDropdown(data.items);
        return;
      }
    } catch (_) {
      /* fallback */
    }
    const data = await apiGet(`/api/v1/chart/search?kind=board&keyword=${q}${tdQ}`);
    showDropdown(
      (data.items || []).map((it) => ({
        industry_code: it.industry_code,
        industry_name: it.industry_name,
        content_type: it.content_type,
      }))
    );
  }

  function renderHeader(payload) {
    if (!elHeader) return;
    const name = payload.name || selectedName || payload.industry_code || selectedCode;
    const code = payload.display_code || payload.industry_code || selectedCode;
    const t = payload.latest_timing || {};
    const snap = payload.snapshot || {};
    elHeader.innerHTML = [
      `<div class="timing-kline-title"><strong>${name}</strong> <span class="muted">${code}</span></div>`,
      `<div class="timing-kline-metrics">`,
      metric("综合分", fmt(t.score), true),
      metric("趋势", fmt(t.score_trend)),
      metric("资金", fmt(t.score_fund)),
      metric("量价", fmt(t.score_vp)),
      metric("情绪", fmt(t.score_sentiment)),
      metric("状态", labelState(t.position_state)),
      metric("信号", labelSignal(t.signal_type)),
      metric("收盘", fmt(snap.close ?? t.close, 2)),
      `</div>`,
    ].join("");
  }

  function metric(label, val, strong) {
    return `<div class="vp-metric"><span class="vp-metric-label">${label}</span><span class="vp-metric-val${strong ? " strong" : ""}">${val}</span></div>`;
  }

  function buildOption(payload) {
    const bars = payload.bars || [];
    const timing = payload.timing || [];
    const dates = bars.map((b) => b.trade_date);
    const ohlc = bars.map((b) => [Number(b.open), Number(b.close), Number(b.low), Number(b.high)]);
    const vols = bars.map((b) => Number(b.vol || 0));
    const amounts = bars.map((b) => Number(b.amount || 0) / 1e8);
    const ma20 = timing.map((t) => (t && t.ma20 != null ? Number(t.ma20) : null));
    const ma60 = timing.map((t) => (t && t.ma60 != null ? Number(t.ma60) : null));
    const scoreTrend = timing.map((t) => (t && t.score_trend != null ? Number(t.score_trend) : null));
    const scoreFund = timing.map((t) => (t && t.score_fund != null ? Number(t.score_fund) : null));
    const scoreVp = timing.map((t) => (t && t.score_vp != null ? Number(t.score_vp) : null));
    const scoreSent = timing.map((t) =>
      t && t.score_sentiment != null ? Number(t.score_sentiment) : null
    );

    const markPoints = [];
    timing.forEach((t, i) => {
      if (!t || (t.signal_type !== "buy" && t.signal_type !== "sell")) return;
      const isBuy = t.signal_type === "buy";
      const low = ohlc[i] ? ohlc[i][2] : null;
      const high = ohlc[i] ? ohlc[i][3] : null;
      markPoints.push({
        name: isBuy ? "买" : "卖",
        coord: [dates[i], isBuy ? low : high],
        value: isBuy ? "买" : "卖",
        symbol: "triangle",
        symbolRotate: isBuy ? 0 : 180,
        symbolSize: 12,
        itemStyle: { color: isBuy ? "#16a34a" : "#dc2626" },
        label: { show: true, formatter: isBuy ? "买" : "卖", fontSize: 10, color: "#fff" },
      });
    });

    const volSeriesData = volMode === "amount" ? amounts : vols;
    const volName = volMode === "amount" ? "成交金额(亿)" : "成交量";
    const volColors = bars.map((b) =>
      Number(b.close) >= Number(b.open) ? "rgba(239,68,68,0.65)" : "rgba(34,197,94,0.65)"
    );

    const grids = [
      { left: 56, right: 28, top: "4%", height: "30%" },
      { left: 56, right: 28, top: "38%", height: "9%" },
      { left: 56, right: 28, top: "50%", height: "9%" },
      { left: 56, right: 28, top: "62%", height: "9%" },
      { left: 56, right: 28, top: "74%", height: "9%" },
      { left: 56, right: 28, top: "86%", height: "9%" },
    ];

    function scoreSeries(name, data, color, gi) {
      return {
        name,
        type: "line",
        data,
        xAxisIndex: gi,
        yAxisIndex: gi,
        showSymbol: false,
        lineStyle: { width: 1.5, color },
        areaStyle: { color: color + "22" },
        markLine: {
          symbol: "none",
          silent: true,
          data: [
            { yAxis: 70, lineStyle: { color: "#16a34a", type: "dashed", width: 1 } },
            { yAxis: 40, lineStyle: { color: "#dc2626", type: "dashed", width: 1 } },
          ],
          label: { show: false },
        },
      };
    }

    return {
      animation: false,
      backgroundColor: "transparent",
      legend: {
        top: 0,
        right: 20,
        textStyle: { color: "#94a3b8", fontSize: 11 },
        data: ["K线", "MA20", "MA60", volName, "趋势", "资金", "量价", "情绪"],
      },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        formatter(params) {
          const idx = params && params[0] ? params[0].dataIndex : -1;
          if (idx < 0) return "";
          const b = bars[idx] || {};
          const t = timing[idx] || {};
          return [
            `<strong>${dates[idx]}</strong>`,
            `开 ${fmt(b.open, 2)} 高 ${fmt(b.high, 2)} 低 ${fmt(b.low, 2)} 收 ${fmt(b.close, 2)} (${fmt(b.pct_change, 2)}%)`,
            `成交量 ${fmt(b.vol, 0)} · 成交额 ${fmt(Number(b.amount || 0) / 1e8, 2)} 亿`,
            `Score ${fmt(t.score)} · ${labelSignal(t.signal_type)} · ${labelState(t.position_state)}`,
            `趋势 ${fmt(t.score_trend)} / 资金 ${fmt(t.score_fund)} / 量价 ${fmt(t.score_vp)} / 情绪 ${fmt(t.score_sentiment)}`,
            t.signal_reason ? `原因 ${t.signal_reason}` : "",
          ]
            .filter(Boolean)
            .join("<br/>");
        },
      },
      grid: grids,
      xAxis: grids.map((_, i) => ({
        type: "category",
        data: dates,
        gridIndex: i,
        axisLabel: { show: i === grids.length - 1, color: "#64748b", fontSize: 10 },
        axisLine: { lineStyle: { color: "#334155" } },
      })),
      yAxis: [
        { scale: true, gridIndex: 0, splitLine: { lineStyle: { color: "#1e293b" } }, axisLabel: { color: "#94a3b8" } },
        { scale: true, gridIndex: 1, splitLine: { show: false }, axisLabel: { color: "#94a3b8", fontSize: 10 } },
        { min: 0, max: 100, scale: false, gridIndex: 2, splitLine: { show: false }, axisLabel: { color: "#94a3b8", fontSize: 10 } },
        { min: 0, max: 100, scale: false, gridIndex: 3, splitLine: { show: false }, axisLabel: { color: "#94a3b8", fontSize: 10 } },
        { min: 0, max: 100, scale: false, gridIndex: 4, splitLine: { show: false }, axisLabel: { color: "#94a3b8", fontSize: 10 } },
        { min: 0, max: 100, scale: false, gridIndex: 5, splitLine: { show: false }, axisLabel: { color: "#94a3b8", fontSize: 10 } },
      ],
      dataZoom: [
        { type: "inside", xAxisIndex: [0, 1, 2, 3, 4, 5] },
        { type: "slider", xAxisIndex: [0, 1, 2, 3, 4, 5], bottom: 2, height: 16, borderColor: "#1e293b", fillerColor: "rgba(56,189,248,0.2)" },
      ],
      series: [
        {
          name: "K线",
          type: "candlestick",
          data: ohlc,
          xAxisIndex: 0,
          yAxisIndex: 0,
          itemStyle: {
            color: "#ef4444",
            color0: "#22c55e",
            borderColor: "#ef4444",
            borderColor0: "#22c55e",
          },
          markPoint: markPoints.length ? { data: markPoints } : undefined,
        },
        {
          name: "MA20",
          type: "line",
          data: ma20,
          xAxisIndex: 0,
          yAxisIndex: 0,
          showSymbol: false,
          lineStyle: { width: 1, color: "#f59e0b" },
        },
        {
          name: "MA60",
          type: "line",
          data: ma60,
          xAxisIndex: 0,
          yAxisIndex: 0,
          showSymbol: false,
          lineStyle: { width: 1, color: "#a855f7" },
        },
        {
          name: volName,
          type: "bar",
          data: volSeriesData,
          xAxisIndex: 1,
          yAxisIndex: 1,
          itemStyle: {
            color: (p) => volColors[p.dataIndex] || "#64748b",
          },
        },
        scoreSeries("趋势", scoreTrend, "#3b82f6", 2),
        scoreSeries("资金", scoreFund, "#22c55e", 3),
        scoreSeries("量价", scoreVp, "#f59e0b", 4),
        scoreSeries("情绪", scoreSent, "#ec4899", 5),
      ],
      graphic: [
        subLabel("成交量/额", "38%"),
        subLabel("趋势", "50%"),
        subLabel("资金", "62%"),
        subLabel("量价", "74%"),
        subLabel("情绪", "86%"),
      ],
    };
  }

  function subLabel(text, top) {
    return {
      type: "text",
      left: 8,
      top,
      style: { text, fill: "#64748b", fontSize: 11 },
      z: 100,
    };
  }

  function renderChart(payload) {
    if (!window.echarts || !elChart) return;
    if (!chartInst) chartInst = echarts.init(elChart);
    chartInst.setOption(buildOption(payload), true);
    if (elEmpty) elEmpty.classList.add("hidden");
  }

  async function loadChart() {
    showError("");
    if (!selectedCode) {
      showError("请先选择板块");
      return;
    }
    const end = elEnd.value ? toApiTradeDate(elEnd.value) : "";
    const start = elStart.value ? toApiTradeDate(elStart.value) : "";
    if (!end) {
      showError("请选择结束日期");
      return;
    }
    let url = `/api/v1/timing/boards/${encodeURIComponent(selectedCode)}/kline?trade_date=${end}&days=${rangeDays}`;
    if (start) url += `&start_date=${start}`;

    const data = await apiGet(url);
    lastPayload = data;
    if (typeof setDecisionCtx === "function") {
      setDecisionCtx({
        boardCode: selectedCode,
        boardName: selectedName || data.name,
        tradeDate: elEnd.value,
      });
    }
    renderHeader(data);
    renderChart(data);
  }

  // events
  if (elPresets) {
    elPresets.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      applyPreset(Number(btn.dataset.days || 60));
    });
  }

  if (elVolChips) {
    elVolChips.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      elVolChips.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      volMode = btn.dataset.mode || "vol";
      if (lastPayload) renderChart(lastPayload);
    });
  }

  if (elSearch) {
    elSearch.addEventListener("input", () => {
      clearTimeout(searchTimer);
      const kw = elSearch.value.trim();
      if (kw.length < 1) {
        hideDropdown();
        return;
      }
      searchTimer = setTimeout(() => searchBoards(kw).catch(() => hideDropdown()), 250);
    });
  }

  if (elDropdown) {
    elDropdown.addEventListener("click", (e) => {
      const btn = e.target.closest(".board-dropdown-item[data-code]");
      if (!btn) return;
      selectedCode = btn.dataset.code || "";
      selectedName = btn.dataset.name || "";
      if (elSearch) elSearch.value = `${selectedName} (${selectedCode})`;
      hideDropdown();
    });
  }

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#board-picker")) hideDropdown();
  });

  btnLoad.addEventListener("click", () => {
    loadChart().catch((err) => showError(err.message || String(err)));
  });

  window.addEventListener("resize", () => chartInst && chartInst.resize());

  // URL ?code= & end=
  function readQuery() {
    const q = new URLSearchParams(window.location.search);
    const code = q.get("code") || q.get("industry_code") || "";
    const name = q.get("name") || "";
    const end = normalizeIsoDate(q.get("end") || q.get("trade_date") || "");
    const days = Number(q.get("days") || 0);
    if (code) {
      selectedCode = code;
      selectedName = name;
      if (elSearch) elSearch.value = name ? `${name} (${code})` : code;
    }
    if (end && elEnd) elEnd.value = end;
    if (days === 20 || days === 60 || days === 120) rangeDays = days;
  }

  readQuery();
  loadTradeDates()
    .then(() => {
      if (selectedCode) return loadChart();
      // 无板块时拉排行第一只作默认
      const td = elEnd.value ? toApiTradeDate(elEnd.value) : "";
      return apiGet(
        `/api/v1/timing/rank?trade_date=${td}&content_types=${encodeURIComponent("行业,概念")}&top=1&sort=score`
      ).then((data) => {
        const item = (data.items || [])[0];
        if (!item) return;
        selectedCode = item.industry_code;
        selectedName = item.industry_name || "";
        if (elSearch) elSearch.value = `${selectedName} (${selectedCode})`;
        return loadChart();
      });
    })
    .catch((err) => showError(err.message || String(err)));
})();
