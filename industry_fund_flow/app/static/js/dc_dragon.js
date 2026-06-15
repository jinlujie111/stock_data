(function () {
  const elDate = document.getElementById("trade-date");
  const chipGroup = document.getElementById("content-type-chips");
  const elKeyword = document.getElementById("board-keyword");
  const elLeadersBody = document.getElementById("leaders-body");
  const elLeadersEmpty = document.getElementById("leaders-empty");
  const elLeadersUpdated = document.getElementById("leaders-updated");
  const elPageError = document.getElementById("page-error");
  const elDetailCard = document.getElementById("detail-card");
  const elDetailTitle = document.getElementById("detail-title");
  const elSummary = document.getElementById("summary-text");
  const elScoresBody = document.getElementById("scores-body");
  const btnQuery = document.getElementById("btn-query");
  const btnClose = document.getElementById("btn-close-detail");

  let selectedTypes = ["行业", "概念"];

  function fmtNum(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(1);
  }

  function showError(msg) {
    elPageError.textContent = msg;
    elPageError.classList.remove("hidden");
  }

  function clearError() {
    elPageError.classList.add("hidden");
  }

  function getContentTypesParam() {
    return selectedTypes.length ? selectedTypes.join(",") : "行业,概念";
  }

  function bindChips() {
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
          chipGroup.querySelectorAll(".chip").forEach((c) => {
            if (["行业", "概念"].includes(c.dataset.value)) c.classList.add("active");
          });
        }
      });
    });
  }

  async function loadTradeDates() {
    const res = await fetch("/api/v1/dragon/trade-dates");
    if (!res.ok) throw new Error("加载交易日失败");
    const data = await res.json();
    elDate.innerHTML = "";
    (data.dates || []).forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d;
      opt.textContent = d;
      elDate.appendChild(opt);
    });
    if (data.latest) elDate.value = data.latest;
  }

  async function loadLeaders() {
    clearError();
    const td = elDate.value;
    const kw = elKeyword.value.trim();
    const params = new URLSearchParams({
      trade_date: td,
      content_types: getContentTypesParam(),
      top: "100",
    });
    if (kw) params.set("keyword", kw);
    const res = await fetch(`/api/v1/dragon/leaders?${params}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "加载龙头榜失败");
    elLeadersUpdated.textContent = `数据日期：${data.trade_date || td}`;
    const items = data.items || [];
    if (!items.length) {
      elLeadersBody.innerHTML = "";
      elLeadersEmpty.classList.remove("hidden");
      return;
    }
    elLeadersEmpty.classList.add("hidden");
    elLeadersBody.innerHTML = items
      .map(
        (r) =>
          `<tr>` +
          `<td>${r.content_type || "—"}</td>` +
          `<td>${r.industry_name || r.industry_code}</td>` +
          `<td>${r.leader_composite_name || "—"}</td>` +
          `<td>${fmtNum(r.score_composite)}</td>` +
          `<td>${r.leader_fund_name || "—"}</td>` +
          `<td>${r.leader_trend_name || "—"}</td>` +
          `<td><button type="button" class="btn btn-ghost btn-drill" data-code="${r.industry_code}">下钻</button></td>` +
          `</tr>`
      )
      .join("");
    elLeadersBody.querySelectorAll(".btn-drill").forEach((btn) => {
      btn.addEventListener("click", () => openDetail(btn.dataset.code));
    });
  }

  async function openDetail(industryCode) {
    clearError();
    const td = elDate.value;
    const [sumRes, scoreRes] = await Promise.all([
      fetch(`/api/v1/dragon/boards/${encodeURIComponent(industryCode)}/summary?trade_date=${td}`),
      fetch(`/api/v1/dragon/boards/${encodeURIComponent(industryCode)}/scores?trade_date=${td}`),
    ]);
    const summary = await sumRes.json();
    const scores = await scoreRes.json();
    if (!sumRes.ok) throw new Error(summary.detail || "加载摘要失败");
    if (!scoreRes.ok) throw new Error(scores.detail || "加载评分明细失败");
    elDetailTitle.textContent = `${summary.industry_name || industryCode} · 成分股评分`;
    elSummary.textContent = summary.summary_text || "";
    const items = scores.items || [];
    elScoresBody.innerHTML = items
      .map(
        (r) =>
          `<tr${r.is_composite_leader ? ' class="row-leader"' : ""}>` +
          `<td>${r.stock_name || r.ts_code}</td>` +
          `<td>${fmtNum(r.score_composite)}</td>` +
          `<td>${fmtNum(r.score_fund)}</td>` +
          `<td>${fmtNum(r.score_trend)}</td>` +
          `<td>${fmtNum(r.score_inst)}</td>` +
          `<td>${r.rank_composite ?? "—"}</td>` +
          `</tr>`
      )
      .join("");
    elDetailCard.classList.remove("hidden");
    elDetailCard.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function refresh() {
    try {
      await loadLeaders();
    } catch (e) {
      showError(e.message || String(e));
    }
  }

  btnQuery.addEventListener("click", refresh);
  btnClose.addEventListener("click", () => elDetailCard.classList.add("hidden"));

  bindChips();
  loadTradeDates()
    .then(refresh)
    .catch((e) => showError(e.message || String(e)));
})();
