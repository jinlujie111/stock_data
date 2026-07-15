(function () {
  const { fmtNum, apiGet } = window.DcBoard;

  const elError = document.getElementById("page-error");
  const elLogBody = document.getElementById("log-body");
  const elLogEmpty = document.getElementById("log-empty");
  const elPosBody = document.getElementById("pos-body");
  const elPosEmpty = document.getElementById("pos-empty");

  const f = {
    code: document.getElementById("t-code"),
    name: document.getElementById("t-name"),
    side: document.getElementById("t-side"),
    date: document.getElementById("t-date"),
    price: document.getElementById("t-price"),
    shares: document.getElementById("t-shares"),
    note: document.getElementById("t-note"),
  };

  function showError(msg) {
    elError.textContent = msg;
    elError.classList.remove("hidden");
  }
  function clearError() {
    elError.classList.add("hidden");
  }

  function cls(v) {
    const n = Number(v);
    if (Number.isNaN(n)) return "";
    return n > 0 ? "cell-rise" : n < 0 ? "cell-fall" : "";
  }

  async function apiSend(method, path, body) {
    const res = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "请求失败");
    return data;
  }

  async function loadPositions() {
    const data = await apiGet("/api/v1/quant/positions");
    const items = data.items || [];
    if (!items.length) {
      elPosBody.innerHTML = "";
      elPosEmpty.classList.remove("hidden");
      return;
    }
    elPosEmpty.classList.add("hidden");
    elPosBody.innerHTML = items
      .map(
        (p) => `
      <tr>
        <td>${p.ts_code}</td>
        <td>${p.stock_name || "—"}</td>
        <td>${p.net_shares}</td>
        <td>${p.avg_cost != null ? fmtNum(p.avg_cost, 2) : "—"}</td>
        <td>${p.cur_price != null ? fmtNum(p.cur_price, 2) : "—"}</td>
        <td>${p.market_value != null ? fmtNum(p.market_value, 0) : "—"}</td>
        <td class="${cls(p.unrealized)}">${p.unrealized != null ? fmtNum(p.unrealized, 0) : "—"}</td>
        <td class="${cls(p.unrealized_pct)}">${p.unrealized_pct != null ? p.unrealized_pct.toFixed(2) + "%" : "—"}</td>
      </tr>`
      )
      .join("");
  }

  async function loadLog() {
    clearError();
    const data = await apiGet("/api/v1/quant/trades");
    const items = data.items || [];
    if (!items.length) {
      elLogBody.innerHTML = "";
      elLogEmpty.classList.remove("hidden");
      return;
    }
    elLogEmpty.classList.add("hidden");
    elLogBody.innerHTML = items
      .map(
        (t) => `
      <tr>
        <td>${t.trade_date}</td>
        <td class="${t.side === "BUY" ? "cell-rise" : "cell-fall"}">${t.side === "BUY" ? "买入" : "卖出"}</td>
        <td>${t.ts_code}</td>
        <td>${t.stock_name || "—"}</td>
        <td>${fmtNum(t.price, 2)}</td>
        <td>${t.shares != null ? t.shares : "—"}</td>
        <td>${t.amount != null ? fmtNum(t.amount, 0) : "—"}</td>
        <td class="muted">${t.source === "strategy" ? "策略" : "手动"}</td>
        <td class="muted">${t.note || "—"}</td>
        <td><button type="button" class="btn btn-ghost btn-sm" data-del="${t.id}">删除</button></td>
      </tr>`
      )
      .join("");
    elLogBody.querySelectorAll("[data-del]").forEach((b) =>
      b.addEventListener("click", () => del(b.dataset.del))
    );
  }

  async function del(id) {
    try {
      await apiSend("DELETE", `/api/v1/quant/trades/${id}`);
      await refresh();
    } catch (e) {
      showError(e.message);
    }
  }

  async function add() {
    clearError();
    if (!f.code.value.trim()) {
      showError("请输入代码");
      return;
    }
    if (!f.date.value) {
      showError("请选择日期");
      return;
    }
    if (!f.price.value) {
      showError("请输入价格");
      return;
    }
    try {
      await apiSend("POST", "/api/v1/quant/trades", {
        ts_code: f.code.value.trim(),
        stock_name: f.name.value.trim() || null,
        side: f.side.value,
        trade_date: f.date.value.replace(/-/g, ""),
        price: Number(f.price.value),
        shares: f.shares.value ? Number(f.shares.value) : null,
        note: f.note.value.trim() || null,
      });
      f.price.value = "";
      f.shares.value = "";
      f.note.value = "";
      await refresh();
    } catch (e) {
      showError(e.message);
    }
  }

  async function refresh() {
    await loadPositions();
    await loadLog();
  }

  document.getElementById("btn-add").addEventListener("click", add);

  (function init() {
    f.date.value = new Date().toISOString().slice(0, 10);
    refresh().catch((e) => showError(e.message));
  })();
})();
