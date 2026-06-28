(function () {
  const elDate = document.getElementById("trade-date");
  const elKeyword = document.getElementById("track-keyword");
  const elTracksBody = document.getElementById("tracks-body");
  const elTracksEmpty = document.getElementById("tracks-empty");
  const elPoolCard = document.getElementById("pool-card");
  const elPoolTitle = document.getElementById("pool-title");
  const elPoolBody = document.getElementById("pool-body");
  const elPoolEmpty = document.getElementById("pool-empty");
  const elPageError = document.getElementById("page-error");
  const btnQuery = document.getElementById("btn-query");

  function fmtNum(v, d) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(d == null ? 1 : d);
  }

  async function apiGet(path) {
    const res = await fetch(path, { credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "请求失败");
    return data;
  }

  function showError(msg) {
    elPageError.textContent = msg;
    elPageError.classList.remove("hidden");
  }

  function clearError() {
    elPageError.classList.add("hidden");
  }

  async function loadDates() {
    const data = await apiGet("/api/v1/ai-core/trade-dates?limit=60");
    elDate.innerHTML = "";
    (data.dates || []).forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d;
      opt.textContent = d;
      elDate.appendChild(opt);
    });
    if (data.latest) elDate.value = data.latest;
  }

  async function loadTracks() {
    clearError();
    const td = elDate.value;
    const kw = elKeyword.value.trim();
    let path = `/api/v1/ai-core/tracks?trade_date=${encodeURIComponent(td)}`;
    if (kw) path += `&keyword=${encodeURIComponent(kw)}`;
    const data = await apiGet(path);
    const items = data.items || [];
    elTracksBody.innerHTML = "";
    if (!items.length) {
      elTracksEmpty.classList.remove("hidden");
      return;
    }
    elTracksEmpty.classList.add("hidden");
    items.forEach((t) => {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${t.heat_sort || "—"}</td>` +
        `<td>${t.industry_name}<br><span class="muted">${t.industry_id}</span></td>` +
        `<td>${t.content_type || "—"}</td>` +
        `<td>${t.core_cnt || 0}</td>` +
        `<td><button type="button" class="btn btn-ghost btn-sm" data-iid="${t.industry_id}">查看核心池</button></td>`;
      tr.querySelector("button").addEventListener("click", () => loadPool(t.industry_id, t.industry_name));
      elTracksBody.appendChild(tr);
    });
  }

  async function loadPool(industryId, industryName) {
    clearError();
    const td = elDate.value;
    const data = await apiGet(
      `/api/v1/ai-core/pool?trade_date=${encodeURIComponent(td)}&industry_id=${encodeURIComponent(industryId)}`
    );
    elPoolCard.classList.remove("hidden");
    elPoolTitle.textContent = `核心池：${industryName || data.industry_name}`;
    elPoolBody.innerHTML = "";
    const items = data.items || [];
    if (!items.length) {
      elPoolEmpty.classList.remove("hidden");
      return;
    }
    elPoolEmpty.classList.add("hidden");
    items.forEach((r) => {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${r.ts_code}</td>` +
        `<td>${r.stock_name || "—"}</td>` +
        `<td><span class="level-badge level-${(r.level || "").toLowerCase()}">${r.level || "—"}</span></td>` +
        `<td>${fmtNum(r.score, 1)}</td>` +
        `<td>${fmtNum(r.weight, 4)}</td>` +
        `<td>${r.segment || "—"}</td>` +
        `<td class="reason-cell">${r.reason || "—"}</td>`;
      elPoolBody.appendChild(tr);
    });
  }

  btnQuery.addEventListener("click", () => {
    loadTracks().catch((e) => showError(e.message));
  });

  loadDates()
    .then(() => loadTracks())
    .catch((e) => showError(e.message));
})();
