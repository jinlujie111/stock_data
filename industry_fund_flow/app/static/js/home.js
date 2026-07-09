(function () {
  const { apiGet, normalizeIsoDate, initTradeDateCalendar } = window.DcBoard;
  const elDate = document.getElementById("breadth-date");
  const elGrid = document.getElementById("breadth-metrics");
  const elEmpty = document.getElementById("breadth-empty");
  const elError = document.getElementById("breadth-error");
  const elSummary = document.getElementById("breadth-summary");
  const elTrendChart = document.getElementById("breadth-trend-chart");
  const elTrendEmpty = document.getElementById("breadth-trend-empty");
  const elMarketSentimentSummary = document.getElementById("market-sentiment-summary");
  const elMarketSentimentChart = document.getElementById("market-sentiment-chart");
  const elMarketSentimentEmpty = document.getElementById("market-sentiment-empty");

  let trendChart = null;
  let marketSentimentChart = null;

  const SENTIMENT_BANDS = [
    { min: 0, max: 10, label: "0~10 躺平", color: "rgba(100, 116, 139, 0.12)" },
    { min: 10, max: 20, label: "10~20 冰点", color: "rgba(59, 130, 246, 0.08)" },
    { min: 20, max: 40, label: "20~40 偏弱", color: "rgba(34, 197, 94, 0.06)" },
    { min: 40, max: 60, label: "40~60 中性", color: "rgba(250, 204, 21, 0.06)" },
    { min: 60, max: 80, label: "60~80 偏强", color: "rgba(249, 115, 22, 0.07)" },
    { min: 80, max: 90, label: "80~90 高潮", color: "rgba(239, 68, 68, 0.08)" },
    { min: 90, max: 100, label: "90~100 极度高潮", color: "rgba(168, 85, 247, 0.09)" },
  ];

  function sentimentMarkAreas() {
    return SENTIMENT_BANDS.map((band) => [
      {
        yAxis: band.min,
        itemStyle: { color: band.color },
        label: {
          show: true,
          color: "#94a3b8",
          fontSize: 11,
          position: "insideTopLeft",
          formatter: band.label,
        },
      },
      { yAxis: band.max },
    ]);
  }

  function sentimentMarkLines() {
    return [10, 20, 80, 90].map((value) => ({
      yAxis: value,
      label: {
        show: true,
        formatter: `${value}`,
        color: "#cbd5e1",
        fontSize: 11,
      },
      lineStyle: {
        color: "rgba(148, 163, 184, 0.5)",
        type: "dashed",
        width: 1,
      },
    }));
  }

  function fmtValue(val, fmt) {
    if (val === null || val === undefined || val === "") return "—";
    if (fmt === "int") return Number(val).toLocaleString("zh-CN");
    if (fmt === "pct") {
      const n = Number(val);
      if (Number.isNaN(n)) return val;
      const pct = n <= 1 && n >= -1 ? n * 100 : n;
      return pct.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) + "%";
    }
    return val;
  }

  function renderMetrics(payload) {
    if (!payload.data) {
      elGrid.innerHTML = "";
      elEmpty.classList.remove("hidden");
      elSummary.textContent = payload.trade_date
        ? `${payload.trade_date} 暂无市场广度数据`
        : "暂无市场广度数据";
      return;
    }
    elEmpty.classList.add("hidden");
    const data = payload.data;
    elGrid.innerHTML = payload.metrics
      .filter((m) => m.key !== "trade_date")
      .map((m) => {
        const val = data[m.key];
        let cls = "metric-value";
        if (m.key === "advance_cnt" || m.key === "limit_up_cnt") cls += " metric-up";
        if (m.key === "decline_cnt" || m.key === "limit_down_cnt") cls += " metric-down";
        return (
          `<div class="metric-card">` +
          `<div class="metric-label">${m.label}</div>` +
          `<div class="${cls}">${fmtValue(val, m.fmt)}</div>` +
          `</div>`
        );
      })
      .join("");
    elSummary.textContent = `交易日期 ${data.trade_date} · 沪深 A 股全市场广度`;
  }

  function renderTrendChart(items) {
    if (!items || !items.length) {
      if (trendChart) {
        trendChart.dispose();
        trendChart = null;
      }
      elTrendChart.style.display = "none";
      elTrendEmpty.classList.remove("hidden");
      return;
    }

    elTrendEmpty.classList.add("hidden");
    elTrendChart.style.display = "block";

    if (!trendChart) {
      trendChart = echarts.init(elTrendChart);
      window.addEventListener("resize", () => trendChart && trendChart.resize());
    }

    const dates = items.map((r) => r.trade_date);
    const advance = items.map((r) => r.advance_cnt);
    const decline = items.map((r) => r.decline_cnt);

    trendChart.setOption({
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        backgroundColor: "#1a2332",
        borderColor: "#2d3748",
        textStyle: { color: "#e2e8f0", fontSize: 12 },
        formatter(params) {
          const lines = [`${params[0].axisValue}`];
          params.forEach((p) => {
            lines.push(`${p.marker}${p.seriesName}：${Number(p.value).toLocaleString("zh-CN")}`);
          });
          return lines.join("<br/>");
        },
      },
      legend: {
        data: ["上涨家数", "下跌家数"],
        top: 0,
        right: 0,
        textStyle: { color: "#94a3b8", fontSize: 12 },
      },
      grid: { left: 48, right: 16, top: 36, bottom: 28 },
      xAxis: {
        type: "category",
        data: dates,
        boundaryGap: false,
        axisLine: { lineStyle: { color: "#334155" } },
        axisLabel: { color: "#94a3b8", fontSize: 11 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#1e293b" } },
        axisLabel: {
          color: "#94a3b8",
          fontSize: 11,
          formatter: (v) => (v >= 1000 ? v / 1000 + "k" : v),
        },
      },
      series: [
        {
          name: "上涨家数",
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 5,
          data: advance,
          lineStyle: { width: 2, color: "#f87171" },
          itemStyle: { color: "#f87171" },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(248, 113, 113, 0.25)" },
                { offset: 1, color: "rgba(248, 113, 113, 0)" },
              ],
            },
          },
        },
        {
          name: "下跌家数",
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 5,
          data: decline,
          lineStyle: { width: 2, color: "#4ade80" },
          itemStyle: { color: "#4ade80" },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(74, 222, 128, 0.25)" },
                { offset: 1, color: "rgba(74, 222, 128, 0)" },
              ],
            },
          },
        },
      ],
    });
  }

  function renderMarketSentiment(items) {
    if (!items || !items.length) {
      if (marketSentimentChart) {
        marketSentimentChart.dispose();
        marketSentimentChart = null;
      }
      elMarketSentimentChart.style.display = "none";
      elMarketSentimentEmpty.classList.remove("hidden");
      elMarketSentimentSummary.textContent = "暂无大盘情绪数据";
      return;
    }

    const latest = items[items.length - 1];
    elMarketSentimentSummary.textContent = `最新交易日 ${latest.trade_date} · 大盘情绪 ${fmtValue(latest.score, "num")} 分`;
    elMarketSentimentEmpty.classList.add("hidden");
    elMarketSentimentChart.style.display = "block";

    if (!marketSentimentChart) {
      marketSentimentChart = echarts.init(elMarketSentimentChart);
      window.addEventListener("resize", () => marketSentimentChart && marketSentimentChart.resize());
    }

    marketSentimentChart.setOption({
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        backgroundColor: "#1a2332",
        borderColor: "#2d3748",
        textStyle: { color: "#e2e8f0", fontSize: 12 },
        formatter(params) {
          const item = params[0];
          return `${item.axisValue}<br/>${item.marker}大盘情绪：${Number(item.value).toFixed(1)}`;
        },
      },
      grid: { left: 48, right: 16, top: 20, bottom: 28 },
      xAxis: {
        type: "category",
        data: items.map((r) => r.trade_date),
        boundaryGap: false,
        axisLine: { lineStyle: { color: "#334155" } },
        axisLabel: { color: "#94a3b8", fontSize: 11 },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        splitLine: { lineStyle: { color: "#1e293b" } },
        axisLabel: { color: "#94a3b8", fontSize: 11 },
      },
      series: [
        {
          name: "大盘情绪",
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 5,
          data: items.map((r) => r.score),
          lineStyle: { width: 2, color: "#60a5fa" },
          itemStyle: { color: "#60a5fa" },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(96, 165, 250, 0.25)" },
                { offset: 1, color: "rgba(96, 165, 250, 0)" },
              ],
            },
          },
          markLine: {
            symbol: "none",
            silent: true,
            data: sentimentMarkLines(),
          },
          markArea: {
            silent: true,
            data: sentimentMarkAreas(),
          },
        },
      ],
    });
  }

  async function loadBreadth() {
    elError.classList.add("hidden");
    const td = elDate.value;
    const url = td
      ? `/api/market-breadth?trade_date=${encodeURIComponent(td)}`
      : "/api/market-breadth";
    const payload = await apiGet(url);
    if (payload.trade_date) {
      const iso = normalizeIsoDate(payload.trade_date);
      if (iso && elDate.value !== iso) elDate.value = iso;
    }
    renderMetrics(payload);
  }

  async function loadTrend() {
    const res = await apiGet("/api/market-breadth/history?days=30");
    renderTrendChart(res.items);
  }

  async function loadMarketSentiment() {
    const res = await apiGet("/api/v1/sentiment/history?days=30");
    renderMarketSentiment((res.market && res.market.items) || []);
  }

  elDate.addEventListener("change", () => {
    loadBreadth().catch((err) => {
      elError.textContent = err.message;
      elError.classList.remove("hidden");
    });
  });

  initTradeDateCalendar(elDate, "/api/market-breadth/trade-dates?limit=90")
    .then(() => Promise.all([loadBreadth(), loadTrend(), loadMarketSentiment()]))
    .catch((err) => {
      elError.textContent = err.message;
      elError.classList.remove("hidden");
    });
})();
