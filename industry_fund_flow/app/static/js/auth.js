(function () {
  const form = document.getElementById("login-form") || document.getElementById("register-form");
  const errorEl = document.getElementById("error");
  if (!form || !errorEl) return;

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

      if (res.status === 303 || res.status === 0) {
        window.location.href = "/";
        return;
      }

      let detail = "操作失败，请重试";
      try {
        const data = await res.json();
        detail = data.detail || detail;
      } catch (_) {
        /* 非 JSON 响应 */
      }
      errorEl.textContent = typeof detail === "string" ? detail : JSON.stringify(detail);
      errorEl.classList.remove("hidden");
    } catch (err) {
      errorEl.textContent = "网络错误，请稍后重试";
      errorEl.classList.remove("hidden");
    } finally {
      if (btn) btn.disabled = false;
    }
  });
})();
