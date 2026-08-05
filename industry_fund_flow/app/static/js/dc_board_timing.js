(function () {
  const board = window.DcBoard || {};
  const kline = window.DcKline || {};
  const { normalizeIsoDate, toApiTradeDate } = board;

  const PAGE =
    (document.querySelector(".timing-wb") &&
      document.querySelector(".timing-wb").getAttribute("data-timing-page")) ||
    "signals";
  const SHOW_SIGNALS = PAGE === "signals";
  const SHOW_RANK = PAGE === "rank";
  const SHOW_BACKTEST = PAGE === "backtest";

  const elDate = document.getElementById("trade-date");
  const elTypes = document.getElementById("content-types");
  const elSigFilter = document.getElementById("signal-filter");
  const elSort = document.getElementById("sort-key");
  const elSearch = document.getElementById("board-search");
  const elDropdown = document.getElementById("board-dropdown");
  const elFilterHint = document.getElementById("filter-hint");
  const btnDatePrev = document.getElementById("btn-date-prev");
  const btnDateNext = document.getElementById("btn-date-next");
  const btnDateLatest = document.getElementById("btn-date-latest");
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
  const elLinkBacktest = document.getElementById("link-to-backtest");
  const elPickHint = document.getElementById("backtest-pick-hint");
  const elPickCard = document.getElementById("backtest-pick-card");

  let chartInst = null;
  let equityInst = null;
  let currentCode = "";
  let klineDays = 60;
  let volMode = "vol";
  let lastPayload = null;
  let activeRunCode = "daily_default";
  let tradeDatesIso = []; // desc: latest first
  let searchTimer = null;

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

  function signalBadge(s) {
    if (s === "buy") return `<span class="sig-badge sig-badge--buy">买入</span>`;
    if (s === "sell") return `<span class="sig-badge sig-badge--sell">卖出</span>`;
    return `<span class="muted">—</span>`;
  }

  function statePill(s) {
    const cls =
      s === "long" ? "pos-pill--long" : s === "watch" ? "pos-pill--watch" : s === "flat" ? "pos-pill--flat" : "";
    return `<span class="pos-pill ${cls}">${labelState(s)}</span>`;
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

  function metric(label, val, strong, tone) {
    const toneCls = tone ? ` ${tone}` : "";
    const strongCls = strong ? " strong" : "";
    return (
      `<div class="tw-kpi"><span class="tw-kpi-label">${label}</span>` +
      `<span class="tw-kpi-val${strongCls}${toneCls}">${val}</span></div>`
    );
  }

  function markActiveRow(code) {
    document.querySelectorAll(".timing-wb-table tr.clickable-row").forEach((tr) => {
      tr.classList.toggle("is-active", tr.getAttribute("data-code") === code);
    });
  }

  async function loadDates() {
    const data = await fetchJson("/api/v1/timing/trade-dates?limit=500");
    tradeDatesIso = (data.dates || [])
      .map((d) => (normalizeIsoDate ? normalizeIsoDate(d) : String(d).slice(0, 10)))
      .filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d));
    const latest = (normalizeIsoDate && normalizeIsoDate(data.latest)) || tradeDatesIso[0] || "";
    if (!tradeDatesIso.length) {
      showError("暂无择时数据，请先运行 run_board_timing_batch");
      updateDateHint();
      return;
    }
    if (elDate) {
      elDate.min = tradeDatesIso[tradeDatesIso.length - 1];
      elDate.max = tradeDatesIso[0];
      elDate.value = latest;
    }
    updateDateHint();
    updateDateNavState();
  }

  function selectedDate() {
    if (!elDate || !elDate.value) return "";
    return toApiTradeDate ? toApiTradeDate(elDate.value) : String(elDate.value).replace(/-/g, "");
  }

  function searchKeyword() {
    return (elSearch && elSearch.value ? elSearch.value : "").trim();
  }

  /** 对齐到最近有效交易日：优先同日，否则往前找，再往后找 */
  function snapToTradeDate(iso) {
    if (!iso || !tradeDatesIso.length) return iso || "";
    if (tradeDatesIso.includes(iso)) return iso;
    for (const d of tradeDatesIso) {
      if (d <= iso) return d;
    }
    return tradeDatesIso[tradeDatesIso.length - 1];
  }

  function setTradeDate(iso, { refresh = true } = {}) {
    const snapped = snapToTradeDate(iso);
    if (!snapped || !elDate) return;
    if (elDate.value !== snapped) elDate.value = snapped;
    updateDateHint(iso !== snapped ? iso : "");
    updateDateNavState();
    if (refresh) refreshAll().catch((e) => showError(e.message));
  }

  function updateDateHint(requested) {
    if (!elFilterHint) return;
    const cur = elDate && elDate.value ? elDate.value : "—";
    const latest = tradeDatesIso[0] || "—";
    const parts = [`当前 ${cur}`, `最新 ${latest}`, `共 ${tradeDatesIso.length} 个交易日`];
    if (requested && requested !== cur) parts.unshift(`已对齐到最近交易日（原 ${requested}）`);
    const kw = searchKeyword();
    if (kw) parts.push(`搜索「${kw}」`);
    elFilterHint.textContent = parts.join(" · ");
  }

  function updateDateNavState() {
    const idx = tradeDatesIso.indexOf(elDate && elDate.value);
    if (btnDatePrev) btnDatePrev.disabled = idx < 0 || idx >= tradeDatesIso.length - 1;
    if (btnDateNext) btnDateNext.disabled = idx <= 0;
    if (btnDateLatest) btnDateLatest.disabled = !tradeDatesIso.length || idx === 0;
  }

  function shiftTradeDate(delta) {
    if (!elDate || !tradeDatesIso.length) return;
    const idx = tradeDatesIso.indexOf(elDate.value);
    const cur = idx >= 0 ? idx : 0;
    // tradeDatesIso 降序：+1 = 更早，-1 = 更新
    const next = Math.max(0, Math.min(tradeDatesIso.length - 1, cur + delta));
    setTradeDate(tradeDatesIso[next]);
  }

  function hideDropdown() {
    if (elDropdown) elDropdown.classList.add("hidden");
  }

  function showDropdown(items) {
    if (!elDropdown) return;
    if (!items.length) {
      elDropdown.innerHTML = '<div class="board-option board-option--empty">无匹配板块</div>';
    } else {
      elDropdown.innerHTML = items
        .map((it) => {
          const code = it.industry_code || "";
          const name = it.industry_name || code;
          const ct = it.content_type || "—";
          const score = it.score != null ? ` · ${fmt(it.score)}` : "";
          const sig =
            it.signal_type === "buy" ? "买" : it.signal_type === "sell" ? "卖" : "";
          const sigHtml = sig ? ` <span class="sig-badge sig-badge--${it.signal_type}">${sig}</span>` : "";
          return (
            `<button type="button" class="board-option" data-code="${code}" data-name="${name}">` +
            `[${ct}] ${name} (${code})${score}${sigHtml}</button>`
          );
        })
        .join("");
    }
    elDropdown.classList.remove("hidden");
  }

  async function searchBoardsSuggest(keyword) {
    const kw = (keyword || "").trim();
    if (!kw) {
      hideDropdown();
      return;
    }
    const td = selectedDate();
    const types = encodeURIComponent(elTypes.value || "行业,概念");
    const tdQ = td ? `&trade_date=${encodeURIComponent(td)}` : "";
    try {
      const data = await fetchJson(
        `/api/v1/timing/boards/search?keyword=${encodeURIComponent(kw)}&content_types=${types}&limit=20${tdQ}`
      );
      showDropdown(data.items || []);
    } catch (e) {
      showDropdown([]);
      showError(e.message || String(e));
    }
  }

  function scheduleSearchSuggest() {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      searchBoardsSuggest(searchKeyword()).catch((e) => showError(e.message));
    }, 220);
  }

  async function loadBtSummary() {
    if (!SHOW_BACKTEST || !elBtSummary || elBtSummary.classList.contains("hidden")) return;
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
        metric("平均收益", fmtPct(run.avg_return), false, tonePct(run.avg_return)),
        metric("等权收益", fmtPct(run.total_return), true, tonePct(run.total_return)),
        metric("买入持有", fmtPct(run.bench_return), false, tonePct(run.bench_return)),
        metric("最大回撤", fmtPct(run.max_drawdown), false, "tone-down"),
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
    if (!SHOW_BACKTEST) return;
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
    if (!SHOW_BACKTEST) return;
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
    if (!SHOW_SIGNALS || !elSigBody) return;
    const td = selectedDate();
    if (!td) return;
    const sig = elSigFilter.value;
    const types = encodeURIComponent(elTypes.value);
    const kw = searchKeyword();
    let url = `/api/v1/timing/signals?trade_date=${td}&content_types=${types}&top=100`;
    if (sig === "buy" || sig === "sell") url += `&signal_type=${sig}`;
    if (kw) url += `&keyword=${encodeURIComponent(kw)}`;
    const data = await fetchJson(url);
    const items = data.items || [];
    elSigBody.innerHTML = items
      .map((r) => {
        return (
          `<tr data-code="${r.industry_code}" class="clickable-row">` +
          `<td>${signalBadge(r.signal_type)}</td>` +
          `<td><strong>${r.industry_name || r.industry_code}</strong></td>` +
          `<td class="muted">${r.content_type || "—"}</td>` +
          `<td><strong>${fmt(r.score)}</strong></td>` +
          `<td>${fmt(r.score_trend)}</td>` +
          `<td>${fmt(r.score_fund)}</td>` +
          `<td>${fmt(r.score_vp)}</td>` +
          `<td>${fmt(r.score_sentiment)}</td>` +
          `<td class="muted">${r.signal_reason || "—"}</td>` +
          `</tr>`
        );
      })
      .join("");
    elSigEmpty && elSigEmpty.classList.toggle("hidden", items.length > 0);
    elSigBody.querySelectorAll("tr[data-code]").forEach((tr) => {
      tr.addEventListener("click", () => openDetail(tr.getAttribute("data-code")));
    });
    if (currentCode) markActiveRow(currentCode);
  }

  async function loadRank() {
    if (!SHOW_RANK || !elRankBody) return;
    const td = selectedDate();
    if (!td) return;
    const types = encodeURIComponent(elTypes.value);
    const kw = searchKeyword();
    const sort = encodeURIComponent(elSort.value || "score");
    const sig = elSigFilter.value;
    const top = kw ? 120 : 80;
    let url =
      `/api/v1/timing/rank?trade_date=${td}&content_types=${types}&top=${top}&sort=${sort}&with_metrics=true`;
    if (sig === "buy" || sig === "sell") url += `&signal_type=${sig}`;
    if (kw) url += `&keyword=${encodeURIComponent(kw)}`;
    const data = await fetchJson(url);
    const items = data.items || [];
    elRankBody.innerHTML = items
      .map((r, i) => {
        return (
          `<tr data-code="${r.industry_code}" class="clickable-row">` +
          `<td class="muted">${r.rank_score != null ? r.rank_score : i + 1}</td>` +
          `<td><strong>${r.industry_name || r.industry_code}</strong></td>` +
          `<td class="muted">${r.content_type || "—"}</td>` +
          `<td><strong>${fmt(r.score)}</strong></td>` +
          `<td>${statePill(r.position_state)}</td>` +
          `<td class="${tonePct(r.bt_total_return)}">${fmtPct(r.bt_total_return)}</td>` +
          `<td>${fmtPct(r.bt_win_rate)}</td>` +
          `<td>${r.bt_trade_count != null ? r.bt_trade_count : "—"}</td>` +
          `<td class="tone-down">${fmtPct(r.bt_max_drawdown)}</td>` +
          `</tr>`
        );
      })
      .join("");
    elRankEmpty && elRankEmpty.classList.toggle("hidden", items.length > 0);
    if (elRankEmpty) {
      elRankEmpty.textContent = kw
        ? `未找到匹配「${kw}」的板块`
        : "暂无数据，请先跑日批";
    }
    elRankBody.querySelectorAll("tr[data-code]").forEach((tr) => {
      tr.addEventListener("click", () => openDetail(tr.getAttribute("data-code")));
    });
    if (currentCode) markActiveRow(currentCode);
    updateDateHint();
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
      metric("信号", labelSignal(t.signal_type), false, signalClass(t.signal_type)),
      metric("收益率", fmtPct(bt.total_return), true, tonePct(bt.total_return)),
      metric("买入持有", fmtPct(bt.bench_return), false, tonePct(bt.bench_return)),
      metric("超额", fmtPct(bt.excess_return), false, tonePct(bt.excess_return)),
      metric("成功率", fmtPct(bt.win_rate)),
      metric("夏普", fmt(bt.sharpe, 2)),
      metric("Calmar", fmt(bt.calmar, 2)),
      metric("盈亏比", fmt(bt.profit_factor, 2)),
      metric("回撤", fmtPct(bt.max_drawdown), false, "tone-down"),
      metric("连亏", bt.max_loss_streak != null ? String(bt.max_loss_streak) : "—"),
      metric("交易数", bt.trade_count != null ? String(bt.trade_count) : "—"),
      metric("成交", payload.exec_model || "t1_open"),
    ].join("");
  }

  function renderTrades(payload) {
    if (!elBtTradeBody) return;
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
    if (!elHistBody) return;
    const sigs = payload.signals || [];
    elHistBody.innerHTML = sigs
      .slice()
      .reverse()
      .map((s) => {
        return (
          `<tr>` +
          `<td>${s.trade_date || "—"}</td>` +
          `<td>${signalBadge(s.signal_type)}</td>` +
          `<td>${fmt(s.score)}</td>` +
          `<td class="muted">${s.signal_reason || "—"}</td>` +
          `</tr>`
        );
      })
      .join("");
  }

  function renderCharts(payload) {
    if (elChart && kline.renderTimingKlineChart) {
      chartInst = kline.renderTimingKlineChart(elChart, payload, {
        chartInst,
        volMode,
      });
    }
    if (elEquity && kline.renderTimingEquityChart) {
      const curve = (payload.backtest && payload.backtest.equity_curve) || [];
      const buyhold = (payload.backtest && payload.backtest.buyhold_curve) || [];
      equityInst = kline.renderTimingEquityChart(elEquity, curve, {
        chartInst: equityInst,
        buyholdCurve: buyhold,
      });
    }
  }

  function syncBacktestLink(code) {
    if (!elLinkBacktest || !code) return;
    const td = selectedDate();
    const qs = new URLSearchParams({ code });
    if (td) qs.set("trade_date", td);
    elLinkBacktest.href = `/dc/timing-backtest?${qs.toString()}`;
  }

  async function openDetail(code) {
    if (!code) return;
    currentCode = code;
    markActiveRow(code);
    syncBacktestLink(code);
    const td = selectedDate();
    const url =
      `/api/v1/timing/boards/${encodeURIComponent(code)}/kline?days=${klineDays}` +
      (td ? `&trade_date=${td}` : "");
    try {
      showError("");
      const payload = await fetchJson(url);
      lastPayload = payload;
      if (elPickCard) elPickCard.classList.add("hidden");
      if (elPickHint) elPickHint.classList.add("hidden");
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
    updateDateHint();
    const tasks = [];
    if (SHOW_BACKTEST) {
      tasks.push(loadParamsAndRuns(), loadBtSummary());
    }
    if (SHOW_SIGNALS) tasks.push(loadSignals());
    if (SHOW_RANK) tasks.push(loadRank());
    await Promise.all(tasks);
  }

  function applyQueryParams() {
    const qs = new URLSearchParams(window.location.search);
    const code = qs.get("code");
    const days = Number(qs.get("days") || 0);
    const td = qs.get("trade_date");
    const kw = qs.get("keyword") || qs.get("q");
    if (days === 20 || days === 60 || days === 120) {
      klineDays = days;
      if (elPresets) {
        elPresets.querySelectorAll(".chip").forEach((c) => {
          c.classList.toggle("active", Number(c.getAttribute("data-days")) === klineDays);
        });
      }
    }
    if (kw && elSearch) elSearch.value = kw;
    if (td) {
      const iso = normalizeIsoDate ? normalizeIsoDate(td) : td;
      if (iso) {
        setTradeDate(iso, { refresh: false });
        return refreshAll().then(() => {
          if (code) openDetail(code);
        });
      }
    }
    if (code) {
      setTimeout(() => openDetail(code), 0);
    }
  }

  btnQuery &&
    btnQuery.addEventListener("click", () => {
      hideDropdown();
      refreshAll().catch((e) => showError(e.message));
    });
  elDate &&
    elDate.addEventListener("change", () => {
      setTradeDate(elDate.value);
    });
  btnDatePrev && btnDatePrev.addEventListener("click", () => shiftTradeDate(1));
  btnDateNext && btnDateNext.addEventListener("click", () => shiftTradeDate(-1));
  btnDateLatest &&
    btnDateLatest.addEventListener("click", () => {
      if (tradeDatesIso[0]) setTradeDate(tradeDatesIso[0]);
    });
  elSearch &&
    elSearch.addEventListener("input", () => {
      scheduleSearchSuggest();
      updateDateHint();
    });
  elSearch &&
    elSearch.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        hideDropdown();
        refreshAll().catch((e) => showError(e.message));
      } else if (ev.key === "Escape") {
        hideDropdown();
      }
    });
  elDropdown &&
    elDropdown.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".board-option[data-code]");
      if (!btn) return;
      const code = btn.getAttribute("data-code");
      const name = btn.getAttribute("data-name") || code;
      if (elSearch) elSearch.value = name;
      hideDropdown();
      refreshAll()
        .then(() => openDetail(code))
        .catch((e) => showError(e.message));
    });
  document.addEventListener("click", (ev) => {
    if (!elDropdown || elDropdown.classList.contains("hidden")) return;
    if (ev.target.closest(".tw-board-picker")) return;
    hideDropdown();
  });
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
