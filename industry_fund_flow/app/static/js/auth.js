(function () {
  const form = document.getElementById("login-form") || document.getElementById("register-form");
  const errorEl = document.getElementById("error");
  if (!form || !errorEl) return;

  function formatDetail(data) {
    if (!data || data.detail === undefined || data.detail === null) {
      return "操作失败，请重试";
    }
    const d = data.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d.map(function (item) {
        return item.msg || item.message || JSON.stringify(item);
      }).join("；");
    }
    return JSON.stringify(d);
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    errorEl.classList.add("hidden");
    const btn = form.querySelector('button[type="submit"]');
    if (btn) btn.disabled = true;

    try {
      const res = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        redirect: "manual",
      });

      if (res.status === 303 || res.status === 302 || res.status === 307 || res.status === 0) {
        window.location.href = "/";
        return;
      }

      if (res.ok) {
        window.location.href = "/";
        return;
      }

      let detail = "操作失败，请重试";
      const text = await res.text();
      try {
        detail = formatDetail(JSON.parse(text));
      } catch (_) {
        if (text && text.length < 200) detail = text;
      }
      errorEl.textContent = detail;
      errorEl.classList.remove("hidden");
    } catch (err) {
      errorEl.textContent = "网络错误，请稍后重试";
      errorEl.classList.remove("hidden");
    } finally {
      if (btn) btn.disabled = false;
    }
  });
})();
