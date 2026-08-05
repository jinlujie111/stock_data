(function () {
  const board = window.DcBoard || {};
  const kline = window.DcKline || {};
  const { normalizeIsoDate, toApiTradeDate } = board;

  const elDate = document.getElementById("trade-date");
  const elTypes = document.getElementById("content-types");
  const elSigFilter = document.getElementById("signal-filter");
  const elSort = document.getElementById("sort-key");
  const elSearch = document.getElementById("board-search");
  const btnQuery = document.getElementById("btn-query");
  const elError = document.getElementById("page-error");
  const elBtSummary = document.getElementById("bt-summary");
  const elBtRunCode = document.getElementById("bt-run-code");
  const elBtCost = document.getElementById("bt-cost-bps");
  const elBtLookback = document.getElementById("bt-lookback");
  const elBtBuy = document.getElementById("bt-buy-score");
  const elBtSell = document.getElementById("bt-sell-score");
  const elBtStop = document.getElementById("bt-stop-loss");
  const elBtParamsView = document.getElementById("bt-params-view");
  const btnBtRun = document.getElementById("btn-bt-run");
  const elSigBody = document.getElementById("signal-body");
  const elSigEmpty = document.getElementById("signal-empty");
  const elRankBody = document.getElementById("rank-body");
  const elRankEmpty = document.getElementById("rank-empty");
  const elDetailCard = document.getElementById("detail-card");
  const elDetailTitle = document.getElementById("detail-title");
  const elDetailMetrics = document.getElementById("detail-metrics");
  const elHistBody = document.getElementById("hist-signal-body");
  const elBtTradeBody = document.getElementById("bt-trade-body");
  const elChart = document.getElementById("timing-kline-chart");
  const elEquity = document.getElementById("timing-equity-chart");
  const elPresets = document.getElementById("kline-range-presets");
  const elVolChips = document.getElementById("vol-mode-chips");
  const btnKline = document.getElementById("btn-kline-refresh");

  let chartInst = null;
  let equityInst = null;
  let currentCode = "";
  let klineDays = 60;
  let volMode = "vol";
  let lastPayload = null;
  let activeRunCode = "daily_default";

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

  function fmtPct(n, d) {
    if (n == null || n === "") return "—";
    const x = Number(n);
    if (Number.isNaN(x)) return "—";
    return `${(x * 100).toFixed(d == null ? 1 : d)}%`;
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

  function tonePct(n) {
    if (n == null || Number.isNaN(Number(n))) return "";
    return Number(n) >= 0 ? "tone-up" : "tone-down";
  }

  function metric(label, val, strong) {
    return `<div class="vp-metric"><span class="vp-metric-label">${label}</span><span class="vp-metric-val${strong ? " strong" : ""}">${val}</span></div>`;
  }

  async function loadDates() {
    const data = await fetchJson("/api/v1/timing/trade-dates?limit=240");
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

  async function loadBtSummary() {
    if (!elBtSummary) return;
    try {
      const data = await fetchJson(
        `/api/v1/timing/backtest/summary?run_code=${encodeURIComponent(activeRunCode)}`
      );
      const run = data.run;
      if (!run) {
        elBtSummary.innerHTML = metric("回测", "未跑 · 请执行回测或点「按参数回测」");
        return;
      }
      const unstable =
        run.trade_count != null && Number(run.trade_count) < 10
          ? metric("样本", "交易偏少，统计不稳")
          : "";
      elBtSummary.innerHTML = [
        metric("成交模型", data.exec_model || "t1_open", true),
        metric("Run", run.run_code || activeRunCode),
        metric("回测区间", `${run.start_date} ~ ${run.end_date}`),
        metric("成功率", fmtPct(run.win_rate)),
        metric("平均收益", fmtPct(run.avg_return)),
        metric("等权收益", fmtPct(run.total_return), true),
        metric("买入持有", fmtPct(run.bench_return)),
        metric("最大回撤", fmtPct(run.max_drawdown)),
        metric("夏普", fmt(run.sharpe, 2)),
        metric("Calmar", fmt(run.calmar, 2)),
        metric("盈亏比", fmt(run.profit_factor, 2)),
        metric("最大连亏", run.max_loss_streak != null ? String(run.max_loss_streak) : "—"),
        metric("交易笔数", run.trade_count != null ? String(run.trade_count) : "—"),
        metric("板块数", run.board_count != null ? String(run.board_count) : "—"),
        unstable,
      ]
        .filter(Boolean)
        .join("");
    } catch (e) {
      elBtSummary.innerHTML = metric("回测", e.message || "加载失败");
    }
  }

  function fillParamInputs(params) {
    if (!params) return;
    if (elBtCost && params.cost_bps != null) elBtCost.value = params.cost_bps;
    if (elBtLookback && params.backtest_lookback_days != null)
      elBtLookback.value = params.backtest_lookback_days;
    if (elBtBuy && params.buy_score != null) elBtBuy.value = params.buy_score;
    if (elBtSell && params.sell_score != null) elBtSell.value = params.sell_score;
    if (elBtStop && params.stop_loss_pct != null) elBtStop.value = params.stop_loss_pct;
  }

  async function loadParamsAndRuns() {
    try {
      const [cfg, runs] = await Promise.all([
        fetchJson(`/api/v1/timing/config?run_code=${encodeURIComponent(activeRunCode)}`),
        fetchJson("/api/v1/timing/backtest/runs?limit=30"),
      ]);
      const items = runs.items || [];
      if (elBtRunCode) {
        const codes = new Set(["daily_default", "web_custom"]);
        items.forEach((r) => codes.add(r.run_code));
        elBtRunCode.innerHTML = Array.from(codes)
          .map((c) => `<option value="${c}"${c === activeRunCode ? " selected" : ""}>${c}</option>`)
          .join("");
      }
      const p = cfg.active_params || cfg.defaults || {};
      fillParamInputs(p);
      if (elBtParamsView) {
        elBtParamsView.innerHTML = [
          metric("买入阈值", fmt(p.buy_score, 0), true),
          metric("卖出阈值", fmt(p.sell_score, 0)),
          metric("止损", fmtPct(p.stop_loss_pct)),
          metric("成本bp", fmt(p.cost_bps, 1)),
          metric("回看日", p.backtest_lookback_days != null ? String(p.backtest_lookback_days) : "—"),
          metric("exec", p.exec_model || "t1_open"),
          metric("快照", cfg.run ? cfg.run.run_code : "默认"),
        ].join("");
      }
    } catch (e) {
      if (elBtParamsView) elBtParamsView.innerHTML = metric("参数", e.message || "加载失败");
    }
  }

  async function runCustomBacktest() {
    const td = selectedDate();
    const qs = new URLSearchParams({
      run_code: (elBtRunCode && elBtRunCode.value) || "web_custom",
    });
    if (td) qs.set("trade_date", td);
    if (elBtCost && elBtCost.value !== "") qs.set("cost_bps", elBtCost.value);
    if (elBtLookback && elBtLookback.value !== "") qs.set("lookback_days", elBtLookback.value);
    if (elBtBuy && elBtBuy.value !== "") qs.set("buy_score", elBtBuy.value);
    if (elBtSell && elBtSell.value !== "") qs.set("sell_score", elBtSell.value);
    if (elBtStop && elBtStop.value !== "") qs.set("stop_loss_pct", elBtStop.value);
    showError("");
    btnBtRun && (btnBtRun.disabled = true);
    try {
      const res = await fetch(`/api/v1/timing/backtest/run?${qs.toString()}`, {
        method: "POST",
        credentials: "same-origin",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || res.statusText || "回测失败");
      activeRunCode = qs.get("run_code") || "web_custom";
      await loadParamsAndRuns();
      await loadBtSummary();
      await loadRank();
      if (currentCode) await openDetail(currentCode);
    } catch (e) {
      showError(e.message || String(e));
    } finally {
      btnBtRun && (btnBtRun.disabled = false);
    }
  }

  async function loadSignals() {
    const td = selectedDate();
    if (!td) return;
    const sig = elSigFilter.value;
    const types = encodeURIComponent(elTypes.value);
    let url = `/api/v1/timing/signals?trade_date=${td}&content_types=${types}&top=100`;
    if (sig === "buy" || sig === "sell") url += `&signal_type=${sig}`;
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
    const sort = encodeURIComponent(elSort.value || "score");
    const sig = elSigFilter.value;
    let url =
      `/api/v1/timing/rank?trade_date=${td}&content_types=${types}&top=80&sort=${sort}&with_metrics=true`;
    if (sig === "buy" || sig === "sell") url += `&signal_type=${sig}`;
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
          `<td class="${tonePct(r.bt_total_return)}">${fmtPct(r.bt_total_return)}</td>` +
          `<td>${fmtPct(r.bt_win_rate)}</td>` +
          `<td>${r.bt_trade_count != null ? r.bt_trade_count : "—"}</td>` +
          `<td>${fmtPct(r.bt_max_drawdown)}</td>` +
          `</tr>`
        );
      })
      .join("");
    elRankEmpty.classList.toggle("hidden", items.length > 0);
    elRankBody.querySelectorAll("tr[data-code]").forEach((tr) => {
      tr.addEventListener("click", () => openDetail(tr.getAttribute("data-code")));
    });
  }

  function renderDetailHeader(payload) {
    const name = payload.name || payload.industry_code || currentCode;
    const code = payload.display_code || payload.industry_code || currentCode;
    const t = payload.latest_timing || {};
    const bt = (payload.backtest && payload.backtest.metrics) || {};
    elDetailTitle.textContent = `${name} · ${code}`;
    elDetailMetrics.innerHTML = [
      metric("综合分", fmt(t.score), true),
      metric("状态", labelState(t.position_state)),
      metric("信号", labelSignal(t.signal_type)),
      metric("收益率", fmtPct(bt.total_return), true),
      metric("买入持有", fmtPct(bt.bench_return)),
      metric("超额", fmtPct(bt.excess_return)),
      metric("成功率", fmtPct(bt.win_rate)),
      metric("夏普", fmt(bt.sharpe, 2)),
      metric("Calmar", fmt(bt.calmar, 2)),
      metric("盈亏比", fmt(bt.profit_factor, 2)),
      metric("回撤", fmtPct(bt.max_drawdown)),
      metric("连亏", bt.max_loss_streak != null ? String(bt.max_loss_streak) : "—"),
      metric("交易数", bt.trade_count != null ? String(bt.trade_count) : "—"),
      metric("成交", payload.exec_model || "t1_open"),
    ].join("");
  }

  function renderTrades(payload) {
    const trades = (payload.backtest && payload.backtest.trades) || [];
    elBtTradeBody.innerHTML = trades
      .map((t) => {
        return (
          `<tr>` +
          `<td>${t.buy_signal_date || "—"}</td>` +
          `<td>${t.entry_date || "—"}</td>` +
          `<td>${fmt(t.entry_price, 2)}</td>` +
          `<td>${t.sell_signal_date || "—"}</td>` +
          `<td>${t.exit_date || "—"}</td>` +
          `<td>${fmt(t.exit_price, 2)}</td>` +
          `<td class="${tonePct(t.return_pct)}">${fmtPct(t.return_pct)}</td>` +
          `<td>${t.hold_days != null ? t.hold_days : "—"}</td>` +
          `<td>${t.is_open ? "盯市" : "已平"}</td>` +
          `<td class="muted">${t.exit_reason || "—"}</td>` +
          `</tr>`
        );
      })
      .join("");
  }

  function renderHist(payload) {
    const sigs = payload.signals || [];
    elHistBody.innerHTML = sigs
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

  function renderCharts(payload) {
    if (kline.renderTimingKlineChart) {
      chartInst = kline.renderTimingKlineChart(elChart, payload, {
        chartInst,
        volMode,
      });
    }
    const curve = (payload.backtest && payload.backtest.equity_curve) || [];
    const buyhold = (payload.backtest && payload.backtest.buyhold_curve) || [];
    if (kline.renderTimingEquityChart) {
      equityInst = kline.renderTimingEquityChart(elEquity, curve, {
        chartInst: equityInst,
        buyholdCurve: buyhold,
      });
    }
  }

  async function openDetail(code) {
    if (!code) return;
    currentCode = code;
    const td = selectedDate();
    const url =
      `/api/v1/timing/boards/${encodeURIComponent(code)}/kline?days=${klineDays}` +
      (td ? `&trade_date=${td}` : "");
    try {
      showError("");
      const payload = await fetchJson(url);
      lastPayload = payload;
      elDetailCard.classList.remove("hidden");
      renderDetailHeader(payload);
      renderCharts(payload);
      renderTrades(payload);
      renderHist(payload);
      elDetailCard.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      showError(e.message || String(e));
    }
  }

  async function refreshAll() {
    showError("");
    await Promise.all([loadParamsAndRuns(), loadBtSummary(), loadSignals(), loadRank()]);
  }

  function applyQueryParams() {
    const qs = new URLSearchParams(window.location.search);
    const code = qs.get("code");
    const days = Number(qs.get("days") || 0);
    if (days === 20 || days === 60 || days === 120) {
      klineDays = days;
      if (elPresets) {
        elPresets.querySelectorAll(".chip").forEach((c) => {
          c.classList.toggle("active", Number(c.getAttribute("data-days")) === klineDays);
        });
      }
    }
    if (code) {
      setTimeout(() => openDetail(code), 0);
    }
  }

  btnQuery && btnQuery.addEventListener("click", () => refreshAll().catch((e) => showError(e.message)));
  elDate && elDate.addEventListener("change", () => refreshAll().catch((e) => showError(e.message)));
  btnBtRun && btnBtRun.addEventListener("click", () => runCustomBacktest());
  elBtRunCode &&
    elBtRunCode.addEventListener("change", () => {
      activeRunCode = elBtRunCode.value || "daily_default";
      loadParamsAndRuns()
        .then(() => loadBtSummary())
        .then(() => loadRank())
        .then(() => (currentCode ? openDetail(currentCode) : null))
        .catch((e) => showError(e.message));
    });
  btnKline &&
    btnKline.addEventListener("click", () => {
      if (currentCode) openDetail(currentCode);
    });
  elPresets &&
    elPresets.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".chip");
      if (!btn) return;
      klineDays = Number(btn.getAttribute("data-days")) || 60;
      elPresets.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      if (currentCode) openDetail(currentCode);
    });
  elVolChips &&
    elVolChips.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".chip");
      if (!btn) return;
      volMode = btn.getAttribute("data-vol") || "vol";
      elVolChips.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      if (lastPayload) renderCharts(lastPayload);
    });

  window.addEventListener("resize", () => {
    chartInst && chartInst.resize();
    equityInst && equityInst.resize();
  });

  loadDates()
    .then(() => refreshAll())
    .then(() => applyQueryParams())
    .catch((e) => showError(e.message || String(e)));
})();
