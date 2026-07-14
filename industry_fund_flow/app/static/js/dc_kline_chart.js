/** K 线趋势图（ECharts candlestick + MA + 支撑阻力叠加） */
(function () {
  const SUPPORT_COLOR = "#22c55e";
  const RESISTANCE_COLOR = "#ef4444";

  const INDICATOR_COLORS = {
    ma: { support: SUPPORT_COLOR, resistance: RESISTANCE_COLOR },
    fibonacci: { support: SUPPORT_COLOR, resistance: RESISTANCE_COLOR },
    volume_price: { support: SUPPORT_COLOR, resistance: RESISTANCE_COLOR },
    trendline: { support: SUPPORT_COLOR, resistance: RESISTANCE_COLOR },
  };

  const INDICATOR_LABELS = {
    ma: "均线",
    fibonacci: "斐波那契",
    volume_price: "量价关系",
    trendline: "趋势线",
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

  function fmtVol(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return "—";
    if (n >= 1e8) return (n / 1e8).toFixed(2) + "亿";
    if (n >= 1e4) return (n / 1e4).toFixed(2) + "万";
    return n.toFixed(0);
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

  function buildMarkLines(indicatorKey, levelData) {
    const colors = INDICATOR_COLORS[indicatorKey] || {
      support: SUPPORT_COLOR,
      resistance: RESISTANCE_COLOR,
    };
    const lines = [];
    const labelBase = {
      show: true,
      position: "end",
      fontSize: 10,
      padding: [2, 6, 2, 4],
      backgroundColor: "rgba(15, 20, 25, 0.85)",
      borderRadius: 3,
    };
    (levelData.supports || []).forEach((lv) => {
      lines.push({
        name: lv.label,
        yAxis: lv.price,
        lineStyle: { color: colors.support, type: "dashed", width: 1.4 },
        label: {
          ...labelBase,
          formatter: fmtPrice(lv.price),
          color: colors.support,
        },
      });
    });
    (levelData.resistances || []).forEach((lv) => {
      lines.push({
        name: lv.label,
        yAxis: lv.price,
        lineStyle: { color: colors.resistance, type: "dashed", width: 1.4 },
        label: {
          ...labelBase,
          formatter: fmtPrice(lv.price),
          color: colors.resistance,
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
      const lineName =
        line.label || (line.type === "support" ? "上升支撑线" : "下降阻力线");
      out.push({
        name: lineName,
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
    const allResistances = [];
    const allSupports = [];

    activeIndicators.forEach((key) => {
      const data = levels[key];
      if (!data) return;
      (data.resistances || []).forEach((lv) => {
        allResistances.push({ ...lv, indicator: key });
      });
      (data.supports || []).forEach((lv) => {
        allSupports.push({ ...lv, indicator: key });
      });
    });

    allResistances.sort((a, b) => b.price - a.price);
    allSupports.sort((a, b) => b.price - a.price);

    const blocks = [];

    if (allResistances.length) {
      blocks.push(`
        <div class="kline-level-block kline-level-block--res">
          <div class="kline-level-title kline-level-title--res">阻力位 <span class="kline-level-legend">红色虚线</span></div>
          ${allResistances
            .map(
              (lv) => `
            <div class="kline-level-item kline-level-item--res">
              <span class="kline-level-tag">${INDICATOR_LABELS[lv.indicator] || lv.indicator}</span>
              <span class="kline-level-name">${lv.label}</span>
              <strong>${fmtPrice(lv.price)}</strong>
            </div>`
            )
            .join("")}
        </div>`);
    }

    if (allSupports.length) {
      blocks.push(`
        <div class="kline-level-block kline-level-block--sup">
          <div class="kline-level-title kline-level-title--sup">支撑位 <span class="kline-level-legend">绿色虚线</span></div>
          ${allSupports
            .map(
              (lv) => `
            <div class="kline-level-item kline-level-item--sup">
              <span class="kline-level-tag">${INDICATOR_LABELS[lv.indicator] || lv.indicator}</span>
              <span class="kline-level-name">${lv.label}</span>
              <strong>${fmtPrice(lv.price)}</strong>
            </div>`
            )
            .join("")}
        </div>`);
    }

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
      if (existingChart && !existingChart.isDisposed()) existingChart.dispose();
      chartEl.innerHTML = '<div class="table-empty">暂无 K 线数据</div>';
      return null;
    }

    let chart = existingChart;
    if (chart && chart.isDisposed()) chart = null;
    if (!chart) {
      chartEl.innerHTML = "";
      chartEl.style.height = opts.height || "480px";
      chart = echarts.init(chartEl);
      if (!chartEl._resizeBound) {
        chartEl._resizeBound = true;
        window.addEventListener("resize", () => chart && !chart.isDisposed() && chart.resize());
      }
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
        allMarkLines.push(...buildMarkLines(key, levelData));
        return;
      }
      allMarkLines.push(...buildMarkLines(key, levelData));
    });

    const hasLevelLines = allMarkLines.length > 0;
    const gridRight = hasLevelLines ? 72 : 24;

    if (allMarkLines.length) {
      series[0].markLine.data = allMarkLines;
      series[0].markLine.label = { show: true };
    } else {
      series[0].markLine.data = [];
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
          { left: 56, right: gridRight, top: 36, height: "58%" },
          { left: 56, right: gridRight, top: "72%", height: "16%" },
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

  const VP_STATUS_LABEL = {
    mainline_burst: "主线爆发",
    trend_up: "趋势上升",
    range_bound: "震荡",
    weak: "弱势",
    ebbing: "退潮",
  };

  const VP_SIGNAL_LABEL = {
    main_rise: "主升",
    ebbing: "退潮",
    none: "无",
    launch: "启动",
    distribution: "派发",
  };

  function vpLabelStatus(v) {
    if (!v) return "—";
    return VP_STATUS_LABEL[v] || v;
  }

  function vpLabelSignal(v) {
    if (!v || v === "none") return "—";
    return VP_SIGNAL_LABEL[v] || v;
  }

  function vpPct(v) {
    if (v === null || v === undefined || v === "") return "—";
    return (Number(v) * 100).toFixed(1) + "%";
  }

  /** 板块量价页：K 线 + 成交量 + VP 指标叠加 */
  function renderVpKlineChart(chartEl, payload, options) {
    const opts = options || {};
    const bars = payload.bars || [];
    const vpSeries = payload.vp_series || [];
    const existingChart = opts.existingChart || null;

    if (typeof echarts === "undefined") {
      chartEl.innerHTML = '<div class="table-empty kline-error">ECharts 未加载</div>';
      return null;
    }

    if (!bars.length) {
      if (existingChart && !existingChart.isDisposed()) existingChart.dispose();
      chartEl.innerHTML = '<div class="table-empty">暂无 K 线数据</div>';
      return null;
    }

    let chart = existingChart;
    if (chart && chart.isDisposed()) chart = null;
    if (!chart) {
      chartEl.innerHTML = "";
      chartEl._vpPointerBound = false;
      chartEl.style.height = opts.height || "560px";
      chart = echarts.init(chartEl);
      if (!chartEl._vpResizeBound) {
        chartEl._vpResizeBound = true;
        window.addEventListener("resize", () => chart && !chart.isDisposed() && chart.resize());
      }
    }

    const dates = bars.map((b) => b.trade_date);
    const ohlc = bars.map((b) => [Number(b.open), Number(b.close), Number(b.low), Number(b.high)]);
    const vols = bars.map((b) => Number(b.vol || 0));
    const vpScores = vpSeries.map((v) =>
      v && v.vp_score != null && v.vp_score !== "" ? Number(v.vp_score) : null
    );
    const risingPcts = vpSeries.map((v) =>
      v && v.rising_ratio != null ? +(Number(v.rising_ratio) * 100).toFixed(2) : null
    );
    const breakoutPcts = vpSeries.map((v) =>
      v && v.breakout_ratio != null ? +(Number(v.breakout_ratio) * 100).toFixed(2) : null
    );
    const streakDays = vpSeries.map((v) =>
      v && v.amount_streak_days != null ? Number(v.amount_streak_days) : null
    );
    const trendRet20 = vpSeries.map((v) =>
      v && v.trend_return_20d != null ? Number(v.trend_return_20d) : null
    );

    const markPoints = [];
    vpSeries.forEach((v, i) => {
      if (!v || !v.signal_type || v.signal_type === "none") return;
      const high = ohlc[i] ? ohlc[i][3] : null;
      if (high == null) return;
      markPoints.push({
        name: vpLabelSignal(v.signal_type),
        coord: [dates[i], high],
        value: vpLabelSignal(v.signal_type),
        symbol: "pin",
        symbolSize: 36,
        itemStyle: { color: v.signal_type === "launch" || v.signal_type === "main_rise" ? "#f59e0b" : "#94a3b8" },
        label: { show: true, formatter: vpLabelSignal(v.signal_type), fontSize: 9, color: "#fff" },
      });
    });

    function resolveDataIndex(params, axisValue) {
      if (axisValue != null && axisValue !== "") {
        const idx = dates.indexOf(String(axisValue));
        if (idx >= 0) return idx;
      }
      if (params && params.length) {
        for (const p of params) {
          if (p.dataIndex != null && p.dataIndex >= 0) return p.dataIndex;
        }
      }
      return -1;
    }

    function buildVpTooltipHtml(idx) {
      if (idx < 0 || idx >= dates.length) return "";
      const bar = bars[idx] || {};
      const vp = vpSeries[idx] || {};
      const pctChg = bar.pct_change != null ? fmtPct(bar.pct_change) : "—";
      return [
        `<strong>${dates[idx]}</strong>`,
        `收 ${fmtPrice(bar.close)} (${pctChg})`,
        `成交量 ${fmtVol(bar.vol != null ? bar.vol : vols[idx])}`,
        `VP分 <strong>${vp.vp_score != null ? Number(vp.vp_score).toFixed(1) : "—"}</strong>`,
        `状态 ${vpLabelStatus(vp.vp_status)} · 信号 ${vpLabelSignal(vp.signal_type)}`,
        `上涨占比 ${vpPct(vp.rising_ratio)} · 突破占比 ${vpPct(vp.breakout_ratio)}`,
        `连续强度 ${vp.continuity_strength != null ? Number(vp.continuity_strength).toFixed(2) : "—"} · 连续 ${vp.amount_streak_days != null ? vp.amount_streak_days + "天" : "—"}`,
        vp.trend_return_20d != null ? `20日趋势 ${Number(vp.trend_return_20d).toFixed(2)}%` : "",
        vp.leader_strength != null ? `龙头强度 ${Number(vp.leader_strength).toFixed(2)}` : "",
        vp.industry_vol_ratio_20 != null ? `行业量比 ${Number(vp.industry_vol_ratio_20).toFixed(2)}` : "",
      ]
        .filter(Boolean)
        .join("<br/>");
    }

    function vpSubChartHints(idx) {
      if (idx < 0 || idx >= dates.length) return [];
      const vp = vpSeries[idx] || {};
      const volText = `成交量 ${fmtVol(vols[idx])}`;
      const vpText = `VP分 ${vp.vp_score != null ? Number(vp.vp_score).toFixed(1) : "—"}`;
      return [
        {
          type: "text",
          id: "vp-vol-hint",
          left: 58,
          top: "57%",
          z: 100,
          style: { text: volText, fill: "#e2e8f0", fontSize: 11 },
        },
        {
          type: "text",
          id: "vp-score-hint",
          left: 58,
          top: "73%",
          z: 100,
          style: { text: vpText, fill: "#3b82f6", fontSize: 12, fontWeight: "bold" },
        },
      ];
    }

    function bindVpCrosshairSync(chart, chartEl, ctx) {
      if (chartEl._vpPointerBound) return;
      chartEl._vpPointerBound = true;
      const { dates: dts } = ctx;
      let lastIdx = -1;

      function clearHints() {
        lastIdx = -1;
        chart.setOption({ graphic: [] });
      }

      function syncPointer(idx) {
        if (idx < 0 || idx >= dts.length) {
          clearHints();
          return;
        }
        if (idx === lastIdx) return;
        lastIdx = idx;
        chart.setOption({ graphic: vpSubChartHints(idx) });
        chart.dispatchAction({ type: "showTip", seriesIndex: 0, dataIndex: idx });
      }

      chart.on("updateAxisPointer", (event) => {
        const xInfo = (event.axesInfo || []).find((a) => a.axisDim === "x");
        if (!xInfo || xInfo.value == null) {
          clearHints();
          return;
        }
        syncPointer(Number(xInfo.value));
      });

      chart.on("globalout", () => {
        clearHints();
      });
    }

    chart.setOption(
      {
        backgroundColor: "transparent",
        animation: false,
        axisPointer: {
          link: [{ xAxisIndex: [0, 1, 2] }],
          label: {
            show: true,
            backgroundColor: "#334155",
            color: "#e2e8f0",
            fontSize: 10,
          },
          lineStyle: {
            color: "#64748b",
            width: 1,
            type: "dashed",
          },
          crossStyle: {
            color: "#64748b",
            width: 1,
            type: "dashed",
          },
        },
        tooltip: {
          trigger: "axis",
          axisPointer: {
            type: "cross",
            animation: false,
          },
          backgroundColor: "#1a2332",
          borderColor: "#2d3748",
          textStyle: { color: "#e2e8f0", fontSize: 12 },
          position(point, _params, _dom, _rect, size) {
            const x = Math.min(Math.max(point[0], 80), size.viewSize[0] - 160);
            return [x, 36];
          },
          formatter(params) {
            if (!params || !params.length) return "";
            const idx = resolveDataIndex(params, params[0].axisValue);
            return buildVpTooltipHtml(idx);
          },
        },
        legend: {
          data: ["K线", "VP分", "上涨占比", "突破占比", "连续放量天数", "20日趋势"],
          top: 0,
          textStyle: { color: "#94a3b8", fontSize: 11 },
          inactiveColor: "#64748b",
        },
        stateAnimation: { duration: 0 },
        grid: [
          { left: 56, right: 48, top: 32, height: "42%" },
          { left: 56, right: 48, top: "56%", height: "12%" },
          { left: 56, right: 48, top: "72%", height: "18%" },
        ],
        xAxis: [
          {
            type: "category",
            data: dates,
            boundaryGap: true,
            axisLine: { lineStyle: { color: "#334155" } },
            axisLabel: { color: "#94a3b8", fontSize: 10 },
            axisPointer: { show: true, snap: true },
            gridIndex: 0,
          },
          {
            type: "category",
            data: dates,
            gridIndex: 1,
            axisLabel: { show: false },
            axisLine: { show: false },
            axisTick: { show: false },
            axisPointer: { show: true, snap: true },
          },
          {
            type: "category",
            data: dates,
            gridIndex: 2,
            axisLabel: { color: "#94a3b8", fontSize: 10 },
            axisLine: { lineStyle: { color: "#334155" } },
            axisPointer: { show: true, snap: true },
          },
        ],
        yAxis: [
          {
            scale: true,
            gridIndex: 0,
            splitLine: { lineStyle: { color: "#1e293b" } },
            axisLabel: { color: "#94a3b8", fontSize: 10 },
            axisPointer: { show: true, snap: false },
          },
          {
            scale: true,
            gridIndex: 1,
            splitNumber: 2,
            axisLabel: { show: false },
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { show: false },
            axisPointer: {
              show: true,
              snap: true,
              label: {
                show: true,
                backgroundColor: "#334155",
                color: "#e2e8f0",
                fontSize: 10,
                formatter: (p) => fmtVol(p.value),
              },
            },
          },
          {
            min: 0,
            max: 100,
            gridIndex: 2,
            position: "left",
            splitLine: { lineStyle: { color: "#1e293b" } },
            axisLabel: { color: "#94a3b8", fontSize: 10, formatter: "{value}" },
            axisPointer: {
              show: true,
              snap: true,
              label: {
                show: true,
                backgroundColor: "#334155",
                color: "#3b82f6",
                fontSize: 10,
                formatter: (p) => (p.value != null ? Number(p.value).toFixed(1) : ""),
              },
            },
          },
          {
            min: 0,
            gridIndex: 2,
            position: "right",
            splitLine: { show: false },
            axisLabel: { color: "#a855f7", fontSize: 10 },
            axisPointer: { show: true, snap: false, label: { show: false } },
          },
        ],
        dataZoom: [
          { type: "inside", xAxisIndex: [0, 1, 2], start: 0, end: 100 },
          {
            show: true,
            xAxisIndex: [0, 1, 2],
            type: "slider",
            bottom: 4,
            height: 18,
            borderColor: "#334155",
            textStyle: { color: "#64748b" },
          },
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
            markPoint: markPoints.length ? { data: markPoints, symbolKeepAspect: true } : undefined,
            emphasis: { focus: "none", scale: false },
            blur: { itemStyle: { opacity: 1 } },
          },
          {
            name: "成交量",
            type: "bar",
            xAxisIndex: 1,
            yAxisIndex: 1,
            data: vols.map((v, i) => ({
              value: v,
              itemStyle: {
                color: ohlc[i][1] >= ohlc[i][0] ? "rgba(239,68,68,0.85)" : "rgba(34,197,94,0.85)",
              },
            })),
            emphasis: { focus: "none", scale: false },
          },
          {
            name: "VP分",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: vpScores,
            smooth: true,
            showSymbol: false,
            lineStyle: { width: 2, color: "#3b82f6" },
            itemStyle: { color: "#3b82f6" },
            emphasis: { focus: "none", scale: false },
          },
          {
            name: "上涨占比",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: risingPcts,
            smooth: true,
            showSymbol: false,
            lineStyle: { width: 1.2, color: "#22c55e", type: "dashed" },
            emphasis: { focus: "none", scale: false },
          },
          {
            name: "突破占比",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 2,
            data: breakoutPcts,
            smooth: true,
            showSymbol: false,
            lineStyle: { width: 1.2, color: "#f59e0b", type: "dashed" },
            emphasis: { focus: "none", scale: false },
          },
          {
            name: "连续放量天数",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 3,
            data: streakDays,
            smooth: false,
            showSymbol: true,
            symbolSize: 4,
            lineStyle: { width: 1.5, color: "#a855f7" },
            itemStyle: { color: "#a855f7" },
            emphasis: { focus: "none", scale: false },
          },
          {
            name: "20日趋势",
            type: "line",
            xAxisIndex: 2,
            yAxisIndex: 3,
            data: trendRet20,
            smooth: true,
            showSymbol: false,
            lineStyle: { width: 1.2, color: "#06b6d4", type: "dotted" },
            itemStyle: { color: "#06b6d4" },
            emphasis: { focus: "none", scale: false },
          },
        ],
      },
      true
    );
    bindVpCrosshairSync(chart, chartEl, { dates });
    return chart;
  }

  window.DcKline = {
    renderSnapshotHeader,
    renderKlineChart,
    renderVpKlineChart,
    renderLevelPanel,
    cellCls,
    fmtPct,
    vpLabelStatus,
    vpLabelSignal,
    INDICATOR_LABELS,
  };
})();
