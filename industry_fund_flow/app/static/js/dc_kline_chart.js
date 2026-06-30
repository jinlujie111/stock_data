/** K 线趋势图（ECharts candlestick + MA） */
(function () {
  function calcMA(dayCount, closes) {
    const result = [];
    for (let i = 0; i < closes.length; i++) {
      if (i < dayCount - 1) {
        result.push(null);
        continue;
      }
      let sum = 0;
      for (let j = 0; j < dayCount; j++) sum += Number(closes[i - j]);
      result.push(+(sum / dayCount).toFixed(2));
    }
    return result;
  }

  function fmtPrice(v) {
    if (v === null || v === undefined || v === "") return "—";
    return Number(v).toFixed(2);
  }

  function fmtPct(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    const pct = Math.abs(n) <= 1 && Math.abs(n) !== 0 ? n * 100 : n;
    return (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%";
  }

  function cellCls(v) {
    const n = Number(v);
    if (Number.isNaN(n) || v === null || v === "") return "";
    return n > 0 ? "cell-rise" : n < 0 ? "cell-fall" : "";
  }

  function renderSnapshotHeader(container, payload) {
    const snap = payload.snapshot || {};
    const last = (payload.bars && payload.bars[payload.bars.length - 1]) || {};
    const close = snap.close ?? last.close;
    const preClose = snap.pre_close ?? last.pre_close;
    const pct = snap.pct_change ?? snap.pct_chg ?? snap.fund_pct ?? last.pct_change ?? last.pct_chg;
    const open = snap.open ?? last.open;
    const high = snap.high ?? last.high;
    const low = snap.low ?? last.low;

    container.innerHTML = `
      <div class="kline-head">
        <div class="kline-title-row">
          <div>
            <h2 class="kline-title">${payload.name || payload.code}</h2>
            <span class="kline-code muted">${payload.display_code || payload.code}</span>
          </div>
          <div class="kline-price-block">
            <span class="kline-price ${cellCls(pct)}">${fmtPrice(close)}</span>
            <span class="kline-pct ${cellCls(pct)}">${fmtPct(pct)}</span>
          </div>
        </div>
        <div class="kline-metrics">
          <div class="kline-metric"><span>今开</span><strong class="${cellCls(open != null && preClose != null ? open - preClose : 0)}">${fmtPrice(open)}</strong></div>
          <div class="kline-metric"><span>昨收</span><strong>${fmtPrice(preClose)}</strong></div>
          <div class="kline-metric"><span>换手率</span><strong>${snap.turnover_rate != null ? Number(snap.turnover_rate).toFixed(2) + "%" : "—"}</strong></div>
          <div class="kline-metric"><span>最高</span><strong class="cell-rise">${fmtPrice(high)}</strong></div>
          <div class="kline-metric"><span>最低</span><strong class="cell-fall">${fmtPrice(low)}</strong></div>
          <div class="kline-metric"><span>市盈率 TTM</span><strong>${snap.pe_ttm != null ? Number(snap.pe_ttm).toFixed(2) : "—"}</strong></div>
          <div class="kline-metric"><span>成交量</span><strong>${snap.vol_wan_shou != null ? snap.vol_wan_shou + "万手" : "—"}</strong></div>
          <div class="kline-metric"><span>成交额</span><strong>${snap.amount_yi != null ? snap.amount_yi + "亿" : "—"}</strong></div>
          <div class="kline-metric"><span>总市值</span><strong>${snap.total_mv_yi != null ? snap.total_mv_yi + "亿" : "—"}</strong></div>
        </div>
      </div>`;
  }

  function renderKlineChart(chartEl, payload, existingChart) {
    const bars = payload.bars || [];
    if (!bars.length) {
      if (existingChart) existingChart.dispose();
      chartEl.innerHTML = '<div class="table-empty">暂无 K 线数据</div>';
      return null;
    }

    chartEl.innerHTML = "";
    chartEl.style.height = "420px";
    const chart = existingChart || echarts.init(chartEl);
    if (!existingChart) {
      chartEl._resizeBound = true;
      window.addEventListener("resize", () => chart && chart.resize());
    }

    const dates = bars.map((b) => b.trade_date);
    const ohlc = bars.map((b) => [
      Number(b.open),
      Number(b.close),
      Number(b.low),
      Number(b.high),
    ]);
    const closes = bars.map((b) => Number(b.close));
    const vols = bars.map((b) => Number(b.vol || 0));
    const ma5 = calcMA(5, closes);
    const ma10 = calcMA(10, closes);
    const ma20 = calcMA(20, closes);
    const ma60 = calcMA(60, closes);

    chart.setOption(
      {
        backgroundColor: "transparent",
        animation: false,
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "cross" },
          backgroundColor: "#1a2332",
          borderColor: "#2d3748",
          textStyle: { color: "#e2e8f0", fontSize: 12 },
        },
        legend: {
          data: ["K线", "MA5", "MA10", "MA20", "MA60"],
          top: 0,
          textStyle: { color: "#94a3b8", fontSize: 11 },
        },
        grid: [
          { left: 56, right: 16, top: 36, height: "58%" },
          { left: 56, right: 16, top: "72%", height: "16%" },
        ],
        xAxis: [
          {
            type: "category",
            data: dates,
            boundaryGap: true,
            axisLine: { lineStyle: { color: "#334155" } },
            axisLabel: { color: "#94a3b8", fontSize: 10 },
            min: "dataMin",
            max: "dataMax",
            gridIndex: 0,
          },
          {
            type: "category",
            data: dates,
            gridIndex: 1,
            axisLabel: { show: false },
            axisLine: { show: false },
            axisTick: { show: false },
          },
        ],
        yAxis: [
          {
            scale: true,
            gridIndex: 0,
            splitLine: { lineStyle: { color: "#1e293b" } },
            axisLabel: { color: "#94a3b8", fontSize: 10 },
          },
          {
            scale: true,
            gridIndex: 1,
            splitNumber: 2,
            axisLabel: { show: false },
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { show: false },
          },
        ],
        dataZoom: [
          { type: "inside", xAxisIndex: [0, 1], start: Math.max(0, 100 - (60 / bars.length) * 100) },
          { show: true, xAxisIndex: [0, 1], type: "slider", bottom: 4, height: 18, borderColor: "#334155", textStyle: { color: "#64748b" } },
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
          },
          { name: "MA5", type: "line", data: ma5, smooth: true, showSymbol: false, lineStyle: { width: 1, color: "#f59e0b" }, xAxisIndex: 0, yAxisIndex: 0 },
          { name: "MA10", type: "line", data: ma10, smooth: true, showSymbol: false, lineStyle: { width: 1, color: "#a855f7" }, xAxisIndex: 0, yAxisIndex: 0 },
          { name: "MA20", type: "line", data: ma20, smooth: true, showSymbol: false, lineStyle: { width: 1, color: "#3b82f6" }, xAxisIndex: 0, yAxisIndex: 0 },
          { name: "MA60", type: "line", data: ma60, smooth: true, showSymbol: false, lineStyle: { width: 1, color: "#64748b" }, xAxisIndex: 0, yAxisIndex: 0 },
          {
            name: "成交量",
            type: "bar",
            xAxisIndex: 1,
            yAxisIndex: 1,
            data: vols.map((v, i) => ({
              value: v,
              itemStyle: {
                color: ohlc[i][1] >= ohlc[i][0] ? "rgba(239,68,68,0.55)" : "rgba(34,197,94,0.55)",
              },
            })),
          },
        ],
      },
      true
    );
    return chart;
  }

  window.DcKline = {
    renderSnapshotHeader,
    renderKlineChart,
    cellCls,
    fmtPct,
  };
})();
