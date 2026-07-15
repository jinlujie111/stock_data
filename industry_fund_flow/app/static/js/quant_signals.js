(function () {
  const { fmtNum, apiGet, klineLink } = window.DcBoard;

  const elStrategy = document.getElementById("sel-strategy");
  const elDate = document.getElementById("sel-date");
  const elBody = document.getElementById("signal-body");
  const elEmpty = document.getElementById("signal-empty");
  const elUpdated = document.getElementById("signal-updated");
  const elError = document.getElementById("page-error");
  const btnQuery = document.getElementById("btn-query");

  function showError(msg) {
    elError.textContent = msg;
    elError.classList.remove("hidden");
  }
  function clearError() {
    elError.classList.add("hidden");
  }

  function actionBadge(a) {
    const map = { BUY: "cell-rise", SELL: "cell-fall", HOLD: "" };
    const label = { BUY: "新买", SELL: "剔除", HOLD: "续持" };
    return `<span class="${map[a] || ""}">${label[a] || a}</span>`;
  }

  function fmtFactors(f) {
    if (!f) return "—";
    return Object.keys(f)
      .map((k) => `${k}:${f[k].rank != null ? f[k].rank : "—"}`)
      .join(" · ");
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
    const items = (data.items || []).filter((s) => s.is_active);
    elStrategy.innerHTML = items
      .map((s) => `<option value="${s.id}">${s.name}（${s.horizon === "long" ? "长线" : "短线"}）</option>`)
      .join("");
  }

  async function loadDates() {
    const sid = elStrategy.value;
    if (!sid) return;
    const data = await apiGet(`/api/v1/quant/strategies/${sid}/signal-dates`);
    const dates = data.dates || [];
    elDate.innerHTML = dates.map((d) => `<option value="${d}">${d}</option>`).join("");
  }

  function recordLink(row) {
    return `<button type="button" class="btn btn-ghost btn-sm" data-rec="${row.ts_code}" data-name="${row.stock_name || ""}" data-close="${row.close != null ? row.close : ""}">记买卖点</button>`;
  }

  async function loadSignals() {
    clearError();
    const sid = elStrategy.value;
    if (!sid) return;
    const td = elDate.value ? `?trade_date=${elDate.value.replace(/-/g, "")}` : "";
    const data = await apiGet(`/api/v1/quant/strategies/${sid}/signals${td}`);
    const items = data.items || [];
    elUpdated.textContent = `信号日 ${data.trade_date || "—"} · ${items.length} 条`;
    if (!items.length) {
      elBody.innerHTML = "";
      elEmpty.classList.remove("hidden");
      return;
    }
    elEmpty.classList.add("hidden");
    elBody.innerHTML = items
      .map(
        (row) => `
      <tr>
        <td>${actionBadge(row.action)}</td>
        <td>${row.rank_no != null ? row.rank_no : "—"}</td>
        <td>${row.ts_code}</td>
        <td>${row.stock_name || "—"}</td>
        <td>${fmtNum(row.score, 1)}</td>
        <td>${row.close != null ? fmtNum(row.close, 2) : "—"}</td>
        <td class="muted">${fmtFactors(row.factors)}</td>
        <td>${recordLink(row)}</td>
        <td>${klineLink("stock", row.ts_code, elDate.value)}</td>
      </tr>`
      )
      .join("");
    elBody.querySelectorAll("[data-rec]").forEach((btn) => {
      btn.addEventListener("click", () => recordTrade(btn));
    });
  }

  async function recordTrade(btn) {
    const side = window.prompt("记录买卖点：输入 BUY 或 SELL", "BUY");
    if (!side) return;
    const s = side.trim().toUpperCase();
    if (s !== "BUY" && s !== "SELL") {
      showError("只能输入 BUY 或 SELL");
      return;
    }
    const price = window.prompt("成交价", btn.dataset.close || "");
    if (!price) return;
    const shares = window.prompt("股数（可留空）", "");
    try {
      await apiPost("/api/v1/quant/trades", {
        ts_code: btn.dataset.rec,
        stock_name: btn.dataset.name || null,
        side: s,
        trade_date: (elDate.value || "").replace(/-/g, ""),
        price: Number(price),
        shares: shares ? Number(shares) : null,
        strategy_id: Number(elStrategy.value) || null,
      });
      window.alert("已记录");
    } catch (err) {
      showError(err.message);
    }
  }

  btnQuery.addEventListener("click", () => loadSignals().catch((e) => showError(e.message)));
  elStrategy.addEventListener("change", async () => {
    try {
      await loadDates();
      await loadSignals();
    } catch (e) {
      showError(e.message);
    }
  });
  elDate.addEventListener("change", () => loadSignals().catch((e) => showError(e.message)));

  (async function init() {
    try {
      await loadStrategies();
      await loadDates();
      await loadSignals();
    } catch (err) {
      showError(err.message);
    }
  })();
})();
