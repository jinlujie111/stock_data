(function () {
  const form = document.getElementById("ask-form");
  const input = document.getElementById("ask-input");
  const messages = document.getElementById("ask-messages");
  const submitBtn = document.getElementById("ask-submit");
  const suggestions = document.getElementById("ask-suggestions");
  const SESSION_KEY = "iff_ask_session_id";
  let sessionId = sessionStorage.getItem(SESSION_KEY) || "";

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function appendMessage(role, html, extraClass) {
    const wrap = document.createElement("div");
    wrap.className = "ask-msg ask-msg-" + role + (extraClass ? " " + extraClass : "");
    wrap.innerHTML = '<div class="ask-msg-body">' + html + "</div>";
    messages.appendChild(wrap);
    messages.scrollTop = messages.scrollHeight;
    return wrap;
  }

  function formatDataBlock(data) {
    if (!data) return "";
    const json = JSON.stringify(data, null, 2);
    return (
      '<details class="ask-data-details"><summary>查看原始数据</summary>' +
      '<pre class="ask-data-pre">' +
      escapeHtml(json) +
      "</pre></details>"
    );
  }

  function formatSources(sources) {
    if (!sources || !sources.length) return "";
    const links = sources
      .map(function (s) {
        return '<a href="' + escapeHtml(s.href) + '" class="ask-source-link">' + escapeHtml(s.title) + "</a>";
      })
      .join(" · ");
    return '<div class="ask-sources">来源：' + links + "</div>";
  }

  function formatMeta(meta) {
    const parts = [];
    if (meta.trade_date) parts.push("交易日 " + escapeHtml(meta.trade_date));
    if (meta.follow_up) parts.push("追问");
    if (meta.llm_used) parts.push("AI 汇总");
    else parts.push("规则摘要");
    return '<div class="ask-meta muted">' + parts.join(" · ") + "</div>";
  }

  async function sendQuestion(question) {
    const q = (question || "").trim();
    if (!q) return;

    appendMessage("user", escapeHtml(q));
    input.value = "";
    submitBtn.disabled = true;
    const pending = appendMessage("bot", '<span class="ask-loading">查询中…</span>', "ask-msg-pending");

    try {
      const resp = await fetch("/api/v1/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, session_id: sessionId || null }),
      });
      const payload = await resp.json();
      pending.remove();

      if (!resp.ok) {
        const detail = payload.detail;
        const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
        appendMessage("bot", '<span class="ask-error">' + escapeHtml(msg || "请求失败") + "</span>");
        return;
      }

      if (payload.session_id) {
        sessionId = payload.session_id;
        sessionStorage.setItem(SESSION_KEY, sessionId);
      }

      let body = "<p>" + escapeHtml(payload.answer || "无回答") + "</p>";
      body += formatMeta(payload);
      body += formatSources(payload.sources);
      body += formatDataBlock(payload.data);
      appendMessage("bot", body);
    } catch (err) {
      pending.remove();
      appendMessage("bot", '<span class="ask-error">网络错误，请稍后重试。</span>');
    } finally {
      submitBtn.disabled = false;
      input.focus();
    }
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    sendQuestion(input.value);
  });

  suggestions.addEventListener("click", function (e) {
    const btn = e.target.closest("[data-question]");
    if (!btn) return;
    sendQuestion(btn.getAttribute("data-question"));
  });

  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
})();
