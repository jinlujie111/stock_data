(function () {
  const { apiGet } = window.DcBoard;

  const elBody = document.getElementById("strat-body");
  const elError = document.getElementById("page-error");
  const elCode = document.getElementById("f-code");
  const elName = document.getElementById("f-name");
  const elHorizon = document.getElementById("f-horizon");
  const elDesc = document.getElementById("f-desc");
  const elConfig = document.getElementById("f-config");
  const elTitle = document.getElementById("editor-title");

  let editingId = null;

  const TPL_SHORT = {
    horizon: "short",
    universe: { exclude_st: true, min_amount: 80000000, min_list_days: 60, exclude_limit: true },
    factors: [
      { name: "mom20", weight: 0.3, direction: 1 },
      { name: "vp_score", weight: 0.25, direction: 1 },
      { name: "netflow5", weight: 0.2, direction: 1 },
      { name: "breakout", weight: 0.15, direction: 1 },
      { name: "turnover", weight: 0.1, direction: 1 },
    ],
    select: { top_n: 20, rebalance: "daily" },
    risk: { stop_loss: -0.08, take_profit: 0.2, max_hold_days: 10, exit_rule: "ma20_break" },
  };
  const TPL_LONG = {
    horizon: "long",
    universe: { exclude_st: true, min_amount: 50000000, min_list_days: 120, mv_min: 5000000, mv_max: null },
    factors: [
      { name: "roe", weight: 0.25, direction: 1 },
      { name: "growth", weight: 0.25, direction: 1 },
      { name: "pe_inv", weight: 0.15, direction: 1 },
      { name: "pb_inv", weight: 0.1, direction: 1 },
      { name: "mom120", weight: 0.15, direction: 1 },
      { name: "above_ma60", weight: 0.1, direction: 1 },
    ],
    select: { top_n: 30, rebalance: "monthly" },
    risk: { stop_loss: -0.15, take_profit: null, max_hold_days: null, exit_rule: null },
  };

  function showError(msg) {
    elError.textContent = msg;
    elError.classList.remove("hidden");
  }
  function clearError() {
    elError.classList.add("hidden");
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

  async function loadList() {
    clearError();
    const data = await apiGet("/api/v1/quant/strategies");
    const items = data.items || [];
    elBody.innerHTML = items
      .map((s) => {
        const canEdit = !s.is_system;
        return `
      <tr>
        <td>${s.name}</td>
        <td class="muted">${s.code}</td>
        <td>${s.horizon === "long" ? "长线" : "短线"}</td>
        <td class="muted">${s.description || "—"}</td>
        <td>${s.is_system ? "内置" : "自定义"}</td>
        <td>${s.is_active ? "是" : "否"}</td>
        <td>
          <button type="button" class="btn btn-ghost btn-sm" data-copy='${s.id}'>复制</button>
          ${canEdit ? `<button type="button" class="btn btn-ghost btn-sm" data-edit='${s.id}'>编辑</button>` : ""}
          ${canEdit ? `<button type="button" class="btn btn-ghost btn-sm" data-del='${s.id}'>删除</button>` : ""}
        </td>
      </tr>`;
      })
      .join("");
    window._strats = items;
    elBody.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => edit(b.dataset.edit)));
    elBody.querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", () => copy(b.dataset.copy)));
    elBody.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => del(b.dataset.del)));
  }

  function findStrat(id) {
    return (window._strats || []).find((s) => String(s.id) === String(id));
  }

  function edit(id) {
    const s = findStrat(id);
    if (!s) return;
    editingId = s.id;
    elTitle.textContent = `编辑策略：${s.name}`;
    elCode.value = s.code;
    elCode.disabled = true;
    elName.value = s.name;
    elHorizon.value = s.horizon;
    elDesc.value = s.description || "";
    elConfig.value = JSON.stringify(s.config || {}, null, 2);
  }

  function copy(id) {
    const s = findStrat(id);
    if (!s) return;
    editingId = null;
    elTitle.textContent = "新建策略（复制）";
    elCode.disabled = false;
    elCode.value = s.code + "_copy";
    elName.value = s.name + " 副本";
    elHorizon.value = s.horizon;
    elDesc.value = s.description || "";
    elConfig.value = JSON.stringify(s.config || {}, null, 2);
  }

  async function del(id) {
    if (!window.confirm("确认删除该策略？")) return;
    try {
      await apiSend("DELETE", `/api/v1/quant/strategies/${id}`);
      await loadList();
    } catch (e) {
      showError(e.message);
    }
  }

  function reset() {
    editingId = null;
    elTitle.textContent = "新建策略";
    elCode.disabled = false;
    elCode.value = "";
    elName.value = "";
    elDesc.value = "";
    elConfig.value = "";
  }

  async function save() {
    clearError();
    let config;
    try {
      config = JSON.parse(elConfig.value);
    } catch (e) {
      showError("配置 JSON 解析失败：" + e.message);
      return;
    }
    try {
      if (editingId) {
        await apiSend("PUT", `/api/v1/quant/strategies/${editingId}`, {
          name: elName.value,
          description: elDesc.value,
          config,
        });
      } else {
        await apiSend("POST", "/api/v1/quant/strategies", {
          code: elCode.value,
          name: elName.value,
          horizon: elHorizon.value,
          description: elDesc.value,
          config,
        });
      }
      reset();
      await loadList();
    } catch (e) {
      showError(e.message);
    }
  }

  document.getElementById("btn-save").addEventListener("click", save);
  document.getElementById("btn-reset").addEventListener("click", reset);
  document.getElementById("btn-fill-short").addEventListener("click", () => {
    elConfig.value = JSON.stringify(TPL_SHORT, null, 2);
    elHorizon.value = "short";
  });
  document.getElementById("btn-fill-long").addEventListener("click", () => {
    elConfig.value = JSON.stringify(TPL_LONG, null, 2);
    elHorizon.value = "long";
  });

  loadList().catch((e) => showError(e.message));
})();
