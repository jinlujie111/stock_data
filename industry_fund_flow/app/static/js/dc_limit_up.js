(function () {
  const { apiGet, toApiTradeDate, initTradeDateCalendar } = window.DcBoard;

  const elDate = document.getElementById("trade-date");
  const elLadderBody = document.getElementById("ladder-body");
  const elLadderEmpty = document.getElementById("ladder-empty");
  const elLadderSummary = document.getElementById("ladder-summary");
  const elPageError = document.getElementById("page-error");
  const elFilterHint = document.getElementById("filter-hint");
  const btnQuery = document.getElementById("btn-query");

  function showError(msg) {
    elPageError.textContent = msg;
    elPageError.classList.remove("hidden");
  }

  function clearError() {
    elPageError.classList.add("hidden");
  }

  function cellClass(v) {
    const n = Number(v);
    if (Number.isNaN(n) || v === null || v === "") return "cell-rise";
    return n >= 0 ? "cell-rise" : "cell-fall";
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

  function renderCard(item) {
    const industry = item.industry ? `<span class="ladder-card-industry">${item.industry}</span>` : "";
    return `
      <div class="ladder-card" data-ts="${item.ts_code}" data-name="${item.name || ""}">
        <button type="button" class="ladder-card-add" title="加入股票自选" data-add="${item.ts_code}" data-name="${item.name || ""}">+</button>
        <div class="ladder-card-name">${item.name || item.ts_code}${industry}</div>
        <div class="ladder-card-stat ${cellClass(item.pct_chg)}">${item.stat_text || "—"}</div>
        <div class="ladder-card-code">${item.ts_code || ""}</div>
      </div>`;
  }

  function renderSection(group) {
    if (!group.count) {
      return `
        <div class="ladder-section">
          <div class="ladder-section-head">
            <h3>${group.label}</h3>
            <span class="ladder-section-count">(0个)</span>
          </div>
          <div class="ladder-empty-section">暂无</div>
        </div>`;
    }
    return `
      <div class="ladder-section">
        <div class="ladder-section-head">
          <h3>${group.label}</h3>
          <span class="ladder-section-count">(${group.count}个)</span>
        </div>
        <div class="ladder-grid">
          ${group.items.map(renderCard).join("")}
        </div>
      </div>`;
  }

  function bindCards() {
    elLadderBody.querySelectorAll(".ladder-card-add").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        apiPost("/api/v1/favorites/stocks", {
          ts_code: btn.dataset.add,
          stock_name: btn.dataset.name || null,
        })
          .then(() => {
            btn.textContent = "★";
            btn.disabled = true;
          })
          .catch((err) => showError(err.message));
      });
    });
  }

  function renderLadder(data) {
    elLadderSummary.textContent = `交易日 ${data.trade_date} · 涨停 ${data.total} 只`;
    if (!data.total) {
      elLadderBody.innerHTML = "";
      elLadderEmpty.classList.remove("hidden");
      return;
    }
    elLadderEmpty.classList.add("hidden");
    elLadderBody.innerHTML = data.groups.map(renderSection).join("");
    bindCards();
  }

  async function queryLadder() {
    clearError();
    elFilterHint.textContent = "查询中…";
    try {
      const td = elDate.value ? toApiTradeDate(elDate.value) : "";
      const q = td ? `?trade_date=${td}` : "";
      const data = await apiGet(`/api/v1/limit-up/ladder${q}`);
      renderLadder(data);
      elFilterHint.textContent = "";
    } catch (err) {
      elFilterHint.textContent = "";
      showError(err.message);
    }
  }

  btnQuery.addEventListener("click", () => queryLadder().catch((err) => showError(err.message)));
  elDate.addEventListener("change", () => queryLadder().catch((err) => showError(err.message)));

  (async function init() {
    try {
      await initTradeDateCalendar(elDate, "/api/v1/limit-up/trade-dates?limit=90");
      await queryLadder();
    } catch (err) {
      showError(err.message);
    }
  })();
})();
