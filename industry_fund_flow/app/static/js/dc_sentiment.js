(function () {
  const { apiGet, fmtNum, initTradeDateCalendar, toApiTradeDate } = window.DcBoard;

  const elDate = document.getElementById("trade-date");
  const elDays = document.getElementById("days");
  const elKeyword = document.getElementById("board-keyword");
  const elFilterHint = document.getElementById("filter-hint");
  const elPageError = document.getElementById("page-error");
  const elSummaryText = document.getElementById("summary-text");
  const elBoardPill = document.getElementById("board-pill");
  const elSummaryMetrics = document.getElementById("summary-metrics");
  const elChartEmpty = document.getElementById("chart-empty");
  const elChart = document.getElementById("sentiment-chart");
  const btnResolveBoard = document.getElementById("btn-resolve-board");
  const btnQuery = document.getElementById("btn-query");

  let chart = null;
  let selectedBoard = null;

  function showError(msg) {
    elPageError.textContent = msg;
    elPageError.classList.remove("hidden");
  }

  function clearError() {
    elPageError.classList.add("hidden");
  }

  function fmtScore(val) {
    if (val === null || val === undefined || val === "") return "—";
    return fmtNum(val, 1);
  }

  function scoreTone(score) {
    const n = Number(score);
    if (Number.isNaN(n)) return "";
    if (n >= 75) return "cell-rise";
    if (n <= 35) return "cell-fall";
    return "";
  }

  function renderBoard(board) {
    selectedBoard = board || null;
    if (!board) {
      elBoardPill.textContent = "";
      elBoardPill.classList.add("hidden");
      return;
    }
    elBoardPill.textContent = `${board.content_type || "板块"} · ${board.industry_name || board.industry_code} (${board.industry_code})`;
    elBoardPill.classList.remove("hidden");
  }

  function renderSummary(payload) {
    const marketScore = payload.market?.latest_score;
    const sectorScore = payload.sector?.latest_score;
    const board = payload.board;

    renderBoard(board);
    elSummaryText.textContent = board
      ? `截至 ${payload.trade_date}，大盘情绪与 ${board.industry_name || board.industry_code} 的板块情绪对比。`
      : `截至 ${payload.trade_date}，仅找到大盘情绪数据，未匹配到板块。`;

    elSummaryMetrics.innerHTML = `
      <div class="sentiment-metric">
        <span>大盘情绪</span>
        <strong class="${scoreTone(marketScore)}">${fmtScore(marketScore)}</strong>
      </div>
      <div class="sentiment-metric">
        <span>板块情绪</span>
        <strong class="${scoreTone(sectorScore)}">${fmtScore(sectorScore)}</strong>
      </div>
      <div class="sentiment-metric">
        <span>历史区间</span>
        <strong>${payload.days} 天</strong>
      </div>
      <div class="sentiment-metric">
        <span>板块</span>
        <strong>${board ? board.industry_name || board.industry_code : "未匹配"}</strong>
      </div>
    `;
  }

  function renderChart(payload) {
    const marketItems = payload.market?.items || [];
    const sectorItems = payload.sector?.items || [];
    if (!marketItems.length) {
      if (chart) {
        chart.dispose();
        chart = null;
      }
      elChart.style.display = "none";
      elChartEmpty.classList.remove("hidden");
      return;
    }

    const sectorScoreMap = new Map(sectorItems.map((item) => [item.trade_date, item.score]));
    const dates = marketItems.map((item) => item.trade_date);
    const marketScores = marketItems.map((item) => item.score);
    const sectorScores = dates.map((d) => sectorScoreMap.get(d) ?? null);
    const sectorName = payload.board?.industry_name || payload.board?.industry_code || "板块情绪";

    elChartEmpty.classList.add("hidden");
    elChart.style.display = "block";
    if (!chart) {
      chart = echarts.init(elChart);
      window.addEventListener("resize", () => chart && chart.resize());
    }

    chart.setOption(
      {
        backgroundColor: "transparent",
        animation: false,
        tooltip: {
          trigger: "axis",
          backgroundColor: "#1a2332",
          borderColor: "#2d3748",
          textStyle: { color: "#e2e8f0", fontSize: 12 },
          formatter(params) {
            const lines = [`${params[0].axisValue}`];
            params.forEach((p) => {
              lines.push(`${p.marker}${p.seriesName}：${fmtScore(p.value)}`);
            });
            return lines.join("<br/>");
          },
        },
        legend: {
          data: ["大盘情绪", sectorName],
          top: 0,
          textStyle: { color: "#94a3b8", fontSize: 12 },
        },
        grid: { left: 48, right: 18, top: 36, bottom: 52 },
        xAxis: {
          type: "category",
          data: dates,
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
        dataZoom: [
          { type: "inside", start: Math.max(0, 100 - (180 / dates.length) * 100), end: 100 },
          { type: "slider", bottom: 10, height: 18, borderColor: "#334155", textStyle: { color: "#64748b" } },
        ],
        series: [
          {
            name: "大盘情绪",
            type: "line",
            smooth: true,
            symbol: "none",
            data: marketScores,
            lineStyle: { width: 2, color: "#60a5fa" },
            itemStyle: { color: "#60a5fa" },
          },
          {
            name: sectorName,
            type: "line",
            smooth: true,
            symbol: "none",
            connectNulls: false,
            data: sectorScores,
            lineStyle: { width: 2, color: "#f59e0b" },
            itemStyle: { color: "#f59e0b" },
          },
        ],
      },
      true
    );
  }

  async function resolveBoard() {
    clearError();
    const params = new URLSearchParams();
    if (elDate.value) params.set("trade_date", toApiTradeDate(elDate.value));
    const keyword = elKeyword.value.trim();
    if (selectedBoard?.industry_code && !keyword) {
      params.set("industry_code", selectedBoard.industry_code);
    } else if (keyword) {
      params.set("keyword", keyword);
    }
    const data = await apiGet(`/api/v1/sentiment/resolve-board?${params}`);
    renderBoard(data.item || null);
    return data.item || null;
  }

  function buildHistoryUrl() {
    const params = new URLSearchParams();
    if (elDate.value) params.set("trade_date", toApiTradeDate(elDate.value));
    params.set("days", elDays.value || "365");
    if (selectedBoard?.industry_code) {
      params.set("industry_code", selectedBoard.industry_code);
    } else {
      const keyword = elKeyword.value.trim();
      if (keyword) params.set("keyword", keyword);
    }
    return `/api/v1/sentiment/history?${params}`;
  }

  async function queryHistory() {
    clearError();
    elFilterHint.textContent = "查询中…";
    try {
      const payload = await apiGet(buildHistoryUrl());
      renderSummary(payload);
      renderChart(payload);
      if (payload.board) {
        selectedBoard = payload.board;
      }
      elFilterHint.textContent = "";
    } catch (err) {
      elFilterHint.textContent = "";
      showError(err.message || String(err));
    }
  }

  btnResolveBoard.addEventListener("click", async () => {
    try {
      elFilterHint.textContent = "定位板块中…";
      await resolveBoard();
      elFilterHint.textContent = selectedBoard ? "已定位板块，可直接查询历史。" : "未匹配到板块，可调整关键词。";
    } catch (err) {
      elFilterHint.textContent = "";
      showError(err.message || String(err));
    }
  });

  btnQuery.addEventListener("click", async () => {
    if (!selectedBoard && elKeyword.value.trim()) {
      await resolveBoard();
    }
    await queryHistory();
  });

  elKeyword.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      btnQuery.click();
    }
  });

  (async function init() {
    try {
      await initTradeDateCalendar(elDate, "/api/v1/sentiment/trade-dates?limit=90");
      await queryHistory();
    } catch (err) {
      showError(err.message || String(err));
    }
  })();
})();
