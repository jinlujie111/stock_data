(function () {
  const { fmtNum, apiGet } = window.DcBoard;

  const elStrategy = document.getElementById("sel-strategy");
  const elStart = document.getElementById("bt-start");
  const elEnd = document.getElementById("bt-end");
  const elCapital = document.getElementById("bt-capital");
  const btnRun = document.getElementById("btn-run");
  const elRunsBody = document.getElementById("runs-body");
  const elRunsEmpty = document.getElementById("runs-empty");
  const elError = document.getElementById("page-error");
  const elDetail = document.getElementById("bt-detail");
  const elDetailTitle = document.getElementById("detail-title");
  const elDetailMetrics = document.getElementById("detail-metrics");
  const elNavChart = document.getElementById("nav-chart");
  const elTradesBody = document.getElementById("trades-body");

  let pollTimer = null;

  function showError(msg) {
    elError.textContent = msg;
    elError.classList.remove("hidden");
  }
  function clearError() {
    elError.classList.add("hidden");
  }

  function pct(v) {
    if (v === null || v === undefined) return "—";
    return (Number(v) * 100).toFixed(2) + "%";
  }

  function toApi(d) {
    return (d || "").replace(/-/g, "");
  }

  async function apiPost(path, body) {
    const res = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "请求失败");
    return data;
  }

  async function loadStrategies() {
    const data = await apiGet("/api/v1/quant/strategies");
    const items = data.items || [];
    elStrategy.innerHTML = items
      .map((s) => `<option value="${s.id}">${s.name}（${s.horizon === "long" ? "长线" : "短线"}）</option>`)
      .join("");
  }

  function statusBadge(s) {
    const map = { done: "cell-rise", failed: "cell-fall", running: "", pending: "" };
    return `<span class="${map[s] || ""}">${s}</span>`;
  }

  async function loadRuns() {
    const data = await apiGet("/api/v1/quant/backtests");
    const items = data.items || [];
    if (!items.length) {
      elRunsBody.innerHTML = "";
      elRunsEmpty.classList.remove("hidden");
      return items;
    }
    elRunsEmpty.classList.add("hidden");
    elRunsBody.innerHTML = items
      .map(
        (r) => `
      <tr>
        <td>${r.id}</td>
        <td>${r.strategy_name || "—"}</td>
        <td class="muted">${r.start_date}~${r.end_date}</td>
        <td>${statusBadge(r.status)}</td>
        <td class="${Number(r.total_return) >= 0 ? "cell-rise" : "cell-fall"}">${pct(r.total_return)}</td>
        <td>${pct(r.annual_return)}</td>
        <td class="cell-fall">${pct(r.max_drawdown)}</td>
        <td>${r.sharpe != null ? fmtNum(r.sharpe, 2) : "—"}</td>
        <td>${pct(r.win_rate)}</td>
        <td>${r.trade_count != null ? r.trade_count : "—"}</td>
        <td>${pct(r.bench_return)}</td>
        <td><button type="button" class="btn btn-ghost btn-sm" data-view="${r.id}">查看</button></td>
      </tr>`
      )
      .join("");
    elRunsBody.querySelectorAll("[data-view]").forEach((btn) => {
      btn.addEventListener("click", () => loadDetail(btn.dataset.view).catch((e) => showError(e.message)));
    });
    return items;
  }

  function renderNavChart(nav) {
    if (!nav || !nav.length) {
      elNavChart.innerHTML = '<div class="table-empty">无净值数据</div>';
      return;
    }
    const w = 860;
    const h = 260;
    const pad = { l: 46, r: 12, t: 12, b: 24 };
    const navs = nav.map((x) => Number(x.nav));
    const benchs = nav.map((x) => (x.bench_nav != null ? Number(x.bench_nav) : null));
    const all = navs.concat(benchs.filter((v) => v != null));
    const minY = Math.min(...all);
    const maxY = Math.max(...all);
    const span = maxY - minY || 1;
    const innerW = w - pad.l - pad.r;
    const innerH = h - pad.t - pad.b;
    const px = (i) => pad.l + (i / Math.max(1, nav.length - 1)) * innerW;
    const py = (v) => pad.t + innerH - ((v - minY) / span) * innerH;
    const line = (arr, stroke) => {
      const pts = [];
      arr.forEach((v, i) => {
        if (v == null) return;
        pts.push(`${px(i)},${py(v)}`);
      });
      return `<polyline fill="none" stroke="${stroke}" stroke-width="1.8" points="${pts.join(" ")}"/>`;
    };
    const one = py(1);
    elNavChart.innerHTML = `
      <svg class="history-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:${h}px">
        <line x1="${pad.l}" y1="${one}" x2="${w - pad.r}" y2="${one}" stroke="#cbd5e1" stroke-dasharray="4 4"/>
        ${line(navs, "#2563eb")}
        ${line(benchs, "#f59e0b")}
      </svg>
      <div class="muted" style="font-size:12px">蓝线=策略净值 · 橙线=沪深300基准 · 虚线=1.0</div>`;
  }

  function renderMetrics(run) {
    const m = [
      ["总收益", pct(run.total_return)],
      ["年化", pct(run.annual_return)],
      ["最大回撤", pct(run.max_drawdown)],
      ["夏普", run.sharpe != null ? fmtNum(run.sharpe, 2) : "—"],
      ["胜率", pct(run.win_rate)],
      ["交易数", run.trade_count != null ? run.trade_count : "—"],
      ["基准收益", pct(run.bench_return)],
    ];
    elDetailMetrics.innerHTML = m
      .map(([k, v]) => `<span class="metric-chip"><b>${v}</b><span class="muted">${k}</span></span>`)
      .join("");
  }

  async function loadDetail(runId) {
    const run = await apiGet(`/api/v1/quant/backtests/${runId}`);
    elDetail.style.display = "";
    elDetailTitle.textContent = `#${run.id} ${run.strategy_name || ""} ${run.start_date}~${run.end_date} · ${run.status}`;
    if (run.status === "failed") {
      elNavChart.innerHTML = `<div class="alert alert-error">回测失败：${run.error_msg || "未知错误"}</div>`;
      elDetailMetrics.innerHTML = "";
      elTradesBody.innerHTML = "";
      return;
    }
    renderMetrics(run);
    renderNavChart(run.nav || []);
    const trades = run.trades || [];
    elTradesBody.innerHTML = trades
      .slice(0, 500)
      .map(
        (t) => `
      <tr>
        <td>${t.trade_date}</td>
        <td class="${t.side === "BUY" ? "cell-rise" : "cell-fall"}">${t.side}</td>
        <td>${t.ts_code}</td>
        <td>${t.stock_name || "—"}</td>
        <td>${fmtNum(t.price, 2)}</td>
        <td>${t.shares != null ? t.shares : "—"}</td>
        <td class="${Number(t.pnl) >= 0 ? "cell-rise" : "cell-fall"}">${t.pnl != null ? fmtNum(t.pnl, 0) : "—"}</td>
        <td>${t.return_pct != null ? pct(t.return_pct) : "—"}</td>
        <td>${t.hold_days != null ? t.hold_days : "—"}</td>
        <td class="muted">${t.reason || "—"}</td>
      </tr>`
      )
      .join("");
    elDetail.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function pollRun(runId) {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      try {
        const runs = await loadRuns();
        const cur = (runs || []).find((r) => r.id === runId);
        if (cur && (cur.status === "done" || cur.status === "failed")) {
          clearInterval(pollTimer);
          pollTimer = null;
          await loadDetail(runId);
        }
      } catch (e) {
        clearInterval(pollTimer);
      }
    }, 3000);
  }

  async function runBacktest() {
    clearError();
    const sid = Number(elStrategy.value);
    if (!sid) {
      showError("请选择策略");
      return;
    }
    btnRun.disabled = true;
    btnRun.textContent = "回测中…";
    try {
      const res = await apiPost("/api/v1/quant/backtests", {
        strategy_id: sid,
        start_date: toApi(elStart.value),
        end_date: toApi(elEnd.value),
        init_capital: Number(elCapital.value) || 1000000,
      });
      await loadRuns();
      pollRun(res.run_id);
    } catch (err) {
      showError(err.message);
    } finally {
      btnRun.disabled = false;
      btnRun.textContent = "开始回测";
    }
  }

  btnRun.addEventListener("click", runBacktest);

  (async function init() {
    try {
      if (!elEnd.value) {
        const t = new Date();
        elEnd.value = t.toISOString().slice(0, 10);
      }
      await loadStrategies();
      await loadRuns();
    } catch (err) {
      showError(err.message);
    }
  })();
})();
