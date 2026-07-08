(function () {
  const { fmtNum, apiGet, toApiTradeDate, initTradeDateCalendar } = window.DcBoard;
  const page = window.__START_SIGNAL_PAGE__ || { mode: "short" };
  const mode = page.mode === "mid" ? "mid" : "short";

  const elDate = document.getElementById("trade-date");
  const elTop = document.getElementById("top-n");
  const typeChips = document.getElementById("content-type-chips");
  const statusChips = document.getElementById("status-chips");
  const elRankBody = document.getElementById("rank-body");
  const elRankEmpty = document.getElementById("rank-empty");
  const elRankUpdated = document.getElementById("rank-updated");
  const elSummary = document.getElementById("summary-pills");
  const elPageError = document.getElementById("page-error");
  const elFilterHint = document.getElementById("filter-hint");
  const elRuleHint = document.getElementById("rule-hint");
  const btnQuery = document.getElementById("btn-query");

  let selectedTypes = ["行业", "概念"];
  let selectedStatus = "";

  if (elRuleHint) {
    elRuleHint.textContent =
      mode === "short"
        ? "短期规则：阶段为资金试探/板块爆发、净流入≥2天、资金加速>0、VP≥70、信号 launch/main_rise，满足≥3条判启动；放弃≥2条硬条件优先。"
        : "中期规则：等级主线/超级主线、阶段板块爆发/机构化、均线走强、净流入≥3天、资金加速>0，满足≥3条判启动；放弃≥2条硬条件优先。";
  }

  function showError(msg) {
    elPageError.textContent = msg;
    elPageError.classList.remove("hidden");
  }

  function clearError() {
    elPageError.classList.add("hidden");
  }

  function statusClass(status) {
    if (status === "启动") return "status-start";
    if (status === "观察") return "status-watch";
    return "status-drop";
  }

  function levelClass(level) {
    if (level === "超级主线") return "level-super";
    if (level === "主线") return "level-main";
    if (level === "轮动热点") return "level-rotate";
    return "level-follow";
  }

  function stageClass(stage) {
    if (stage === "板块爆发") return "stage-tag stage-burst";
    if (stage === "机构化") return "stage-tag stage-inst";
    if (stage === "资金试探") return "stage-tag stage-probe";
    return "stage-tag";
  }

  function fmtYi(val) {
    if (val === null || val === undefined || val === "") return "—";
    const n = Number(val);
    if (Number.isNaN(n)) return "—";
    return (n / 1e8).toFixed(2) + "亿";
  }

  function fmtDays(val) {
    if (val === null || val === undefined || val === "") return "—";
    return Math.trunc(Number(val)) + "天";
  }

  if (typeChips) {
    typeChips.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      btn.classList.toggle("active");
      selectedTypes = Array.from(typeChips.querySelectorAll(".chip.active"))
        .map((c) => c.dataset.value)
        .filter(Boolean);
      if (!selectedTypes.length) {
        btn.classList.add("active");
        selectedTypes = [btn.dataset.value];
      }
    });
  }

  if (statusChips) {
    statusChips.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      statusChips.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      selectedStatus = btn.dataset.value || "";
    });
  }

  function buildUrl() {
    const params = new URLSearchParams();
    params.set("mode", mode);
    if (elDate.value) params.set("trade_date", toApiTradeDate(elDate.value));
    params.set("top", elTop.value);
    if (selectedTypes.length) params.set("content_types", selectedTypes.join(","));
    if (selectedStatus) params.set("status", selectedStatus);
    return `/api/v1/start-signal/evaluate?${params}`;
  }

  function renderSummary(summary) {
    if (!summary) {
      elSummary.innerHTML = "";
      return;
    }
    elSummary.innerHTML = `
      <span class="summary-pill">启动<strong class="status-start">${summary["启动"] || 0}</strong></span>
      <span class="summary-pill">观察<strong class="status-watch">${summary["观察"] || 0}</strong></span>
      <span class="summary-pill">放弃<strong>${summary["放弃"] || 0}</strong></span>
      <span class="summary-pill">持续增量资金<strong>${summary.incremental || 0}</strong></span>
    `;
  }

  function renderRank(data) {
    const label = data.mode_label || (mode === "short" ? "短期" : "中期");
    elRankUpdated.textContent = `交易日 ${data.trade_date} · ${label}规则 · ${data.items.length} 条`;
    renderSummary(data.summary);
    if (!data.items.length) {
      elRankBody.innerHTML = "";
      elRankEmpty.classList.remove("hidden");
      return;
    }
    elRankEmpty.classList.add("hidden");
    elRankBody.innerHTML = data.items
      .map((row) => {
        const incr = row.is_incremental_fund_inflow
          ? '<span class="tag-incr">持续增量</span>'
          : "—";
        const parts = `${fmtNum(row.score_mainline)}/${fmtNum(row.score_fund_rule)}/${fmtNum(row.score_vp_rule)}/${fmtNum(row.score_leader_rule)}`;
        const hits = `启${row.start_hit_count || 0}/增${row.incr_hit_count || 0}/弃${row.abandon_hit_count || 0}`;
        return `
      <tr>
        <td>${row.rank ?? "—"}</td>
        <td class="${statusClass(row.signal_status)}">${row.signal_status || "—"}</td>
        <td>${incr}</td>
        <td>${row.content_type || "—"}</td>
        <td>${row.industry_name || "—"}<br><span class="muted">${row.industry_code || ""}</span></td>
        <td><strong>${fmtNum(row.total_score)}</strong></td>
        <td class="score-parts" title="主线/资金/量价/龙头">${parts}</td>
        <td class="${levelClass(row.mainline_level)}">${row.mainline_level || "—"}</td>
        <td><span class="${stageClass(row.mainline_stage)}">${row.mainline_stage || "—"}</span></td>
        <td>${fmtDays(row.net_inflow_days)}</td>
        <td>${fmtYi(row.fund_accel)}</td>
        <td>${fmtNum(row.vp_score)}</td>
        <td>${row.vp_signal_label || row.vp_signal_type || "—"}<br><span class="muted">${row.vp_status_label || row.vp_status || ""}</span></td>
        <td>${row.leader_name || "—"}</td>
        <td class="muted">${hits}</td>
      </tr>`;
      })
      .join("");
  }

  async function queryRank() {
    clearError();
    elFilterHint.textContent = "查询中…";
    try {
      const data = await apiGet(buildUrl());
      renderRank(data);
      elFilterHint.textContent = "";
    } catch (err) {
      elFilterHint.textContent = "";
      showError(err.message || String(err));
    }
  }

  btnQuery.addEventListener("click", queryRank);

  (async function init() {
    try {
      await initTradeDateCalendar(elDate, "/api/v1/start-signal/trade-dates?limit=90");
      await queryRank();
    } catch (err) {
      showError(err.message || String(err));
    }
  })();
})();
