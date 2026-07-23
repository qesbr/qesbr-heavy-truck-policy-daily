const state = { reports: [], type: "daily", current: null };
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, character => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
}[character]));
const typeNames = { daily: "日报", weekly: "周报", monthly: "月报" };
const categoryNames = { 政策: "POLICY", 法规: "REGULATION", 标准: "STANDARD", 市场: "MARKET", 企业: "COMPANY" };
const formatDate = value => new Intl.DateTimeFormat("zh-CN", {
  year: "numeric", month: "2-digit", day: "2-digit", timeZone: "Asia/Shanghai"
}).format(new Date(value));
const readMinutes = articles => Math.max(1, Math.ceil(
  articles.reduce((total, article) => total + (article.summary_zh || "").length, 0) / 420
));

function reportsOfType() {
  return state.reports
    .filter(report => report.report_type === state.type)
    .sort((left, right) => right.period_end.localeCompare(left.period_end));
}

function issueLabel(report) {
  const [, month, day] = report.period_end.split("-").map(Number);
  if (state.type === "daily") return `${day} 日`;
  if (state.type === "weekly") return `${formatDate(report.period_start)} — ${formatDate(report.period_end)}`;
  return `${month} 月`;
}

function headline(report) {
  return report.articles?.[0]?.title_zh || "暂无重要更新";
}

function renderArchive() {
  const grouped = new Map();
  reportsOfType().forEach(report => {
    const key = report.period_end.slice(0, 7);
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(report);
  });
  $("#archive").innerHTML = [...grouped].map(([month, reports], index) => `
    <section class="month-group">
      <button class="month-title" type="button" aria-expanded="${index === 0}">
        <span>${index === 0 ? "⌄" : "›"}</span>
        <strong>${month.replace("-", " 年 ")} 月</strong>
        <small>${reports.length}</small>
      </button>
      <div class="issue-list" ${index === 0 ? "" : "hidden"}>
        ${reports.map(report => `
          <button class="issue ${state.current?.report_id === report.report_id ? "active" : ""}" data-id="${escapeHtml(report.report_id)}">
            <b>${escapeHtml(issueLabel(report))}</b>
            <span>${escapeHtml(headline(report))}</span>
            <em>${report.articles?.length || 0}</em>
          </button>
        `).join("")}
      </div>
    </section>
  `).join("") || '<p class="archive-empty">暂无报告</p>';

  $$(".month-title").forEach(button => button.addEventListener("click", () => {
    const list = button.nextElementSibling;
    const expanded = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!expanded));
    button.firstElementChild.textContent = expanded ? "›" : "⌄";
    list.hidden = expanded;
  }));
  $$(".issue").forEach(button => button.addEventListener("click", () => {
    state.current = state.reports.find(report => report.report_id === button.dataset.id);
    render();
    if (window.innerWidth <= 900) $(".report-page").scrollIntoView({ behavior: "smooth" });
  }));
}

function storyCard(article) {
  const related = (article.related_sources || []).map(source => `
    <li><a target="_blank" rel="noopener" href="${escapeHtml(source.source_url)}">${escapeHtml(source.title)} · ${escapeHtml(source.source_name)}</a></li>
  `).join("");
  const originalTitle = article.title_original && article.title_original !== article.title_zh
    ? `<p class="original-title">${escapeHtml(article.title_original)}</p>` : "";
  return `
    <article class="story">
      <h3>${escapeHtml(article.title_zh)}</h3>
      ${originalTitle}
      <div class="byline"><span>${escapeHtml(article.source_type)}</span>${escapeHtml(article.source_name)} · ${formatDate(article.published_at)}</div>
      <p>${escapeHtml(article.summary_zh)}</p>
      <div class="story-foot">
        ${(article.tags || []).map(tag => `<span>${escapeHtml(tag)}</span>`).join("")}
        <a target="_blank" rel="noopener" href="${escapeHtml(article.source_url)}">查看原文 →</a>
      </div>
      ${related ? `<details><summary>相关报道 ${article.related_sources.length}</summary><ul>${related}</ul></details>` : ""}
    </article>
  `;
}

function renderReport() {
  const report = state.current;
  const articles = report.articles || [];
  const groups = [...new Set(articles.map(article => article.primary_category))].map(category => ({
    category, items: articles.filter(article => article.primary_category === category)
  }));
  $("#volume").textContent = `VOL.${report.report_id.replace(/^(daily|weekly|monthly)-/, "")} · ${articles.length} STORIES · HEAVY TRUCK POLICY`;
  $("#reportTitle").textContent = `政策法规${typeNames[report.report_type]}`;
  $("#reportPeriod").textContent = `${formatDate(report.period_start)} — ${formatDate(report.period_end)} · ${report.report_type.toUpperCase()} · 北京时间`;
  $("#lead").innerHTML = `<small>${report.report_type === "daily" ? "本期摘要" : "本期主线"}</small><h2>${escapeHtml(headline(report))}</h2><p>${escapeHtml(report.summary)}</p>`;
  $("#metrics").innerHTML = `
    <div><strong>${articles.length}</strong><span>条核验信息</span></div>
    <div><strong>${groups.length}</strong><span>主题分类</span></div>
    <div><strong>${articles.filter(article => article.is_highlight).length}</strong><span>重点动态</span></div>
    <div><strong>≈${readMinutes(articles)} min</strong><span>读完本页</span></div>`;
  $("#contents").innerHTML = `
    <div class="contents-head"><strong>本期看点</strong><span>${groups.length} 个主题 · ${articles.length} 篇报道</span></div>
    ${groups.map((group, index) => `<a href="#section-${index + 1}"><b>${String(index + 1).padStart(2, "0")}</b><strong>${escapeHtml(group.category)}</strong><span>${group.items.length}</span></a>`).join("")}`;
  $("#stories").innerHTML = groups.map((group, index) => `
    <section id="section-${index + 1}" class="story-section">
      <header><b>${String(index + 1).padStart(2, "0")}</b><h2>${escapeHtml(group.category)}</h2><small>${escapeHtml(categoryNames[group.category] || "TOPIC")}</small><span>${group.items.length} 篇</span></header>
      ${group.items.map(storyCard).join("")}
    </section>`).join("");
  ["#lead", "#metrics", "#contents", "#stories"].forEach(selector => { $(selector).hidden = !articles.length; });
  $("#empty").hidden = Boolean(articles.length);
}

function render() {
  renderArchive();
  if (state.current) {
    renderReport();
    return;
  }
  $("#volume").textContent = "POLICY INTELLIGENCE";
  $("#reportTitle").textContent = `政策法规${typeNames[state.type]}`;
  $("#reportPeriod").textContent = "暂无报告";
  ["#lead", "#metrics", "#contents", "#stories"].forEach(selector => { $(selector).hidden = true; });
  $("#empty").hidden = false;
}

function selectDefault() {
  const reports = reportsOfType();
  state.current = reports.find(report => report.articles?.length) || reports[0] || null;
  render();
}

$$(".type-tab").forEach(button => button.addEventListener("click", () => {
  $$(".type-tab").forEach(tab => tab.classList.remove("active"));
  button.classList.add("active");
  state.type = button.dataset.type;
  selectDefault();
}));

(async () => {
  try {
    const response = await fetch((window.SITE_CONFIG || {}).dataPath || "data/manifest.json");
    if (!response.ok) throw new Error(String(response.status));
    state.reports = (await response.json()).reports || [];
    selectDefault();
  } catch (error) {
    $("#reportPeriod").textContent = "数据载入失败，请稍后重试";
    $("#empty").hidden = false;
  }
})();
