(function () {
  const board = window.DcBoard || {};
  const { normalizeIsoDate, toApiTradeDate } = board;

  const elDate = document.getElementById("trade-date");
  const elTypes = document.getElementById("content-types");
  const elSigFilter = document.getElementById("signal-filter");
  const elSearch = document.getElementById("board-search");
  const btnQuery = document.getElementById("btn-query");
  const elError = document.getElementById("page-error");
  const elSigBody = document.getElementById("signal-body");
  const elSigEmpty = document.getElementById("signal-empty");
  const elRankBody = document.getElementById("rank-body");
  const elRankEmpty = document.getElementById("rank-empty");
  const elDetailCard = document.getElementById("detail-card");
  const elDetailTitle = document.getElementById("detail-title");
  const elDetailMetrics = document.getElementById("detail-metrics");
  const elHistBody = document.getElementById("hist-signal-body");
  const elChart = document.getElementById("timing-kline-chart");
  const elPresets = document.getElementById("kline-range-presets");
  const btnKline = document.getElementById("btn-kline-refresh");

  let chartInst = null;
  let currentCode = "";
  let klineDays = 60;

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

  async function fetchJson(url) {
    const res = await fetch(url, { credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText || "请求失败");
    return data;
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
    return "—";
  }

  function labelState(s) {
    if (s === "long") return "持有";
    if (s === "watch") return "观望";
    if (s === "flat") return "空仓";
    return s || "—";
  }

  function signalClass(s) {
    if (s === "buy") return "tone-up";
    if (s === "sell") return "tone-down";
    return "";
  }

  async function loadDates() {
    const data = await fetchJson("/api/v1/timing/trade-dates?limit=120");
    const dates = data.dates || [];
    elDate.innerHTML = dates
      .map((d) => {
        const iso = normalizeIsoDate ? normalizeIsoDate(d) : d;
        const api = toApiTradeDate ? toApiTradeDate(iso) : String(d).replace(/-/g, "");
        return `<option value="${api}">${iso}</option>`;
      })
      .join("");
    if (!dates.length) showError("暂无择时数据，请先运行 run_board_timing_batch");
  }

  function selectedDate() {
    return elDate.value || "";
  }

  async function loadSignals() {
    const td = selectedDate();
    if (!td) return;
    const sig = elSigFilter.value;
    const types = encodeURIComponent(elTypes.value);
    let url = `/api/v1/timing/signals?trade_date=${td}&content_types=${types}&top=100`;
    if (sig) url += `&signal_type=${sig}`;
    const data = await fetchJson(url);
    const items = data.items || [];
    elSigBody.innerHTML = items
      .map((r) => {
        return (
          `<tr data-code="${r.industry_code}" class="clickable-row">` +
          `<td class="${signalClass(r.signal_type)}"><strong>${labelSignal(r.signal_type)}</strong></td>` +
          `<td>${r.industry_name || r.industry_code}</td>` +
          `<td>${r.content_type || "—"}</td>` +
          `<td>${fmt(r.score)}</td>` +
          `<td>${fmt(r.score_trend)}</td>` +
          `<td>${fmt(r.score_fund)}</td>` +
          `<td>${fmt(r.score_vp)}</td>` +
          `<td>${fmt(r.score_sentiment)}</td>` +
          `<td class="muted">${r.signal_reason || "—"}</td>` +
          `</tr>`
        );
      })
      .join("");
    elSigEmpty.classList.toggle("hidden", items.length > 0);
    elSigBody.querySelectorAll("tr[data-code]").forEach((tr) => {
      tr.addEventListener("click", () => openDetail(tr.getAttribute("data-code")));
    });
  }

  async function loadRank() {
    const td = selectedDate();
    if (!td) return;
    const types = encodeURIComponent(elTypes.value);
    const kw = (elSearch.value || "").trim();
    let url = `/api/v1/timing/rank?trade_date=${td}&content_types=${types}&top=50&sort=score`;
    const data = await fetchJson(url);
    let items = data.items || [];
    if (kw) {
      const k = kw.toLowerCase();
      items = items.filter(
        (r) =>
          String(r.industry_name || "").toLowerCase().includes(k) ||
          String(r.industry_code || "").toLowerCase().includes(k)
      );
    }
    elRankBody.innerHTML = items
      .map((r, i) => {
        return (
          `<tr data-code="${r.industry_code}" class="clickable-row">` +
          `<td>${r.rank_score != null ? r.rank_score : i + 1}</td>` +
          `<td>${r.industry_name || r.industry_code}</td>` +
          `<td>${r.content_type || "—"}</td>` +
          `<td><strong>${fmt(r.score)}</strong></td>` +
          `<td>${labelState(r.position_state)}</td>` +
          `<td>${fmt(r.score_trend)}</td>` +
          `<td>${fmt(r.score_fund)}</td>` +
          `<td>${fmt(r.score_vp)}</td>` +
          `<td>${fmt(r.score_sentiment)}</td>` +
          `</tr>`
        );
      })
      .join("");
    elRankEmpty.classList.toggle("hidden", items.length > 0);
    elRankBody.querySelectorAll("tr[data-code]").forEach((tr) => {
      tr.addEventListener("click", () => openDetail(tr.getAttribute("data-code")));
    });
  }

  async function openDetail(code) {
    if (!code) return;
    currentCode = code;
    const td = selectedDate();
    const detail = await fetchJson(
      `/api/v1/timing/boards/${encodeURIComponent(code)}?trade_date=${td}`
    );
    const item = detail.item || {};
    elDetailCard.classList.remove("hidden");
    elDetailTitle.textContent = `${item.industry_name || code} · ${item.industry_code || code}`;
    elDetailMetrics.innerHTML = [
      ["综合分", fmt(item.score)],
      ["趋势", fmt(item.score_trend)],
      ["资金", fmt(item.score_fund)],
      ["量价", fmt(item.score_vp)],
      ["情绪", fmt(item.score_sentiment)],
      ["状态", labelState(item.position_state)],
      ["信号", labelSignal(item.signal_type)],
      ["过热", item.sentiment_overheat ? "是" : "否"],
    ]
      .map(
        ([k, v]) =>
          `<div class="vp-metric"><span class="vp-metric-label">${k}</span><span class="vp-metric-val">${v}</span></div>`
      )
      .join("");
    await loadKline();
    elDetailCard.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderChart(payload) {
    if (!window.echarts || !elChart) return;
    if (!chartInst) chartInst = echarts.init(elChart);
    const bars = payload.bars || [];
    const timing = payload.timing || [];
    const dates = bars.map((b) => b.trade_date);
    const ohlc = bars.map((b) => [b.open, b.close, b.low, b.high]);
    const scores = timing.map((t) => (t && t.score != null ? Number(t.score) : null));
    const flows = timing.map((t) => (t && t.flow5 != null ? Number(t.flow5) / 1e8 : null));
    const markPoints = [];
    timing.forEach((t, i) => {
      if (!t || (t.signal_type !== "buy" && t.signal_type !== "sell")) return;
      const high = ohlc[i] ? ohlc[i][3] : null;
      const low = ohlc[i] ? ohlc[i][2] : null;
      const isBuy = t.signal_type === "buy";
      markPoints.push({
        name: isBuy ? "买" : "卖",
        coord: [dates[i], isBuy ? low : high],
        value: isBuy ? "买" : "卖",
        symbol: "triangle",
        symbolRotate: isBuy ? 0 : 180,
        symbolSize: 14,
        itemStyle: { color: isBuy ? "#16a34a" : "#dc2626" },
        label: { show: true, formatter: isBuy ? "买" : "卖", fontSize: 10, color: "#fff" },
      });
    });

    chartInst.setOption(
      {
        animation: false,
        legend: { data: ["K线", "Score", "flow5(亿)"], top: 0, textStyle: { color: "#94a3b8" } },
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
              `收 ${fmt(b.close, 2)} (${fmt(b.pct_change, 2)}%)`,
              `Score ${fmt(t.score)} · ${labelSignal(t.signal_type)} · ${labelState(t.position_state)}`,
              `趋势 ${fmt(t.score_trend)} / 资金 ${fmt(t.score_fund)} / 量价 ${fmt(t.score_vp)} / 情绪 ${fmt(t.score_sentiment)}`,
              t.signal_reason ? `原因 ${t.signal_reason}` : "",
            ]
              .filter(Boolean)
              .join("<br/>");
          },
        },
        axisPointer: { link: [{ xAxisIndex: "all" }] },
        grid: [
          { left: 56, right: 24, top: 36, height: "48%" },
          { left: 56, right: 24, top: "62%", height: "14%" },
          { left: 56, right: 24, top: "80%", height: "14%" },
        ],
        xAxis: [
          { type: "category", data: dates, gridIndex: 0, axisLabel: { show: false } },
          { type: "category", data: dates, gridIndex: 1, axisLabel: { show: false } },
          { type: "category", data: dates, gridIndex: 2 },
        ],
        yAxis: [
          { scale: true, gridIndex: 0, splitLine: { lineStyle: { color: "#1e293b" } } },
          { scale: true, gridIndex: 1, splitLine: { show: false } },
          { scale: true, gridIndex: 2, splitLine: { show: false } },
        ],
        dataZoom: [
          { type: "inside", xAxisIndex: [0, 1, 2] },
          { type: "slider", xAxisIndex: [0, 1, 2], bottom: 4, height: 18 },
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
            name: "Score",
            type: "line",
            data: scores,
            xAxisIndex: 1,
            yAxisIndex: 1,
            showSymbol: false,
            lineStyle: { width: 2, color: "#38bdf8" },
            markLine: {
              symbol: "none",
              data: [
                { yAxis: 70, lineStyle: { color: "#16a34a", type: "dashed" } },
                { yAxis: 40, lineStyle: { color: "#dc2626", type: "dashed" } },
              ],
            },
          },
          {
            name: "flow5(亿)",
            type: "bar",
            data: flows,
            xAxisIndex: 2,
            yAxisIndex: 2,
            itemStyle: {
              color: (p) => (p.value >= 0 ? "#16a34a" : "#dc2626"),
            },
          },
        ],
      },
      true
    );

    elHistBody.innerHTML = (payload.signals || [])
      .slice()
      .reverse()
      .map((s) => {
        return (
          `<tr>` +
          `<td>${s.trade_date || "—"}</td>` +
          `<td class="${signalClass(s.signal_type)}">${labelSignal(s.signal_type)}</td>` +
          `<td>${fmt(s.score)}</td>` +
          `<td class="muted">${s.signal_reason || "—"}</td>` +
          `</tr>`
        );
      })
      .join("");
  }

  async function loadKline() {
    if (!currentCode) return;
    const td = selectedDate();
    const url = `/api/v1/timing/boards/${encodeURIComponent(currentCode)}/kline?trade_date=${td}&days=${klineDays}`;
    const data = await fetchJson(url);
    renderChart(data);
  }

  async function refreshAll() {
    showError("");
    try {
      await loadSignals();
      await loadRank();
    } catch (e) {
      showError(e.message || String(e));
    }
  }

  btnQuery.addEventListener("click", refreshAll);
  elDate.addEventListener("change", refreshAll);
  elTypes.addEventListener("change", refreshAll);
  elSigFilter.addEventListener("change", refreshAll);
  elSearch.addEventListener("keydown", (e) => {
    if (e.key === "Enter") refreshAll();
  });
  btnKline.addEventListener("click", () => loadKline().catch((e) => showError(e.message)));
  if (elPresets) {
    elPresets.querySelectorAll(".chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        elPresets.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
        btn.classList.add("active");
        klineDays = Number(btn.getAttribute("data-days") || 60);
        loadKline().catch((e) => showError(e.message));
      });
    });
  }
  window.addEventListener("resize", () => chartInst && chartInst.resize());

  loadDates()
    .then(refreshAll)
    .catch((e) => showError(e.message || String(e)));
})();
