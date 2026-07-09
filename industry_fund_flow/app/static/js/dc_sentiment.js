(function () {
  const { apiGet, fmtNum, initTradeDateCalendar, toApiTradeDate } = window.DcBoard;

  const elDate = document.getElementById("trade-date");
  const elDays = document.getElementById("days");
  const chipGroup = document.getElementById("content-type-chips");
  const elBoardSearch = document.getElementById("board-search");
  const elBoardDropdown = document.getElementById("board-dropdown");
  const elBoardSelected = document.getElementById("board-selected");
  const elBoardPicker = document.getElementById("board-picker");
  const elFilterHint = document.getElementById("filter-hint");
  const elPageError = document.getElementById("page-error");
  const elSummaryText = document.getElementById("summary-text");
  const elBoardPill = document.getElementById("board-pill");
  const elSummaryMetrics = document.getElementById("summary-metrics");
  const elChartEmpty = document.getElementById("chart-empty");
  const elChart = document.getElementById("sentiment-chart");
  const btnResetBoards = document.getElementById("btn-reset-boards");
  const btnQuery = document.getElementById("btn-query");

  let chart = null;
  let allBoards = [];
  let selectedTypes = ["行业", "概念"];
  const selectedBoards = new Map();
  let boardSearchTimer = null;

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

  function getContentTypesParam() {
    return selectedTypes.length ? selectedTypes.join(",") : "行业,概念";
  }

  function boardLabel(b) {
    return `[${b.content_type}] ${b.industry_name} (${b.industry_code})`;
  }

  function renderSelectedTags() {
    if (!selectedBoards.size) {
      elBoardSelected.innerHTML = '<span class="board-placeholder">未选择板块（展示默认强势板块）</span>';
      return;
    }
    elBoardSelected.innerHTML = Array.from(selectedBoards.values())
      .map(
        (b) =>
          `<span class="board-tag" data-code="${b.industry_code}">` +
          `${boardLabel(b)}<button type="button" aria-label="移除">×</button></span>`
      )
      .join("");
  }

  function renderBoardPill(board) {
    if (!board) {
      elBoardPill.textContent = "";
      elBoardPill.classList.add("hidden");
      return;
    }
    elBoardPill.textContent = `${board.content_type || "板块"} · ${board.industry_name || board.industry_code} (${board.industry_code})`;
    elBoardPill.classList.remove("hidden");
  }

  function hideDropdown() {
    elBoardDropdown.classList.add("hidden");
  }

  function matchBoard(board, q) {
    const text = `${board.industry_name} ${board.industry_code} ${board.content_type}`.toLowerCase();
    const tokens = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!tokens.length) return true;
    return tokens.every((t) => text.includes(t));
  }

  function renderDropdown(matches) {
    if (!matches.length) {
      elBoardDropdown.innerHTML = '<div class="board-option">无匹配板块</div>';
      elBoardDropdown.classList.remove("hidden");
      return;
    }
    elBoardDropdown.innerHTML = matches
      .slice(0, 50)
      .map(
        (b) =>
          `<button type="button" class="board-option" data-code="${b.industry_code}">` +
          `${boardLabel(b)}</button>`
      )
      .join("");
    elBoardDropdown.classList.remove("hidden");
  }

  async function fetchBoards(keyword) {
    const params = new URLSearchParams({
      trade_date: toApiTradeDate(elDate.value),
      content_types: getContentTypesParam(),
    });
    const kw = (keyword || "").trim();
    if (kw) params.set("keyword", kw);
    const data = await apiGet(`/api/v1/dragon/boards?${params}`);
    return data.items || [];
  }

  async function loadBoardOptions() {
    allBoards = await fetchBoards("");
    const keep = new Map();
    selectedBoards.forEach((b, code) => {
      if (allBoards.some((x) => x.industry_code === code)) keep.set(code, b);
    });
    selectedBoards.clear();
    keep.forEach((b, code) => selectedBoards.set(code, b));
    renderSelectedTags();
    elFilterHint.textContent = `共 ${allBoards.length} 个板块可选；输入名称或代码模糊匹配后点选；未选板块表示展示默认强势板块（类型：${getContentTypesParam().replace(",", "、")}）`;
  }

  function addBoard(code) {
    const board = allBoards.find((b) => b.industry_code === code);
    if (!board) return;
    selectedBoards.set(code, board);
    renderSelectedTags();
    elBoardSearch.value = "";
    hideDropdown();
  }

  function renderSummary(payload) {
    const marketScore = payload.market?.latest_score;
    const sectorScore = payload.sector?.latest_score;
    const board = payload.board;

    renderBoardPill(board);
    elSummaryText.textContent = board
      ? `截至 ${payload.trade_date}，展示 ${board.industry_name || board.industry_code} 的板块情绪。`
      : `截至 ${payload.trade_date}，未匹配到板块。`;

    elSummaryMetrics.innerHTML = `
      <div class="sentiment-metric">
        <span>板块情绪</span>
        <strong class="${scoreTone(sectorScore)}">${fmtScore(sectorScore)}</strong>
      </div>
      <div class="sentiment-metric">
        <span>历史区间</span>
        <strong>${payload.days} 天</strong>
      </div>
      <div class="sentiment-metric">
        <span>大盘情绪参考</span>
        <strong class="${scoreTone(marketScore)}">${fmtScore(marketScore)}</strong>
      </div>
    `;
  }

  function renderChart(payload) {
    const sectorItems = payload.sector?.items || [];
    if (!sectorItems.length) {
      if (chart) {
        chart.dispose();
        chart = null;
      }
      elChart.style.display = "none";
      elChartEmpty.classList.remove("hidden");
      return;
    }

    const dates = sectorItems.map((item) => item.trade_date);
    const sectorScores = sectorItems.map((item) => item.score);
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
          data: [sectorName],
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
          { type: "inside", start: Math.max(0, 100 - (30 / dates.length) * 100), end: 100 },
          { type: "slider", bottom: 10, height: 18, borderColor: "#334155", textStyle: { color: "#64748b" } },
        ],
        series: [
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

  function buildHistoryUrl() {
    const params = new URLSearchParams();
    if (elDate.value) params.set("trade_date", toApiTradeDate(elDate.value));
    params.set("days", elDays.value || "30");
    const boardCodes = Array.from(selectedBoards.keys());
    if (boardCodes.length) params.set("industry_code", boardCodes[0]);
    return `/api/v1/sentiment/history?${params}`;
  }

  async function queryHistory() {
    clearError();
    elFilterHint.textContent = "查询中…";
    try {
      const payload = await apiGet(buildHistoryUrl());
      renderSummary(payload);
      renderChart(payload);
      if (payload.board) renderBoardPill(payload.board);
      elFilterHint.textContent = "";
    } catch (err) {
      elFilterHint.textContent = "";
      showError(err.message || String(err));
    }
  }

  btnQuery.addEventListener("click", async () => {
    await queryHistory();
  });

  chipGroup.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const val = chip.dataset.value;
      if (chip.classList.contains("active")) {
        chip.classList.remove("active");
        selectedTypes = selectedTypes.filter((t) => t !== val);
      } else {
        chip.classList.add("active");
        if (!selectedTypes.includes(val)) selectedTypes.push(val);
      }
      if (!selectedTypes.length) {
        selectedTypes = ["行业", "概念"];
        chipGroup.querySelectorAll(".chip").forEach((c) => c.classList.add("active"));
      }
      loadBoardOptions().catch((err) => showError(err.message || String(err)));
    });
  });

  elBoardSearch.addEventListener("input", () => {
    const q = elBoardSearch.value;
    if (!q.trim()) {
      hideDropdown();
      return;
    }
    clearTimeout(boardSearchTimer);
    boardSearchTimer = setTimeout(async () => {
      try {
        const remote = await fetchBoards(q);
        const pool = remote.length ? remote : allBoards;
        const matches = pool.filter((b) => !selectedBoards.has(b.industry_code) && matchBoard(b, q));
        renderDropdown(matches);
      } catch (err) {
        showError(err.message || String(err));
      }
    }, 200);
  });
  elBoardSearch.addEventListener("focus", () => {
    if (elBoardSearch.value.trim()) {
      elBoardSearch.dispatchEvent(new Event("input"));
    }
  });
  elBoardSearch.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      btnQuery.click();
    }
  });
  elBoardDropdown.addEventListener("click", async (e) => {
    const btn = e.target.closest(".board-option[data-code]");
    if (!btn) return;
    const code = btn.dataset.code;
    if (!allBoards.some((b) => b.industry_code === code)) {
      const found = await fetchBoards(code);
      const board = found.find((b) => b.industry_code === code);
      if (board) allBoards.push(board);
    }
    addBoard(code);
  });
  elBoardSelected.addEventListener("click", (e) => {
    const tag = e.target.closest(".board-tag");
    if (!tag) return;
    if (e.target.tagName === "BUTTON") {
      selectedBoards.delete(tag.dataset.code);
      renderSelectedTags();
    }
  });
  btnResetBoards.addEventListener("click", () => {
    selectedBoards.clear();
    elBoardSearch.value = "";
    hideDropdown();
    renderSelectedTags();
  });
  document.addEventListener("click", (e) => {
    if (!elBoardPicker.contains(e.target)) hideDropdown();
  });

  (async function init() {
    try {
      await initTradeDateCalendar(elDate, "/api/v1/sentiment/trade-dates?limit=90");
      await loadBoardOptions();
      await queryHistory();
    } catch (err) {
      showError(err.message || String(err));
    }
  })();
})();
