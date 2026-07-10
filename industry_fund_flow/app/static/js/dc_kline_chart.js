/** K 线趋势图（ECharts candlestick + MA + 支撑阻力叠加） */
(function () {
  const INDICATOR_COLORS = {
    ma: { support: "#f59e0b", resistance: "#f59e0b" },
    fibonacci: { support: "#22d3ee", resistance: "#22d3ee" },
    volume_price: { support: "#a855f7", resistance: "#a855f7" },
    trendline: { support: "#34d399", resistance: "#f87171" },
    chip: { support: "#fb923c", resistance: "#fb923c" },
  };

  const MA_COLORS = {
    MA5: "#f59e0b",
    MA10: "#a855f7",
    MA20: "#3b82f6",
    MA30: "#06b6d4",
    MA60: "#64748b",
  };

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
    return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
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

  function buildMarkLines(indicatorKey, levelData, dates) {
    const colors = INDICATOR_COLORS[indicatorKey] || { support: "#94a3b8", resistance: "#94a3b8" };
    const lines = [];
    (levelData.supports || []).forEach((lv) => {
      lines.push({
        name: lv.label,
        yAxis: lv.price,
        lineStyle: { color: colors.support, type: "dashed", width: 1.2 },
        label: {
          show: true,
          formatter: lv.label + " " + fmtPrice(lv.price),
          color: colors.support,
          fontSize: 10,
          position: "insideEndTop",
        },
      });
    });
    (levelData.resistances || []).forEach((lv) => {
      lines.push({
        name: lv.label,
        yAxis: lv.price,
        lineStyle: { color: colors.resistance, type: "dashed", width: 1.2 },
        label: {
          show: true,
          formatter: lv.label + " " + fmtPrice(lv.price),
          color: colors.resistance,
          fontSize: 10,
          position: "insideEndBottom",
        },
      });
    });
    return lines;
  }

  function buildTrendlineSeries(levelData, dates) {
    const out = [];
    (levelData.lines || []).forEach((line, idx) => {
      const pts = line.points || [];
      if (pts.length < 2) return;
      const data = pts.map((p) => [dates[p.index] || p.date, p.price]);
      const color = line.type === "support" ? "#34d399" : "#f87171";
      out.push({
        name: line.type === "support" ? "上升支撑线" : "下降阻力线",
        type: "line",
        data,
        showSymbol: true,
        symbolSize: 6,
        lineStyle: { color, width: 1.5 },
        itemStyle: { color },
        xAxisIndex: 0,
        yAxisIndex: 0,
        z: 3,
        _trendline: true,
        id: "trendline-" + idx,
      });
    });
    return out;
  }

  function buildMaSeries(levelData, dates) {
    const series = levelData.series || {};
    const out = [];
    Object.keys(series).forEach((key) => {
      const period = key.replace("ma", "");
      const label = "MA" + period;
      out.push({
        name: label,
        type: "line",
        data: series[key],
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1, color: MA_COLORS[label] || "#94a3b8" },
        xAxisIndex: 0,
        yAxisIndex: 0,
        _maLine: true,
      });
    });
    return out;
  }

  function renderLevelPanel(container, activeIndicators, levels) {
    if (!container) return;
    const blocks = [];
    activeIndicators.forEach((key) => {
      const data = levels[key];
      if (!data) return;
      const supports = data.supports || [];
      const resistances = data.resistances || [];
      if (key === "chip" && (data.profile || []).length) {
        const profile = data.profile.slice().sort((a, b) => a.price - b.price);
        const maxPct = Math.max(...profile.map((x) => x.pct), 1);
        const bars = profile
          .map(
            (p) =>
              `<div class="chip-bar-row"><span class="chip-bar-price">${fmtPrice(p.price)}</span><div class="chip-bar-track"><div class="chip-bar-fill" style="width:${(p.pct / maxPct) * 100}%"></div></div></div>`
          )
          .join("");
        blocks.push(`<div class="kline-level-block"><div class="kline-level-title">筹码分布轮廓${data.meta && data.meta.source === "cyq_chips" ? "(CYQ)" : ""}</div><div class="chip-profile">${bars}</div></div>`);
      }
      if (!supports.length && !resistances.length) return;
      const title = {
        ma: "均线",
        fibonacci: "斐波那契",
        volume_price: "量价关系",
        trendline: "趋势线",
        chip: "筹码分布",
      }[key] || key;
      blocks.push(`
        <div class="kline-level-block">
          <div class="kline-level-title">${title}</div>
          ${resistances
            .map(
              (lv) =>
                `<div class="kline-level-item kline-level-item--res"><span>${lv.label}</span><strong>${fmtPrice(lv.price)}</strong></div>`
            )
            .join("")}
          ${supports
            .map(
              (lv) =>
                `<div class="kline-level-item kline-level-item--sup"><span>${lv.label}</span><strong>${fmtPrice(lv.price)}</strong></div>`
            )
            .join("")}
        </div>`);
    });
    container.innerHTML = blocks.length
      ? blocks.join("")
      : '<div class="table-empty">请选择指标查看支撑/阻力位</div>';
  }

  function renderKlineChart(chartEl, payload, options) {
    const opts = options || {};
    const activeIndicators = opts.activeIndicators || [];
    const existingChart = opts.existingChart || null;

    const bars = payload.bars || [];
    if (!bars.length) {
      if (existingChart) existingChart.dispose();
      chartEl.innerHTML = '<div class="table-empty">暂无 K 线数据</div>';
      return null;
    }

    chartEl.innerHTML = "";
    chartEl.style.height = opts.height || "480px";
    const chart = existingChart || echarts.init(chartEl);
    if (!existingChart && !chartEl._resizeBound) {
      chartEl._resizeBound = true;
      window.addEventListener("resize", () => chart && chart.resize());
    }

    const dates = bars.map((b) => b.trade_date);
    const ohlc = bars.map((b) => [Number(b.open), Number(b.close), Number(b.low), Number(b.high)]);
    const closes = bars.map((b) => Number(b.close));
    const vols = bars.map((b) => Number(b.vol || 0));
    const levels = payload.levels || {};

    const legendItems = ["K线"];
    const series = [
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
        markLine: {
          symbol: "none",
          silent: true,
          data: [],
        },
      },
    ];

    const allMarkLines = [];
    activeIndicators.forEach((key) => {
      const levelData = levels[key];
      if (!levelData) return;
      if (key === "ma") {
        buildMaSeries(levelData, dates).forEach((s) => {
          legendItems.push(s.name);
          series.push(s);
        });
      }
      if (key === "trendline") {
        buildTrendlineSeries(levelData, dates).forEach((s) => {
          legendItems.push(s.name);
          series.push(s);
        });
      }
      if (key !== "trendline") {
        allMarkLines.push(...buildMarkLines(key, levelData, dates));
      } else {
        allMarkLines.push(...buildMarkLines(key, levelData, dates));
      }
    });

    if (allMarkLines.length) {
      series[0].markLine.data = allMarkLines;
      series[0].markLine.label = { show: true };
    }

    series.push({
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
    });

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
          data: legendItems,
          top: 0,
          textStyle: { color: "#94a3b8", fontSize: 11 },
        },
        grid: [
          { left: 56, right: 24, top: 36, height: "58%" },
          { left: 56, right: 24, top: "72%", height: "16%" },
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
          {
            show: true,
            xAxisIndex: [0, 1],
            type: "slider",
            bottom: 4,
            height: 18,
            borderColor: "#334155",
            textStyle: { color: "#64748b" },
          },
        ],
        series,
      },
      true
    );
    return chart;
  }

  window.DcKline = {
    renderSnapshotHeader,
    renderKlineChart,
    renderLevelPanel,
    cellCls,
    fmtPct,
    INDICATOR_COLORS,
  };
})();
