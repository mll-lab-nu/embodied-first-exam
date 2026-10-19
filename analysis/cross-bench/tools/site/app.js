const DATA = /*DATA*/null;
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const pct = (s, n) => n ? Math.round(100 * s / n) + "%" : "–";
// The report gives counts, k/n, not percentages (user 10-18 night); bars and shading are still drawn by share.
// Importance tags from meta/ratings.json (build.py ratings): 「重点」 for high, a quieter 「次要」 for mid, nothing for low.
const rateTag = f => ({high: `<span class="rtag hi" title="评分标为重点的结论">重点</span>`, mid: `<span class="rtag mid" title="评分标为次要的结论">次要</span>`})[DATA.findings[f]?.rating] || "";
const HAS_HIGH = Object.values(DATA.findings).some(f => f.rating === "high");
// 「只看重点」 on topic pages: hides every finding (and child section) not rated high, keeping a parent whose child is;
// the choice is remembered per viewer (browser storage, which may be unavailable: then it starts off every time).
const ONLY_KEY = "xb-only-high";
const onlyHigh = {get() { try { return localStorage.getItem(ONLY_KEY) === "1"; } catch (e) { return false; } },
                  set(v) { try { localStorage.setItem(ONLY_KEY, v ? "1" : "0"); } catch (e) { /* storage blocked: not remembered */ } }};
function applyOnlyHigh(on) {
  const hi = f => DATA.findings[f]?.rating === "high", keep = f => hi(f) || (DATA.findings[f]?.children || []).some(hi);
  document.querySelectorAll("#main article.finding").forEach(a => { a.hidden = on && !keep(a.id.slice(2));
    a.querySelectorAll("section.sub").forEach(x => { x.hidden = on && !hi(x.id.slice(2)); }); });
  const runs = (sel, item, shown) => document.querySelectorAll(sel).forEach(h => { let el = h.nextElementSibling, any = false;
    while (el && !el.matches(sel)) { if (el.matches(item) && shown(el)) any = true; el = el.nextElementSibling; } h.hidden = on && !any; });
  runs("#main h2.sec[id^='sec-']", "article.finding", el => !el.hidden);
  document.querySelectorAll(".ptoc .ptg").forEach(g => { g.hidden = on && !keep(g.dataset.g); });
  document.querySelectorAll(".ptoc .ptk .pt").forEach(x => { x.hidden = on && !hi(x.dataset.f); });
  runs(".ptoc .pts", ".ptg", el => !el.hidden);
  const none = $("#onlyhi-none"); if (none) none.hidden = !on || !!document.querySelector("#main article.finding:not([hidden])");
}
const MODES = {privileged: "privileged", standard: "standard", "standard-realtime": "realtime"};
const CORE = () => DATA.site.set === "core";   // the core set: its pages leave out the all-set scope notes
const MODE_CLS = {privileged: "m-priv", standard: "m-std", "standard-realtime": "m-rt"};
const CB = DATA.method.codebook;
// Hover / tap notes on terms: the one glossary (meta/codebook.json → glossary_zh), the same one the findings are written with.
const TERMS = Object.fromEntries(Object.entries(CB.glossary_zh).map(([w, d]) => [w, `${w}${w === "standard-realtime" ? "（realtime）" : ""}：${d}`]));
TERMS.realtime = TERMS["standard-realtime"];
const modeTag = m => `<span class="pill mode ${MODE_CLS[m] || ""}"${TERMS[m] ? ` data-tip="${esc(TERMS[m])}"` : ""}>${MODES[m] || esc(m)}</span>`;
const STATUS = {"in-progress": "进行中", held: "暂停", "infra-failed": "基础设施失败", skipped: "按设计不跑", "not-scheduled": "未排"};
const ENDS = [["success", "成功", "--ok"], ["timeout", "超时", "--n1"], ["self-stopped", "自己停下", "--n2"], ["fell", "摔倒", "--n5"], ["episode-over", "局被判负", "--n3"], ["token-budget", "token 上限", "--n4"], ["other-fail", "其他失败", "--c0"]];
const STAGE = {understanding: "理解任务", exploration: "摸清环境", perception: "感知与状态估计", design: "设计方法", execution: "控制执行", verification: "验证", deliverable: "交付", "time-budget": "时间与预算"};
const LOOP = Object.fromEntries(DATA.loop.map(([k, name, color]) => [k, [name, color]]));   // v17 approaches (figs.LOOP)
const topicNo = n => DATA.topics[n - 1]?.name || "";   // entity-page sections carry the topic numbers and names
const agentById2 = name => (DATA.agents.find(a => a.name === name) || {}).id || "";
const CAT_SHORT = {tabletop: "桌面", household: "家居", dexterous: "灵巧", dynamic: "动态", reasoning: "推理", safety: "安全"};
/* audience-switch:internal */
const VCLS = {infra: "基础设施问题", rule: "违规", suspect: "评分侧存疑"};
const REASON = {limits_violation_observed: "超出内存、显存、磁盘或进程数上限", answer_packages: "监控发现装了上游 benchmark 包（含原奖励代码）",
  external_tool_calls: "调用了外部工具（如 Codex 连接器）", provider_filter: "模型服务的内容过滤器中途掐断（Gemini）",
  live_success_but_failed: "现场运行或全部回放都成功，最终判失败（多为事后改了评分条件）", episode_success_but_failed: "这一局本身成功，最终判失败",
  api_fatal: "模型 API 致命错误", transport_cut: "与模型服务的连接中断", gateway_refused: "网关拒绝请求", no_reward: "评分没有产出结果",
  infra_error: "评分报告基础设施错误", grader_error: "评分程序出错", NetworkConnectionError: "网络连接错误", ApiOverloadedError: "模型 API 过载",
  ApiRateLimitError: "模型 API 限流", VerifierTimeoutError: "评分超时"};
/* end */
const OUTCOME = {success: "成功", failure: "失败"};
const causeDesc = c => (CB.cause_zh[c] || [])[1] || "";
const GROUP = {understanding: "理解任务", interface: "接口与约定", perception: "感知", control: "控制与接触", planning: "步骤规划", method: "方法", verification: "验证", time: "时间", metacognition: "自我监控", deliverable: "交付", external: "外部"};
const causeName = c => (CB.cause_zh[c] || [c.replace(/^other:/, "")])[0];
const benchName = b => DATA.benches[b]?.name || b;
const agentById = id => DATA.agents.find(a => a.id === id);

// A topic's findings grouped by section, in reading order (shared by the page and its table of contents).
function topicSecs(t) {
  return (t.sections.length ? t.sections : [""]).map(sec => [sec, t.findings.filter(f => (DATA.findings[f].section || "") === sec || (!t.sections.includes(DATA.findings[f].section || "") && sec === t.sections[t.sections.length - 1]))]).filter(([, fs]) => fs.length);
}
function nav(route) {
  const a = (href, text, extra = "") => `<a href="#${href}" class="${route === href || route.startsWith(href + "~") ? "on" : ""}" ${extra}>${esc(text)}</a>`;
  const group = (label, open, body) => `<details class="navgrp"${open ? " open" : ""}><summary class="navsec">${label}</summary>${body}</details>`;
  let h = `<div class="topbar"><a class="brand" href="#home">${esc(DATA.site.title)}</a><span class="here" id="here"></span>
    <button class="navtoggle" id="navtoggle" aria-expanded="false" aria-controls="tree">目录</button></div>
    <p class="brand-sub">数据截至 ${esc(DATA.site.snapshot)}</p><div class="tree" id="tree">
    <form class="searchbox" id="sform" role="search"><input id="sq" type="search" placeholder="搜索结论、案例${/* audience-switch:internal */ "、问题" + /* end */ ""}…" aria-label="搜索" value="${esc(SEARCH.q)}"></form>`;
  const t = route.startsWith("topic-") && DATA.topics.find(x => "topic-" + x.id === route);
  if (t && t.findings.length) {                       // this page's contents: sections, findings, children (children unfold with the current finding)
    const n = DATA.topics.indexOf(t) + 1;
    h += `<nav class="ptoc" aria-label="本页目录"><div class="navsec">本页 · ${n} ${esc(t.name)}</div>` + topicSecs(t).map(([sec, fs]) => (sec ? `<div class="pts">${esc(sec)}</div>` : "")
      + fs.map(f => { const kids = DATA.findings[f].children || [];
        return `<div class="ptg" data-g="${f}"><a class="pt" href="#f-${f}" data-f="${f}"><b>§${f}</b><span>${esc(DATA.findings[f].title)}${rateTag(f)}</span></a>${kids.length ? `<div class="ptk">${kids.map(c => `<a class="pt" href="#f-${c}" data-f="${c}"><b>§${c}</b><span>${esc(DATA.findings[c].title)}${rateTag(c)}</span></a>`).join("")}</div>` : ""}</div>`; }).join("")).join("") + `</nav>`;
  }
  h += a("home", "首页 · 摘要");
  h += `<div class="navsec">专题</div>` + DATA.topics.map((t, i) => a("topic-" + t.id, `${i + 1} ${t.name}`)).join("");
  h += group("Benchmark", route.startsWith("bench-"), DATA.categories.map(c => `<div class="cat">${esc(c.name)}</div><div class="sub">` + c.benches.map(b => a("bench-" + b, benchName(b))).join("") + `</div>`).join(""));
  const cmp = DATA.topics.find(t => t.id === "compare");   // 三家对比 is topic 6: the Agent list's first entry links there
  h += group("Agent", route.startsWith("agent-"), (cmp ? a("topic-compare", `${DATA.topics.indexOf(cmp) + 1} ${cmp.name}`) : "") + DATA.agents.map(x => a("agent-" + x.id, x.name)).join(""));
  h += `<div class="navsec">数据与证据</div>` + /* audience-switch:internal */ a("issues", `问题清单（${DATA.issues.length}）`) + /* end */ a("cases", `案例库（${Object.keys(DATA.cases).length}）`) + a("method", "数据与方法") /* audience-switch:internal */ + (DATA.samples ? a("samples", "图表样例") : "") /* end */;
  $("#nav").innerHTML = h + "</div>";
  $("#navtoggle").onclick = e => { const o = $("#nav").classList.toggle("open"); e.currentTarget.setAttribute("aria-expanded", o); };
  $("#sform").onsubmit = e => { e.preventDefault(); SEARCH.q = $("#sq").value.trim(); location.hash === "#search" ? route() : (location.hash = "search"); };
}

// Scroll position -> highlighted contents entry (and the phone bar's "you are here").
let SPY = null;
function spy() {
  if (SPY) removeEventListener("scroll", SPY);
  const els = [...document.querySelectorAll("#main article.finding, #main section.sub")];
  if (!els.length || !$(".ptoc")) { SPY = null; if ($("#here")) $("#here").textContent = ""; return; }
  let last = "", tick = false;
  const set = () => { tick = false;
    let cur = els[0]; for (const el of els) { if (el.getBoundingClientRect().top < 140) cur = el; else break; }
    const id = cur.id.slice(2); if (id === last) return; last = id;
    document.querySelectorAll(".ptoc .pt").forEach(x => x.classList.toggle("on", x.dataset.f === id));
    document.querySelectorAll(".ptoc .ptg").forEach(g => g.classList.toggle("open", id === g.dataset.g || id.startsWith(g.dataset.g + ".")));
    $("#here").textContent = `§${id}`;
    const on = $(".ptoc .pt.on"), nv = $("#nav");
    if (on && nv.scrollHeight > nv.clientHeight + 4 && getComputedStyle(nv).position === "sticky") { const r = on.getBoundingClientRect(), b = nv.getBoundingClientRect();
      if (r.top < b.top + 40 || r.bottom > b.bottom - 40) nv.scrollTop += r.top - b.top - nv.clientHeight / 3; } };
  SPY = () => { if (!tick) { tick = true; requestAnimationFrame(set); } };
  addEventListener("scroll", SPY, {passive: true}); set();
}

// Term explanations: the first use of each listed term in a block gets a dotted underline with its definition.
const TERM_RE = new RegExp(Object.keys(TERMS).sort((x, y) => y.length - x.length)
  .map(w => /^[\w-]+$/.test(w) ? `(?<![A-Za-z-])${w}(?![A-Za-z-])` : w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "g");
function markTerms(scope, used = new Set()) {
  if (!scope) return used;
  const skip = "a, .qv, .qbars, .chart, .pill, [data-tip], h1, h2, h3, h4, summary, .figcap, table, .card, .term, .legend, code";
  const walk = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, {acceptNode: n => n.parentElement.closest(skip) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT});
  const nodes = []; while (walk.nextNode()) nodes.push(walk.currentNode);
  for (let node of nodes) {
    TERM_RE.lastIndex = 0; let m;
    while ((m = TERM_RE.exec(node.data))) {
      const w = m[0]; if (used.has(TERMS[w])) continue; used.add(TERMS[w]);
      const rest = node.splitText(m.index), after = rest.splitText(w.length);
      const s = document.createElement("span"); s.className = "term"; s.tabIndex = 0; s.dataset.tip = TERMS[w]; s.textContent = w;
      rest.replaceWith(s); node = after; TERM_RE.lastIndex = 0;
    }
  }
  return used;
}

// A finding body -> its visible part (claim + first figure) and its collapsed parts.
function shape(html) {
  const t = document.createElement("template"); t.innerHTML = html; const R = t.content;
  // a child section with several figures keeps them in reading order (the first one is not lifted out as the main figure)
  const several = !R.querySelector(".claim") && R.querySelectorAll(".fig").length > 1;
  // the main figure, plus every other figure written in the claim part (before 证据): all shown as main figures, in order
  // a claim written with 2+ figures between its bullets keeps them where they are written (user 10-19: §1.1 results, then overlap)
  const cl = R.querySelector(".claim"), inClaim = cl ? [...cl.querySelectorAll(".fig")] : [];
  if (inClaim.length > 1) inClaim.forEach(f => f.classList.add("mainfig"));
  const first = several || inClaim.length > 1 ? null : R.querySelector(".fig");
  const lifted = first ? [first, ...inClaim.filter(f => f !== first)] : [];
  const main = lifted.map(f => { f.classList.add("mainfig"); const h = f.outerHTML; f.remove(); return h; }).join("");
  const claim = R.querySelector(".claim"), parts = [...R.querySelectorAll(".parts > .part")];
  const count = el => { const n = el.querySelectorAll(":scope > ul > li").length, g = el.querySelectorAll(".fig").length; return [n && `${n} 条`, g && `${g} 张图`].filter(Boolean).join(" · "); };
  if (claim) return {vis: claim.outerHTML, fig: main, more: parts.map(p => { const b = p.querySelector(".pb");
    return `<details class="part"><summary><span class="pl">${p.querySelector(".pl").innerHTML}</span><span class="pn">${count(b)}</span></summary><div class="pb">${b.innerHTML}</div></details>`; }).join("")};
  // no labelled parts (child sections): the first bullet stays open, the rest fold into one block named by their lead words
  const ul = [...R.children].find(e => e.tagName === "UL"), lis = ul ? [...ul.children] : [];
  const flat = () => { const d = document.createElement("div"); d.append(R); return d.innerHTML; };
  if (lis.length < 2) return {vis: `<div class="claim">${flat()}</div>`, fig: main, more: ""};
  const lead = li => (li.textContent.match(/^\s*([^：:\s]{1,6})[：:]/) || [])[1];
  const names = [...new Set(lis.slice(1).map(lead).filter(Boolean))];
  const rest = lis.slice(1).map(li => li.outerHTML).join(""); ul.replaceChildren(lis[0]);
  return {vis: `<div class="claim">${flat()}</div>`, fig: main, more: `<details class="part"><summary><span class="pl">${esc(names.join(" · ") || "展开")}</span><span class="pn">${lis.length - 1} 条<!--NC--></span></summary><div class="pb"><ul>${rest}</ul><!--CASES--></div></details>`};
}

// Tap support for the hover notes on terms: a tap shows the note under the word.
document.addEventListener("click", e => { const el = e.target.closest(".term");
  if (!el) return; const r = el.getBoundingClientRect(); tip.textContent = el.dataset.tip; tip.hidden = false;
  tip.style.left = Math.max(8, Math.min(r.left, innerWidth - tip.offsetWidth - 8)) + "px"; tip.style.top = (r.bottom + 6) + "px"; });
addEventListener("scroll", () => { if (!tip.hidden && !matchMedia("(hover: hover)").matches) tip.hidden = true; }, {passive: true});

// Search: every finding (and child section), case, issue, benchmark and agent, matched on plain text in the browser.
// Chinese needs no tokenising: each space-separated term must occur somewhere in the entry (case-insensitive).
const SEARCH = {q: "", index: null};
function searchIndex() {
  if (SEARCH.index) return SEARCH.index;
  const plain = h => String(h || "").replace(/<[^>]+>/g, " ").replace(/&[a-z#0-9]+;/gi, " ").replace(/\s+/g, " ");
  const out = [];
  for (const [id, f] of Object.entries(DATA.findings)) out.push({kind: "结论", href: `#f-${id}`, label: `§${id}`, title: f.title, text: f.text || plain(f.html)});
  for (const [id, c] of Object.entries(DATA.cases)) out.push({kind: "案例", href: `#case-${id}`, label: `${c.agent} · ${benchName(c.bench)}`, title: c.title,
    text: [taskName(c), c.mode, c.approach, c.story, c.evidence, (c.decisive || {}).what, causeName(c.primary || "")].map(plain).join(" ")});
  /* audience-switch:internal */
  for (const i of DATA.issues) out.push({kind: "问题", href: `#issue-${i.id}`, label: `问题 ${i.id.slice(1)}`, title: plain(i.what).slice(0, 80), text: plain(i.what) + " " + plain(i.impact)});
  /* end */
  for (const [id, b] of Object.entries(DATA.benches)) out.push({kind: "Benchmark", href: `#bench-${id}`, label: id, title: b.name, text: plain(b.desc) + " " + plain(b.note)});
  for (const x of DATA.agents) out.push({kind: "Agent", href: `#agent-${x.id}`, label: x.harness, title: x.name, text: Object.values(x.notes || {}).map(plain).join(" ")});
  return SEARCH.index = out;
}

const taskName = c => String(c.task || "").replace(new RegExp("^" + c.bench + "[-_]"), "").replace(/-i\d+$/, "");
// A trial as the monitor names it, "run id · host · trial name" (build.case_record): under every video and thumbnail
// and on the case page header. Plain selectable text, so on a card it sits between the card's two links.
const trialRef = c => c.ref ? `<code class="tref">${esc(c.ref)}</code>` : "";
function caseCard(id, n, label = "") {
  const c = DATA.cases[id]; if (!c) return "";
  const img = c.media.poster ? `<img class="thumb" src="${c.media.poster}" alt="" loading="lazy">` : `<span class="thumb ph">没有回放画面</span>`;
  const ok = c.outcome === "success";
  return `<div class="card${c.key_case ? " key" : ""}"${c.media.video ? ` data-video="${c.media.video}"` : ""}><a class="thumbw" href="#case-${id}" tabindex="-1" aria-hidden="true">${img}${c.media.video ? `<span class="vmark" title="有评分回放视频，悬停播放">▶ 视频</span>` : ""}</a>${trialRef(c)}
    <a class="body" href="#case-${id}"><span class="ctop"><span class="pill out ${ok ? "ok" : "no"}">${OUTCOME[c.outcome]}</span>${c.key_case ? `<span class="pill key">精选</span>` : ""}${n ? `<span class="num-badge">[${n}]</span>` : ""}</span>
    ${label ? `<b class="why" title="${esc(label)}">${esc(label)}</b>` : ""}<span class="ttl">${esc(c.title)}</span>
    <span class="cmeta"><span>${esc(c.agent)} · ${esc(benchName(c.bench))} · ${esc(taskName(c))}</span>${modeTag(c.mode)}</span></a></div>`;
}
// Case cards. f (optional): the finding they belong to, whose `nums` (or, without them, its case order) give the mark
// numbers and `labels` say what each case shows (the card's bold lead line). A case with no mark gets no number.
const cases = (ids, numbered, f) => { if (!ids.length) return "";
  const num = (c, i) => !numbered ? 0 : !f ? i + 1 : f.nums ? f.nums[c] || 0 : f.cases.indexOf(c) + 1, lab = c => (f && f.labels && f.labels[c]) || "";
  const card = (c, i) => caseCard(c, num(c, i), lab(c));
  return ids.length <= 9 || !numbered ? `<div class="grid">${ids.map(card).join("")}</div>`
    : `<div class="grid">${ids.slice(0, 9).map(card).join("")}</div><details class="more"><summary>另外 ${ids.length - 9} 个案例</summary><div class="grid">${ids.slice(9).map((c, i) => card(c, i + 9)).join("")}</div></details>`; };
// A finding's (or child's) cases in two parts, so no case shows twice: `vids`, up to 3 cases that have a replay (the
// video strip), and `rest`, every other case (the cards under 其他案例; under 案例 when no case has a video). Strip
// order: the finding's starred cases (a child also takes its parent's), then failures first on the failure topics,
// then the order cited.
const FAIL_FIRST = new Set(["failures", "improve"]);
function caseParts(f) {
  const star = new Set([...(f.star || []), ...((DATA.findings[f.parent] || {}).star || [])]), ff = FAIL_FIRST.has(f.topic);
  const rank = c => (star.has(c) ? 0 : 2) + (ff && DATA.cases[c].outcome !== "failure" ? 1 : 0);
  const vids = f.cases.filter(c => DATA.cases[c]?.media.video).map((c, i) => [rank(c), i, c]).sort((a, b) => a[0] - b[0] || a[1] - b[1]).slice(0, 12).map(x => x[2]);   // every video case plays (user 10-19)
  return {vids, rest: f.cases.filter(c => !vids.includes(c))};
}
const restCards = (f, p, cls = "grid") => p.rest.length ? `${p.vids.length ? "" : '<h4 class="subsh">案例</h4>'}${cases(p.rest, true, f).replace('class="grid"', `class="${cls}"`)}` : "";
// The video strip (caseParts vids) as plain players (nothing loads before play); each: the card's lead claim, the
// trial name, a link to the case.
function videoStrip(f, ids) {
  if (!ids.length) return "";
  // a label that starts with 〔组名〕 puts its card under that sub-heading (groups in the order first cited)
  const full = id => (f.labels && f.labels[id]) || "", grp = id => (full(id).match(/^〔([^〕]+)〕/) || [])[1] || "";
  const fig = id => { const c = DATA.cases[id], lab = full(id).replace(/^〔[^〕]+〕/, "");
    return `<figure class="vcase"><video controls muted preload="none" playsinline${c.media.poster ? ` poster="${c.media.poster}"` : ""} src="${c.media.video}"></video>
      <figcaption>${lab ? `<b class="why" title="${esc(lab)}">${esc(lab)}</b>` : ""}${trialRef(c)}<a class="vlink" href="#case-${id}">看案例</a></figcaption></figure>`; };
  const groups = [...new Set(ids.map(grp))];
  const body = groups.length === 1 && !groups[0] ? `<div class="vgrid">${ids.map(fig).join("")}</div>`
    : groups.map(g => `${g ? `<h5 class="vgroup">${esc(g)}</h5>` : ""}<div class="vgrid">${ids.filter(id => grp(id) === g).map(fig).join("")}</div>`).join("");
  return `<div class="vstrip"><h4 class="subsh">案例</h4>${body}</div>`;
}
const topicName = f => DATA.topics.find(t => t.id === DATA.findings[f].topic)?.name;
const fItem = (f, extra = "") => `<li><a class="fid" href="#f-${f}">§${f}</a><span>${esc(DATA.findings[f].title)}${rateTag(f)}${extra}</span></li>`;
const findingLinks = ids => ids.length ? `<ul class="flist">${ids.filter(f => DATA.findings[f]).map(f => fItem(f, ` <span class="pill">${esc(topicName(f))}</span>`)).join("")}</ul>` : `<p class="note">暂无。</p>`;
const keyPill = f => DATA.findings[f]?.top ? `<span class="pill key" title="首页关键发现之一">关键发现</span>` : "";
const statusPill = s => s === "recheck" ? `<span class="pill warn">待复核</span>` : s === "retired" ? `<span class="pill">已作废</span>` : "";

function endBar(endings) {
  const n = Object.values(endings).reduce((a, b) => a + b, 0) || 1;
  const segs = ENDS.filter(([k]) => endings[k]).map(([k, label, v]) => `<i style="width:${100 * endings[k] / n}%;background:var(${v})" title="${label} ${endings[k]}/${n}"></i>`).join("");
  return `<div class="bar" role="img" aria-label="结束方式分布">${segs}</div>`;
}
const endLegend = () => `<div class="legend">${ENDS.map(([, l, v]) => `<span><i style="background:var(${v})"></i>${l}</span>`).join("")}</div>`;
const rate = (s, n) => n ? `<div class="rate"><span>${s}/${n}</span><span class="mini"><i style="width:${100 * s / n}%"></i></span></div>` : `<span class="meta">–</span>`;

const ACT = [["shell", "命令与脚本", "--l3"], ["write", "写文件", "--l1"], ["read", "读文件", "--l2"], ["image", "看图", "--c7"]];
function activityStrip(a) {
  if (!a || !a.kinds) return "";
  const B = a.kinds.shell.length, sum = i => ACT.reduce((s, [k]) => s + a.kinds[k][i], 0);
  const top = Math.max(1, ...Array.from({length: B}, (_, i) => sum(i)));
  const at = m => `${Math.min(100, 100 * m / a.span).toFixed(1)}%`, mm = m => `${Math.floor(m)}:${String(Math.round(m % 1 * 60)).padStart(2, "0")}`;
  const cols = Array.from({length: B}, (_, i) => `<span class="col" data-tip="${mm(i * a.span / B)}–${mm((i + 1) * a.span / B)}：${ACT.filter(([k]) => a.kinds[k][i]).map(([k, l]) => `${l} ${a.kinds[k][i]}`).join("，") || "无调用"}">${ACT.map(([k, , c]) => a.kinds[k][i] ? `<i style="height:${100 * a.kinds[k][i] / top}%;background:var(${c})"></i>` : "").join("")}</span>`).join("");
  const ms = [...a.marks].sort((x, y) => x[1] - y[1]);
  const groups = [];                                   // marks closer than 3% of the span share one line and one badge
  ms.forEach(([l, t], i) => { const g = groups[groups.length - 1]; if (g && (t - g.t) / a.span < 0.03) g.ids.push(i); else groups.push({t, ids: [i]}); });
  const marks = groups.map(g => { const lab = g.ids.length > 1 ? `${g.ids[0] + 1}–${g.ids[g.ids.length - 1] + 1}` : `${g.ids[0] + 1}`;
    return `<span class="mk" style="left:${at(g.t)}" data-tip="${g.ids.map(i => `${i + 1} ${ms[i][0]} ${mm(ms[i][1])}`).join("；")}"><span class="mkn">${lab}</span></span>`; }).join("");
  const keyList = ms.length ? `<ol class="mklist">${ms.map(([l, t], i) => `<li><b>${i + 1}</b> ${esc(l)} <span class="mono">${mm(t)}</span></li>`).join("")}</ol>` : "";
  const clk = a.clock.map(t => `<span class="clk" style="left:${at(t)}" data-tip="看时钟 ${mm(t)}"></span>`).join("");
  const lim = a.cutoff && a.cutoff < a.span ? `<span class="lim" style="left:${at(a.cutoff)}" data-tip="时限 ${mm(a.cutoff)}"></span>` : "";
  return `<div class="legend">${ACT.map(([, l, c]) => `<span><i style="background:var(${c})"></i>${l}</span>`).join("")}<span><i style="background:var(--ink-2);width:3px"></i>看时钟</span></div>
    <div class="act" role="img" aria-label="工具调用随时间的分布"><div class="cols">${cols}</div>${lim}${marks}${clk}</div>
    <div class="act-ax"><span>0</span><span>${mm(a.span / 2)}</span><span>${mm(a.span)}${a.cutoff ? `（时限 ${mm(a.cutoff)}）` : ""}</span></div>${keyList}
    <p class="note">每根柱是一段时间里的工具调用数；带编号的竖线是分析标出的时刻。${a.approx ? "这个 harness 的步骤没有时间戳，时刻按请求时间近似。" : ""}</p>`;
}

// Progress staircase (progress label): level 0–5 over session time on the activity strip's time axis, a dot per
// milestone (level and its 'what' on hover), a line at the progress-2 no-return event in its kind's colour (none drawn
// for kind none), the end type at the end of the line; the list below says the same without hovering.
function progressStair(p, a, outcome) {
  if (!p || !p.ms) return "";
  const P = CB.progress_zh, lv = l => `第 ${l} 级·${P.level[l][0]}`, mm = m => `${Math.floor(m)}:${String(Math.round(m % 1 * 60)).padStart(2, "0")}`;
  const span = (a && a.span) || Math.max(p.cutoff || 0, p.end || 0, ...p.ms.map(m => m[0]), 1);
  const X = m => Math.min(100, 100 * m / span), Y = l => 92 - 17 * l, end = Math.min(p.end || span, span);
  let d = `M0,${Y(0)}`, cur = 0;
  for (const [t, l] of p.ms) { d += ` L${X(t).toFixed(2)},${Y(cur)} L${X(t).toFixed(2)},${Y(l)}`; cur = l; }
  d += ` L${X(end).toFixed(2)},${Y(cur)}`;
  const area = `${d} L${X(end).toFixed(2)},100 L0,100 Z`;
  const name = (t, k) => (t[k] || [k])[0];
  const nr = p.nr && p.nr !== "none" && p.nr_t != null;
  const nrSay = nr ? `${name(P.no_return, p.nr)}：${p.nr_what}（${name(P.noticed, p.nr_noticed)}；之后：${name(P.nr_after, p.nr_after)}`
    + (p.nr_after === "kept-trying" && p.wasted != null ? `，约 ${Math.round(p.wasted)} 分钟` : "") + "）" : "";
  const endName = p.end_kind ? name(P.end, p.end_kind) : "", endSay = endName ? `${endName}${p.end_what ? "：" + p.end_what : ""}` : "";
  const dots = p.ms.map(([t, l, w]) => `<span class="sdot" style="left:${X(t).toFixed(2)}%;top:${Y(l)}%;background:var(--lv${l})" data-tip="${mm(t)} · ${esc(lv(l))}：${esc(w)}"></span>`).join("");
  const crit = nr ? `<span class="scrit${X(p.nr_t) > 60 ? " r" : ""}" style="left:${X(p.nr_t).toFixed(2)}%;border-color:var(${p.nr_color})" data-tip="${esc(`不可挽回点 ${mm(p.nr_t)} · ${nrSay}`)}"><span class="scritn">${esc(name(P.no_return, p.nr))}</span></span>` : "";
  const fin = endName ? `<span class="send${cur >= 4 ? " lo" : ""}${X(end) < 30 ? " l" : ""}" style="left:${X(end).toFixed(2)}%;top:${Y(cur)}%" data-tip="${esc(`结束 ${mm(end)} · ${endSay}`)}"><span class="sendn"><i style="background:var(${p.end_color})"></i>${esc(endName)}</span></span>` : "";
  const lim = p.cutoff && p.cutoff < span ? `<span class="lim" style="left:${X(p.cutoff)}%" data-tip="时限 ${mm(p.cutoff)}"></span>` : "";
  const yl = [0, 1, 2, 3, 4, 5].map(l => `<span style="top:${Y(l)}%" data-tip="${esc(lv(l))}：${esc(P.level[l][1])}">${l}</span>`).join("");
  const list = p.ms.map(([t, l, w]) => `<li><i style="background:var(--lv${l})"></i><span class="mono">${mm(t)}</span><span>${esc(lv(l))}：${esc(w)}</span></li>`)
    .concat(nr ? [`<li class="scl"><i style="background:var(${p.nr_color})"></i><span class="mono">${mm(p.nr_t)}</span><span>不可挽回点·${esc(nrSay)}</span></li>`] : [])
    .concat(endName ? [`<li class="sel"><i style="background:var(${p.end_color})"></i><span class="mono">${mm(end)}</span><span>结束·${esc(endSay)}</span></li>`] : []);
  return `<p class="figcap">进展等级随时间</p><div class="stair" role="img" aria-label="进展等级随时间"><div class="syl">${yl}</div><div class="sbox">`
    + `<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path class="sarea" d="${area}"/><path class="sline" d="${d}" vector-effect="non-scaling-stroke"/></svg>${lim}${crit}${dots}${fin}</div></div>`
    + `<div class="act-ax stair-ax"><span>0</span><span>${mm(span / 2)}</span><span>${mm(span)}</span></div><ol class="slist">${list.join("")}</ol>`
    + `<p class="note">纵轴是进展等级（0–5，分析认定；${p.basis === "test-runs" ? "这里按 agent 自己的测试运行算" : "这里按现场这一局算"}）；点 = 第一次到达这一级`
    + (nr ? "；彩色竖线 = 不可挽回点（此后 reset 也补不回、不可能再通过的事件）" : outcome === "failure" && p.nr === "none" ? "；这次失败没有不可挽回点（reset 或重试还能补救的挫折不算）" : "")
    + (endName ? "；线末的标签 = 结束方式" : "") + `${a && a.span ? "；横轴与上面的调用图相同" : ""}。</p>`;
}

// fig:venn (figs.fig_venn): a click, or Enter / Space on a focused region, lists that region's tasks under the diagrams,
// grouped by benchmark, each with its mode.
function vennShow(el) {
  const box = el.closest(".venn"), out = box && box.querySelector(".vlist"); if (!out) return;
  let items = []; try { items = JSON.parse(el.dataset.tasks || "[]"); } catch (e) { items = []; }
  box.querySelectorAll(".on[data-tasks]").forEach(x => x.classList.remove("on")); el.classList.add("on");
  const by = {}; for (const [b, t, m] of items) (by[b] = by[b] || []).push([t, m]);
  out.innerHTML = `<p class="vlh">${esc(el.dataset.title)}：${items.length} 项</p>` + (items.length
    ? `<dl class="vtasks">${Object.entries(by).map(([b, ts]) => `<dt>${esc(b)}（${ts.length}）</dt><dd>${ts.map(([t, m]) => `<span class="vt">${esc(t)} ${modeTag(m)}</span>`).join("")}</dd>`).join("")}</dl>`
    : `<p class="note">没有任务。</p>`);
}
document.addEventListener("click", e => { const el = e.target.closest(".venn [data-tasks]"); if (el) vennShow(el); });
document.addEventListener("keydown", e => { const el = e.target.closest && e.target.closest(".venn [data-tasks]");
  if (el && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); vennShow(el); } });

// fig:waffle (waffle.py): a click on a square lists its group's tasks (the .wgrp around it) under the panels, grouped
// by benchmark, and dims the other squares of that panel; the same group again clears it.
function wafShow(grp) {
  const fig = grp.closest(".waffle"), out = fig && fig.querySelector(".wlist"); if (!out) return;
  const off = grp.classList.contains("hit");
  fig.querySelectorAll(".wpanel").forEach(p => p.classList.remove("sel"));
  fig.querySelectorAll(".wgrp").forEach(g => g.classList.remove("hit"));
  if (off) { out.innerHTML = ""; return; }
  grp.classList.add("hit"); grp.closest(".wpanel").classList.add("sel");
  let items = []; try { items = JSON.parse(grp.dataset.tasks || "[]"); } catch (e) { items = []; }
  const by = {}; for (const [b, t] of items) (by[b] = by[b] || []).push(t);
  out.innerHTML = `<p class="wlh">${esc(grp.dataset.title)}：${items.length} 项</p>` + (items.length
    ? `<dl class="wtasks">${Object.entries(by).map(([b, ts]) => `<dt>${esc(b)}（${ts.length}）</dt><dd>${ts.map(t => `<span class="wt">${esc(t)}</span>`).join("")}</dd>`).join("")}</dl>`
    : `<p class="note">没有任务。</p>`);
}
document.addEventListener("click", e => { const g = e.target.closest(".waffle .wgrp"); if (g) wafShow(g); });

// fig:venn dressing, once an SVG is laid out (venn.py leaves room for both): a rounded pill under each region number
// (PILL_PX, PILL_H) and a dot in the agent's colour before each set label (DOT_W). Venn figures arrive with the page's
// HTML on route, so new ones are picked up by a MutationObserver; one still hidden (no text length yet) waits for view.
const SVGNS = "http://www.w3.org/2000/svg", vennIO = "IntersectionObserver" in window
  ? new IntersectionObserver(es => es.forEach(e => e.isIntersecting && vennDress(e.target))) : null;
function svgEl(tag, cls, at, before) {
  const e = document.createElementNS(SVGNS, tag); e.setAttribute("class", cls);
  for (const [k, v] of Object.entries(at)) e.setAttribute(k, typeof v === "number" ? v.toFixed(1) : v);
  before.before(e); return e;
}
function vennDress(svg) {
  if (svg.dataset.dressed) return;
  const labs = [...svg.querySelectorAll(".vlab")], outs = svg.querySelectorAll(".vo");
  if (labs.length && !labs[0].getComputedTextLength()) { vennIO && vennIO.observe(svg); return; }
  svg.dataset.dressed = 1; vennIO && vennIO.unobserve(svg);
  svg.querySelectorAll(".vnum").forEach(t => {
    const w = t.getComputedTextLength() + 10, h = 17, x = +t.getAttribute("x"), y = +t.getAttribute("y");
    svgEl("rect", "vpill" + (t.classList.contains("vout") ? " vout" : ""), {x: x - w / 2, y: y - h / 2, width: w, height: h, rx: h / 2}, t);
  });
  labs.forEach((t, i) => {
    const a = t.getAttribute("text-anchor"), x = +t.getAttribute("x"), w = t.getComputedTextLength(), D = 10;
    const x0 = a === "start" ? x : a === "end" ? x - w - D : x - (w + D) / 2;      // where the dot + text begins
    t.setAttribute("x", (x0 + D).toFixed(1)); t.setAttribute("text-anchor", "start");
    svgEl("circle", "vkey", {cx: x0 + 3.5, cy: t.getAttribute("y"), r: 3.5,
      style: ((outs[i] && outs[i].getAttribute("style")) || "").replace("stroke", "fill")}, t);
  });
}
const vennDressAll = () => { if (document.fonts && document.fonts.status === "loading") return;   // fonts.ready calls again
  document.querySelectorAll(".venn svg:not([data-dressed])").forEach(vennDress); };
new MutationObserver(() => requestAnimationFrame(vennDressAll)).observe(document.body, {childList: true, subtree: true});
if (document.fonts && document.fonts.ready) document.fonts.ready.then(vennDressAll);

// Case cards play their replay on hover (the same file the case page uses; nothing extra to download until hovered).
document.addEventListener("mouseover", e => {
  const card = e.target.closest(".card[data-video]"); if (!card || card.querySelector("video")) return;
  const img = card.querySelector(".thumb"); if (!img) return;
  const v = document.createElement("video"); v.className = "thumb"; v.src = card.dataset.video; v.muted = true; v.loop = true; v.playsInline = true; v.autoplay = true;
  img.replaceWith(v); card.addEventListener("mouseleave", () => { v.pause(); v.replaceWith(img); }, {once: true});
});
const tip = document.createElement("div"); tip.id = "tip"; tip.hidden = true; document.body.appendChild(tip);
document.addEventListener("mouseover", e => { const el = e.target.closest("[data-tip]"); if (!el) { tip.hidden = true; return; } tip.textContent = el.dataset.tip; tip.hidden = false; });
document.addEventListener("mousemove", e => { if (tip.hidden) return; const w = tip.offsetWidth, x = Math.min(e.clientX + 14, innerWidth - w - 8); tip.style.left = Math.max(8, x) + "px"; tip.style.top = (e.clientY + 16) + "px"; });

// Entity pages (agent, benchmark): numbered sections [num, name, html] ("" = no number) under a one-line contents row.
function entSections(route, secs) {
  const key = (n, i) => `es-${n || "x" + i}`;
  setTimeout(() => document.querySelectorAll("a[data-sec]").forEach(a => a.onclick = e => { e.preventDefault(); document.getElementById(a.dataset.sec)?.scrollIntoView(); }));
  return `<nav class="secrow" aria-label="本页目录">${secs.map(([n, name], i) => `<a href="#${route}" data-sec="${key(n, i)}">${n ? `<b>${n}</b>` : ""}${esc(name)}</a>`).join("")}</nav>`
    + secs.map(([n, name, body], i) => `<section class="esec" id="${key(n, i)}"><h2 class="esec-h">${n ? `<span class="num">${n}</span>` : ""}${esc(name)}</h2>${body}</section>`).join("");
}

/* audience-switch:internal */
function issueList(ids) {
  return `<div class="issues">${ids.map(id => DATA.issues.find(i => i.id === id)).filter(Boolean).map(i => `<div class="issue" id="issue-${i.id}">
    <div class="ih"><span class="fidtag">问题 ${i.id.slice(1)}</span><span class="pill warn">${esc(i.type)}</span>${i.bench.map(b => b === "suite" ? `<span class="pill">整个套件</span>` : `<a class="pill" href="#bench-${b}">${esc(benchName(b))}</a>`).join("")}<span class="pill">${esc(i.status)}</span></div>
    <p>${i.what}</p>${i.impact ? `<p class="note">影响：${i.impact}</p>` : ""}
    <p class="note">${i.findings.length ? `相关结论：${i.findings.map(f => `<a class="fid" href="#f-${f}">§${f}</a>`).join("、")}` : ""}${i.cases.length ? `　案例：${i.cases.map((c, n) => `<a class="cref" href="#case-${c}" data-tip="${esc(DATA.cases[c]?.title || "")}">${n + 1}</a>`).join("")}` : ""}</p></div>`).join("")}</div>`;
}
/* end */

// Home summary: one card per block of findings/_summary.md, with the chart meta/site.json picks for it (built in build.py).
const summaryBlocks = blocks => `<section class="summary">${blocks.map((b, i) => `<article class="sblock">${b.name ? `<header class="shd"><span class="sn">${i + 1}</span><h2>${esc(b.name)}</h2></header>` : ""}
  <div class="sbody">${b.html}</div>${b.fig ? `<figure class="sfig">${b.fig}${DATA.findings[b.from] ? `<figcaption class="src">详见 <a href="#f-${b.from}">§${b.from} ${esc(DATA.findings[b.from].title)}</a>${rateTag(b.from)}</figcaption>` : ""}</figure>` : ""}</article>`).join("")}</section>`;

const pages = {
  home() {
    const s = DATA.site;
    let h = `<header class="mast"><h1>${esc(s.title)}</h1><p class="meta">数据截至 ${esc(s.snapshot)} · ${esc(s.sets[s.set].name)} · ${s.n_valid.toLocaleString()} 个有效 <span class="term" tabindex="0" data-tip="${esc(TERMS.trial)}">trial</span>（共 ${s.n_trials.toLocaleString()}） · ${s.n_reviews} 条分析记录（深读 ${s.n_deep}） · ${s.n_cases} 个案例 · 成功数取自评测看板的全量结果${s.perf_time ? `（${esc(s.perf_time)}）` : ""}</p></header>`;
    if (s.set_note) h += `<section class="setnote">${s.set_note}</section>`;   // all build: the text is written on the core set
    if (s.interim) h += `<p class="note">中间版：${esc(s.sample_note)}</p>`;
    h += DATA.summary.length ? summaryBlocks(DATA.summary) : `<p class="lead">第一轮分析进行中，结论会随分析逐步补上。</p>`;
    h += `<section class="hsec"><h2>关键发现</h2>` + (DATA.top.length ? `<ol class="toplist">${DATA.top.filter(f => DATA.findings[f]).map(f => `<li><a href="#f-${f}"><b class="fid">§${f}</b><span class="tt">${esc(DATA.findings[f].title)}${rateTag(f)}</span><span class="pill">${esc(topicName(f))}</span>${statusPill(DATA.findings[f].status)}</a></li>`).join("")}</ol>` : `<div class="empty">还没有定稿的 finding。</div>`) + `</section>`;
    h += `<section class="hsec"><h2>专题</h2><div class="idx">` + DATA.topics.map((t, i) => `<a class="item" href="#topic-${t.id}"><b>${i + 1} ${esc(t.name)}</b> <span class="pill">${t.findings.length}</span><span>${esc(t.question)}</span></a>`).join("") + `</div></section>`;
    /* audience-switch:internal */
    h += `<details class="hmore"><summary>数据状态：各 agent 跑了多少评测项</summary>${CORE() ? "" : `<p class="note">非 Luna 的 agent 只跑 Luna 没过的评测项，Luna 已过的评测项记为「按设计不跑」，不算缺失。</p>`}<div class="scroll"><table class="t"><tr><th>Agent</th><th>Harness</th><th class="num">完成</th><th class="num">进行中</th><th class="num">暂停</th><th class="num">未排</th><th class="num">按设计不跑</th></tr>`;
    for (const x of DATA.agents) h += `<tr><td><a href="#agent-${x.id}">${esc(x.name)}</a></td><td>${esc(x.harness)}</td>` + ["done", "in-progress", "held", "not-scheduled", "skipped"].map(k => `<td class="num">${(x.status[k] || 0).toLocaleString()}</td>`).join("") + `</tr>`;
    h += `</table></div></details>`;
    /* end */
    h += `<details class="hmore"><summary>全部 Benchmark 与 Agent</summary><div class="idx">` + DATA.categories.map(c => `<div><b>${esc(c.name)}</b><div class="chips">${c.benches.map(b => `<a class="pill" href="#bench-${b}">${esc(benchName(b))}</a>`).join("")}</div></div>`).join("") + `</div>`;
    h += `<div class="chips">${DATA.agents.map(x => `<a class="pill" href="#agent-${x.id}">${esc(x.name)}</a>`).join("")}<a class="pill acc" href="#cases">案例库</a><a class="pill acc" href="#method">数据与方法</a></div></details>`;
    return h;
  },
  topic(id) {
    const t = DATA.topics.find(x => x.id === id); if (!t) return pages.home();
    let h = `<div class="crumb">专题 ${DATA.topics.indexOf(t) + 1}</div><h1>${esc(t.name)}</h1><p class="lead">${esc(t.question)}</p>`;
    if (HAS_HIGH && t.findings.length) {                                       // the 只看重点 toggle (applyOnlyHigh), wired after the page is drawn
      h += `<label class="onlyhi"><input type="checkbox" id="onlyhi"> 只看重点</label><p class="note" id="onlyhi-none" hidden>这个专题没有标为重点的结论。</p>`;
      setTimeout(() => { const box = $("#onlyhi"); if (!box) return; box.checked = onlyHigh.get(); applyOnlyHigh(box.checked);
        box.onchange = () => { onlyHigh.set(box.checked); applyOnlyHigh(box.checked); }; });
    }
    if (id === "outcomes") h += pages._results();
    /* audience-switch:internal */ if (id === "validity" && DATA.issues.length) h += `<p class="note">需要 benchmark 方核对的问题汇总在 <a href="#issues">问题清单</a>（${DATA.issues.length} 项）。</p>`; /* end */
    if (!t.findings.length) return h + `<div class="empty">这个专题的 finding 还在整理。</div>`;
    const secs = topicSecs(t), order = secs.flatMap(([, fs]) => fs), ti = DATA.topics.indexOf(t);
    // 上一节 / 下一节: the neighbouring finding, or the neighbouring topic at either end
    const step = (f, d) => { const j = order.indexOf(f) + d;
      if (order[j]) return `<a class="pn-${d < 0 ? "prev" : "next"}" href="#f-${order[j]}"><small>${d < 0 ? "上一节" : "下一节"}</small><span>§${order[j]} ${esc(DATA.findings[order[j]].title)}</span></a>`;
      const u = DATA.topics[ti + d]; return u ? `<a class="pn-${d < 0 ? "prev" : "next"}" href="#topic-${u.id}"><small>${d < 0 ? "上一个专题" : "下一个专题"}</small><span>${ti + d + 1} ${esc(u.name)}</span></a>` : `<span></span>`; };
    secs.forEach(([sec, fs], si) => {
      if (sec && secs.length > 1) h += `<h2 class="sec" id="sec-${si + 1}">${esc(sec)}</h2>`;
      for (const f of fs) {
        const x = DATA.findings[f], b = shape(x.html);
        const subs = (x.children || []).map(c => { const y = DATA.findings[c], s = shape(y.html), p = caseParts(y), cs = restCards(y, p, "grid sm");
          const vs = videoStrip(y, p.vids);   // above the cards, outside the fold that holds them
          const more = s.more.includes("<!--CASES-->") ? vs + s.more.replace("<!--NC-->", p.rest.length ? ` · ${p.rest.length} 个案例` : "").replace("<!--CASES-->", cs) : s.more + vs + cs;
          return `<section class="sub" id="f-${c}"><div class="shead"><a class="fid" href="#f-${c}">§${c}</a><h4 class="stitle">${esc(y.title)}${rateTag(c)}</h4></div><div class="prose svis">${s.vis}${s.fig}</div>${more}</section>`; }).join("");
        h += `<article class="finding" id="f-${f}"><div class="fhead"><a class="fid" href="#f-${f}">§${f}</a>${keyPill(f)}${statusPill(x.status)}</div><h3 class="ftitle">${esc(x.title)}${rateTag(f)}</h3>
          <div class="prose fvis">${b.vis}${b.fig}</div>${b.more ? `<div class="parts prose">${b.more.replace(/<!--NC-->|<!--CASES-->/g, "")}</div>` : ""}
          ${subs ? `<div class="subs"><p class="subsh">分 ${x.children.length} 节</p>${subs}</div>` : ""}${x.cases.length ? `<div class="fcases">${(p => videoStrip(x, p.vids) + restCards(x, p))(caseParts(x))}</div>` : ""}
          <nav class="pnav" aria-label="上一节与下一节">${step(f, -1)}${step(f, 1)}</nav></article>`;
      }
    });
    setTimeout(() => document.querySelectorAll("#main article.finding").forEach(a => {
      const used = markTerms(a.querySelector(".fvis")); a.querySelectorAll(".svis").forEach(s => markTerms(s, used));
      a.querySelectorAll("details .pb").forEach(p => markTerms(p)); }));
    return h;
  },
  bench(id) {
    const b = DATA.benches[id]; if (!b) return pages.home();
    const cat = DATA.categories.find(c => c.id === b.cat);
    const F = b.facts || {};
    let h = `<div class="crumb">Benchmark · ${esc(cat.name)}</div><h1>${esc(b.name)}</h1><p class="lead">${esc(b.desc)}</p>
      <div class="chips facts"><span class="pill">${b.tasks} 个任务</span><span class="pill">${(F.trials || 0).toLocaleString()} 个有效 trial</span>${b.modes.map(m => `${modeTag(m)}${F.cutoff?.[m] ? `<span class="pill">时限 ${F.cutoff[m]} min</span>` : ""}`).join("")}${(F.robots || []).map(r => `<span class="pill">${esc(r)}</span>`).join("")}${(F.sim || []).map(x => `<span class="pill">${esc(x)}</span>`).join("")}</div>
      ${b.note ? `<div class="prose ebody esum">${b.note}</div>` : ""}`;
    let res = `<p class="note">每格为成功数 / 评过分的评测项数（评测看板的全量结果：每个 agent 每个评测项取最新一次合规运行）。${CORE() ? "" : "非 Luna 的 agent 只跑 Luna 没过的评测项，比例不能和 Luna 的直接比较。"}</p><div class="scroll"><table class="t"><tr><th>Agent</th>${b.modes.map(m => `<th>${modeTag(m)}</th>`).join("")}</tr>`;
    for (const r of b.rows) {
      res += `<tr><td><a href="#agent-${r.agent_id}">${esc(r.agent)}</a></td>` + b.modes.map(m => {
        const c = r.cells[m]; if (!c) return `<td class="meta">–</td>`;
        const other = Object.entries(c.other || {}).filter(([k]) => k !== "skipped").map(([k, v]) => `<span class="pill ${k === "in-progress" || k === "held" ? "warn" : ""}">${STATUS[k]} ${v}</span>`).join(" ");
        return `<td>${rate(c.s, c.n)}${other ? `<div class="chips">${other}</div>` : ""}</td>`;
      }).join("") + `</tr>`;
    }
    const secs = [["1", topicNo(1), res + `</table></div>`]];
    if (b.examples.length) secs.push(["2", topicNo(2), `<p class="note">分析过的 ${b.examples.length} 个 trial 里，每一步动作由谁决定（分类见 <a class="fid" href="#f-2.1">§2.1</a>）。分析是随机抽样，图是这批 trial 的构成，不是成功率。</p>${b.methods}`
      + `<details class="more examples-box"><summary>做法一览：${b.examples.length} 个分析过的 trial，每行一句话说明怎么做的</summary><div class="scroll"><table class="t examples"><tr><th>模式</th><th>Agent</th><th>结果</th><th>方式</th><th>任务与做法</th><th>案例</th></tr>${b.examples.map(r => {
        const c = r.case && DATA.cases[r.case];
        const L = LOOP[r.loop] || [r.loop, "--c0"];
        return `<tr><td>${modeTag(r.mode)}</td><td class="nowrap"><a href="#agent-${agentById2(r.agent)}">${esc(r.agent)}</a></td><td><span class="pill ${r.ok ? "ok" : "no"}">${r.ok ? "成功" : "失败"}</span></td><td class="nowrap"><span class="dot" style="background:var(${L[1]})"></span>${esc(L[0])}</td><td><span class="meta">${esc(r.task)}</span><br>${esc(r.note)}</td><td>${c ? `<a href="#case-${r.case}">${c.media.poster ? `<img class="mini" src="${c.media.poster}" alt="案例">` : "看案例"}</a>` : `<span class="meta">–</span>`}</td></tr>`; }).join("")}</table></div></details>`]);
    if (b.fails) secs.push(["4", topicNo(4), `<p class="note">失败的分析里，最主要的根因（每个失败只记一个）。各原因的含义见 <a href="#method">数据与方法</a>；跨 benchmark 的规律见「失败模式」专题。</p>${b.fails}`]);
    // cases the page has not marked yet (the note and the chart examples carry their own marks)
    const marked = new Set([b.note, b.methods, b.fails].join("").match(/#case-[^"]+/g)?.map(x => x.slice(6)) || []);
    const shown = new Set(b.examples.map(r => r.case).filter(Boolean)), extra = b.cases.filter(c => !shown.has(c) && !marked.has(c));
    const tail = [];
    if (extra.length) tail.push(["", "其他案例", `<p class="note">${extra.map((c, i) => `<a class="cref" href="#case-${c}" data-tip="${esc(DATA.cases[c].title)}">${marked.size + i + 1}</a>`).join("")}</p>`]);   // numbers go on after the page's marks
    /* audience-switch:internal */ if (b.issues.length) tail.push(["", "需要核对的问题", issueList(b.issues)]); /* end */
    tail.push(["", "相关结论", findingLinks(b.findings)]);
    return h + entSections(`bench-${id}`, [...secs, ...tail]);
  },
  agent(id) {
    if (id === "compare") { location.replace("#topic-compare"); return ""; }   // the old 三家对比 page is topic 6 now
    const x = agentById(id); if (!x) return pages.home();
    const scope = x.name === "GPT-6 Luna" || CORE() ? "全部评测项" : "Luna 没过的评测项";
    const N = x.notes || {}, P = x.profile || {};
    let h = `<div class="crumb">Agent</div><h1>${esc(x.name)}</h1><p class="lead">${esc(x.harness)}</p>${N["0"] ? `<div class="prose ebody esum">${N["0"]}</div>` : ""}`;
    const one = `<div class="scroll"><table class="t"><tr>${Object.keys(MODES).map(m => `<th>${modeTag(m)}</th>`).join("")}</tr><tr>${Object.keys(MODES).map(m => `<td>${rate(...(x.open[m] || [0, 0]))}</td>`).join("")}</tr></table></div>`
      + `<div class="fig efig"><h3 class="ctitle">结束方式</h3>${endBar(x.endings)}${endLegend()}<p class="note">用时中位数（占时限）：成功 ${x.time["1"] != null ? Math.round(100 * x.time["1"]) + "%" : "–"} · 失败 ${x.time["0"] != null ? Math.round(100 * x.time["0"]) + "%" : "–"}</p></div>`;
    // sections mirror the topics: same numbers and names, so "4 失败模式" here is this agent's part of topic 4
    const secs = DATA.topics.map((t, i) => [String(i + 1), t]).filter(([n]) => n === "1" || N[n] || P[n]).map(([n, t]) => [n, t.name,
      (n === "1" ? `<p class="note">${scope}上的成功数 / 评过分的评测项数（评测看板的全量结果）。</p>` + one : "") + (N[n] ? `<div class="prose ebody">${N[n]}</div>` : "") + (P[n] || "")
      + `<p class="note">全体 agent 的对比见 <a href="#topic-${t.id}">专题 ${n} ${esc(t.name)}</a>。</p>`]);
    return h + entSections(`agent-${id}`, [...secs, ["", "相关结论", findingLinks(x.findings)], ["", "案例", cases(x.cases) || `<p class="note">暂无。</p>`]]);
  },
  results() { location.replace("#topic-outcomes"); return ""; },
  _results() {
    const R = DATA.results, cats = DATA.categories;
    let h = `<h2 class="sec" id="results">结果总表</h2><p class="note">每格是成功数 / 评过分的评测项数，取自评测看板的全量结果（每个 agent 每个评测项取最新一次合规运行），不是抽样；底色按成功的比例。可切换模式${CORE() ? "" : "和范围"}，点表头排序，最后一行是合计。</p>
      <div class="filters"><span class="seg" id="rm">${[["privileged", "privileged"], ["standard", "standard"], ["standard-realtime", "realtime"], ["all", "全部模式"]].map(([k, l]) => `<button data-v="${k}"${k === "privileged" ? ' class="on"' : ""}>${l}</button>`).join("")}</span>
      ${CORE() ? "" : `<span class="seg" id="rs"><button data-v="open" class="on">Luna 没过的评测项</button><button data-v="all">全部评测项</button></span>`}</div>
      <p class="note" id="rnote"></p><div class="scroll" id="rt"></div>`;
    setTimeout(() => { if (!$("#rt")) return;   // not on this page (the #samples page builds topic markup off-screen)
      const st = {mode: "privileged", scope: "open", sort: null, dir: -1};
      const order = R.order ? R.order.map(([b, c]) => [b, cats.find(x => x.id === c) || {id: c, name: ""}]) : cats.flatMap(c => c.benches.map(b => [b, c]));   // R.order: RoboSafeBench too (no page)
      const bname = b => DATA.benches[b] ? `<a href="#bench-${b}">${esc(benchName(b))}</a>` : esc((R.names || {})[b] || b);
      const get = (b, a) => { const md = R.cells[b]?.[a] || {}; let s = 0, n = 0, wait = 0;
        for (const [m, v] of Object.entries(md)) if (st.mode === "all" || m === st.mode) { s += v[st.scope][0]; n += v[st.scope][1]; wait += (v.other["in-progress"] || 0) + (v.other.held || 0); }
        return [s, n, wait]; };
      const shade = (s, n) => n ? `p${Math.min(5, 1 + Math.floor(5 * s / n - 1e-9))}` : "";
      const cell = (s, n, w) => n ? `<td class="hc ${s ? shade(s, n) : "p1"}" data-tip="${s}/${n} 成功${w ? `；另有 ${w} 个评测项进行中或暂停` : ""}"><b>${s}/${n}</b>${w ? "<small>·</small>" : ""}</td>` : `<td class="hc q0" data-tip="${w ? `${w} 个评测项进行中或暂停` : "没有评过分的评测项"}">${w ? "…" : "–"}</td>`;
      const draw = () => {
        const agents = R.agents.filter(a => st.scope === "all" || a !== "GPT-6 Luna");
        let rows = order.map(([b, c]) => ({b, c, v: agents.map(a => get(b, a))})).filter(r => r.v.some(x => x[1] || x[2]));
        if (st.sort === "bench") rows.sort((x, y) => st.dir * ((R.names || {})[y.b] || y.b).localeCompare((R.names || {})[x.b] || x.b));
        else if (st.sort != null) rows.sort((x, y) => { const [sa, na] = x.v[st.sort], [sb, nb] = y.v[st.sort]; return st.dir * ((na ? sa / na : -1) - (nb ? sb / nb : -1)) * -1; });
        const tot = agents.map((_, i) => rows.reduce((acc, r) => [acc[0] + r.v[i][0], acc[1] + r.v[i][1], acc[2] + r.v[i][2]], [0, 0, 0]));
        const arrow = k => st.sort === k ? (st.dir < 0 ? " ↓" : " ↑") : "";
        $("#rt").innerHTML = `<table class="t heat results"><tr><th data-k="bench" class="sort">Benchmark${arrow("bench")}</th><th>类别</th>${agents.map((a, i) => `<th data-k="${i}" class="sort">${esc(a)}${arrow(i)}</th>`).join("")}</tr>`
          + rows.map(r => `<tr><th scope="row">${bname(r.b)}</th><td class="meta nowrap">${esc(CAT_SHORT[r.c.id] || r.c.name)}</td>${r.v.map(([s, n, w]) => cell(s, n, w)).join("")}</tr>`).join("")
          + `<tr class="total"><th scope="row">合计</th><td></td>${tot.map(([s, n, w]) => cell(s, n, w)).join("")}</tr></table>`;
        $("#rnote").textContent = CORE() ? "" : st.scope === "open" ? "Luna 没过的评测项：非 Luna 的 agent 只跑这些评测项，彼此可比；Luna 在这里全是失败，所以不列。" : "全部评测项：Luna 跑了全部评测项，其他 agent 只跑 Luna 没过的评测项，Luna 一列和其他列不能直接比。";
        document.querySelectorAll("#rt th.sort").forEach(th => th.onclick = () => { const k = th.dataset.k === "bench" ? "bench" : +th.dataset.k; st.dir = st.sort === k ? -st.dir : -1; st.sort = k; draw(); });
      };
      for (const [id, key] of [["rm", "mode"], ["rs", "scope"]]) document.querySelectorAll(`#${id} button`).forEach(btn => btn.onclick = () => {
        st[key] = btn.dataset.v; document.querySelectorAll(`#${id} button`).forEach(x => x.classList.toggle("on", x === btn)); draw(); });
      draw();
    });
    return h;
  },
  /* audience-switch:internal */
  issues() {
    const types = [...new Set(DATA.issues.map(i => i.type))];
    let h = `<div class="crumb">数据与证据</div><h1>问题清单</h1><p class="lead">分析中发现的、需要 benchmark 方核对的问题。只记录现象，不改 benchmark；按能翻转多少结果排序。</p>
      <div class="filters"><select id="it" aria-label="类型"><option value="">类型：全部</option>${types.map(t => `<option>${esc(t)}</option>`).join("")}</select></div><div id="ilist"></div>`;
    setTimeout(() => { const draw = () => { const v = $("#it").value; $("#ilist").innerHTML = issueList(DATA.issues.filter(i => !v || i.type === v).map(i => i.id)); }; $("#it").onchange = draw; draw(); });
    return h;
  },
  /* end */
  cases() {
    const all = Object.values(DATA.cases);
    const opts = (id, label, vals) => `<select id="${id}" aria-label="${label}"><option value="">${label}：全部</option>${[...new Set(vals)].sort().map(v => `<option>${esc(v)}</option>`).join("")}</select>`;
    let h = `<div class="crumb">证据</div><h1>案例库</h1><p class="lead">每个案例来自一条深读或略读的分析记录；finding、benchmark 和 agent 页里的案例都链到这里。</p>`;
    h += `<div class="filters">${opts("fb", "Benchmark", all.map(c => benchName(c.bench)))}${opts("fa", "Agent", all.map(c => c.agent))}${opts("fm", "模式", all.map(c => MODES[c.mode] || c.mode))}${opts("fo", "结果", all.map(c => OUTCOME[c.outcome]))}${opts("fp", "主因", all.map(c => c.primary).filter(Boolean).map(causeName))}</div><p class="note" id="fcount"></p><div class="grid" id="cgrid"></div>`;
    setTimeout(() => {
      const apply = () => {
        const v = k => $("#" + k).value;
        const ids = all.filter(c => (!v("fb") || benchName(c.bench) === v("fb")) && (!v("fa") || c.agent === v("fa")) && (!v("fm") || (MODES[c.mode] || c.mode) === v("fm")) && (!v("fo") || OUTCOME[c.outcome] === v("fo")) && (!v("fp") || (c.primary && causeName(c.primary) === v("fp"))))
          .sort((a, b) => (b.key_case - a.key_case) || (b.score - a.score)).map(c => c.id);
        $("#cgrid").innerHTML = ids.map(c => caseCard(c)).join(""); $("#fcount").textContent = `${ids.length} 个案例`;
      };
      ["fb", "fa", "fm", "fo", "fp"].forEach(k => $("#" + k).onchange = apply); apply();
    });
    return h;
  },
  case(id) {
    const c = DATA.cases[id]; if (!c) return pages.cases();
    const m = c.media.video ? `<div class="media"><video controls muted preload="metadata" ${c.media.poster ? `poster="${c.media.poster}"` : ""} src="${c.media.video}"></video></div>${trialRef(c)}<p class="note">评分回放${c.media.speed > 1 ? `，${c.media.speed} 倍速` : ""}</p>` : c.media.poster ? `<div class="media"><img src="${c.media.image || c.media.poster}" alt=""></div>${trialRef(c)}<p class="note">${c.media.poster_kind === "agent" ? `没有评分回放（${esc(c.media.note || "")}）；这是 agent 自己存下的一张图` : c.media.note ? `没有评分回放视频（${esc(c.media.note)}）；这是能找到的最后一帧` : "评分回放的最后一帧"}</p>` : c.media.note ? `<p class="note">没有回放画面：${esc(c.media.note)}</p>` : "";
    let h = `<div class="crumb"><a href="#cases">案例库</a> · <a href="#bench-${c.bench}">${esc(benchName(c.bench))}</a> · <a href="#agent-${c.agent_id}">${esc(c.agent)}</a></div><h1>${esc(c.title)}</h1>${trialRef(c)}`;
    h += `<div class="chips"><span class="pill ${c.outcome === "success" ? "ok" : "no"}">${OUTCOME[c.outcome]}</span>${modeTag(c.mode)}<span class="pill">用时 ${esc(c.minutes)} / ${esc(c.cutoff)} min</span>${c.loop && c.loop.length ? `<span class="pill deflab" data-tip="${esc(c.loop[2])}"><span class="dot" style="background:var(${c.loop[1]})"></span>${esc(c.loop[0])}</span>` : ""}${c.key_case ? `<span class="pill key">精选</span>` : ""}<span class="pill">${c.depth === "deep" ? "深读" : c.depth === "integrity" ? "越界分析" : "略读"}</span>${c.validity !== "valid" ? `<span class="pill warn" title="${esc(c.validity_reason)}">${c.validity === "infra" ? "基础设施问题" : c.validity === "suspect" ? "评分侧存疑" : "违规"}</span>` : ""}</div>${m}`;
    h += `<p class="meta">${esc(c.task)}</p>` + (c.approach ? `<h2>方法</h2><p>${esc(c.approach)}</p>` : "") + `<h2>经过</h2>${activityStrip(c.activity)}${progressStair(c.progress, c.activity, c.outcome)}`
      + (c.steps.length ? `<ol class="steps">${c.steps.map(([t, x]) => `<li><span class="t">${esc(t)}</span><span>${esc(x)}</span></li>`).join("")}</ol>` : c.story ? `<p>${esc(c.story)}</p>` : "");
    const I = c.integrity;
    if (I) h += `<h2>越界行为</h2><div class="chips"><span class="pill ${I.severity === "violation" ? "no" : I.severity === "minor" ? "warn" : ""}">${{violation: "违规", minor: "灰区", none: "无问题"}[I.severity] || esc(I.severity)}</span><span class="pill">动机：${{"answer-seeking": "找答案", "understanding-api": "弄懂接口", housekeeping: "整理", speed: "提速", other: "其他"}[I.intent] || esc(I.intent)}</span><span class="pill">影响：${{none: "没有", helped: "有帮助", decisive: "决定成败", unknown: "不清楚"}[I.effect] || esc(I.effect)}</span></div>`
      + `<ol class="steps">${(I.events || []).map(e => `<li><span class="t">${esc(e.t || "")}</span><span><span class="mono">${esc(e.kind)}</span> ${esc(e.what)}<br><span class="note">拿到：${{nothing: "没有", partial: "部分", answer: "答案内容"}[e.got] || esc(e.got)} · 指令是否允许：${{yes: "允许", no: "不允许", unclear: "不清楚"}[e.allowed] || esc(e.allowed)}（规则：${esc(e.rule)}）</span></span></li>`).join("")}</ol>${I.note ? `<p>${esc(I.note)}</p>` : ""}`;
    if (c.outcome === "failure" && c.primary) h += `<h2>失败分析</h2><dl class="kv"><dt>阶段</dt><dd>${esc(STAGE[c.stage] || c.stage)}</dd><dt>主因</dt><dd>${esc(causeName(c.primary))} <span class="note">${esc(causeDesc(c.primary))}</span></dd>${c.secondary.length ? `<dt>次因</dt><dd>${c.secondary.map(s => `<span class="deflab" data-tip="${esc(causeDesc(s))}">${esc(causeName(s))}</span>`).join("、")}</dd>` : ""}<dt>决定性错误</dt><dd>[${esc(c.decisive.t || "?")}] ${esc(c.decisive.what)}</dd><dt>证据</dt><dd>${esc(c.evidence)}</dd><dt>最接近成功</dt><dd>${esc(c.best)}</dd></dl>`;
    const t = c.time;
    if (c.depth !== "integrity") h += `<h2>时间</h2><dl class="kv"><dt>查看时钟</dt><dd>${t.clock_aware ? "有" : "没有"}${t.clock_checks_seen != null ? `（${t.clock_checks_seen} 次）` : ""}</dd><dt>按预算规划</dt><dd>${t.planned_budget ? "有" : "没有"}</dd><dt>首个交付物</dt><dd>${esc(t.first_deliverable_t || "–")}</dd><dt>为何此时结束</dt><dd>${esc(t.stop_reason)}</dd>${t.wasted ? `<dt>浪费</dt><dd>${esc(t.wasted)}</dd>` : ""}</dl>`;
    if (c.style.notes) h += `<h2>风格</h2><p>${esc(c.style.notes)}</p>`;
    if (c.notable.length) h += `<h2>值得注意</h2><ul>${c.notable.map(n => `<li>${esc(n)}</li>`).join("")}</ul>`;
    if (c.findings.length) h += `<h2>引用它的结论</h2>${findingLinks(c.findings)}`;
    return h;
  },
  search() {
    const q = SEARCH.q, terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    let h = `<div class="crumb">搜索</div><h1>搜索${q ? `：${esc(q)}` : ""}</h1>`;
    if (!terms.length) return h + `<p class="lead">在左上角输入词语，回车。可以输入多个词，用空格隔开，结果须包含全部的词；例如「Opus 时钟」「抓空 RoboCasa」${/* audience-switch:internal */ "「问题 38」" + /* end */ ""}。</p>`;
    const hits = searchIndex().map(e => { const t = e.title.toLowerCase(), all = (e.title + " " + e.label + " " + e.text).toLowerCase();
      return terms.every(w => all.includes(w)) ? {e, score: terms.filter(w => t.includes(w)).length * 10 + terms.reduce((n, w) => n + all.split(w).length - 1, 0)} : null; }).filter(Boolean)
      .sort((a, b) => b.score - a.score);
    const snip = txt => { const low = txt.toLowerCase(), i = Math.max(0, low.indexOf(terms[0]) - 40); let s = esc(txt.slice(i, i + 160));
      for (const w of terms) s = s.replace(new RegExp(w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), m => `<mark>${m}</mark>`); return (i ? "…" : "") + s + "…"; };
    h += `<p class="note">${hits.length} 条结果${hits.length > 80 ? "，显示前 80 条" : ""}。</p>`;
    const kinds = ["结论", "问题", "Benchmark", "Agent", "案例"];
    for (const k of kinds) {
      const hs = hits.filter(x => x.e.kind === k).slice(0, k === "案例" ? 40 : 30); if (!hs.length) continue;
      h += `<h2 class="sec">${k}（${hits.filter(x => x.e.kind === k).length}）</h2><ul class="sres">${hs.map(({e}) => `<li><a href="${e.href}"><span class="fid">${esc(e.label)}</span> ${esc(e.title)}</a><p class="note">${snip(e.text)}</p></li>`).join("")}</ul>`;
    }
    return h;
  },
  method() {
    const M = DATA.method, s = DATA.site;
    const tbl = (obj, label) => `<div class="scroll"><table class="t"><tr><th>${label}</th><th class="num">数量</th></tr>${Object.entries(obj).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<tr><td>${esc(STATUS[k] || k)}</td><td class="num">${v.toLocaleString()}</td></tr>`).join("")}</table></div>`;
    let h = `<div class="crumb">证据</div><h1>数据与方法</h1><p class="lead">数据截至 ${esc(s.snapshot)}${/* audience-switch:internal */ `；本次比上次新增 ${M.changes.added} 个、变化 ${M.changes.changed} 个、消失 ${M.changes.gone} 个 trial` + /* end */ ""}。</p>`;
    /* audience-switch:internal */
    h += `<h2>有效性</h2><p>抽样分析只用 valid；infra（基础设施）不算 agent 的失败；rule（违规）和 suspect（可疑）单独列出，不计成功。看板的结果不按这些类别排除：评过分的都算，被内容过滤器掐断的记作失败。</p>${tbl(M.validity, "类别")}<h3>不计入统计的 trial：原因</h3><div class="scroll"><table class="t"><tr><th>类别</th><th>原因代码</th><th>含义</th><th class="num">数量</th></tr>${M.reasons.map(([cls, why, n]) => `<tr><td>${esc(VCLS[cls] || cls)}</td><td class="mono">${esc(why)}</td><td>${esc(why.split(",").map(w => REASON[w] || "").filter(Boolean).join("；") || "–")}</td><td class="num">${n}</td></tr>`).join("")}</table></div>`;
    h += `<h2>评测项状态</h2><p>评测项 = 一个任务（含模式）× 一个 agent。${CORE() ? "" : "按设计不跑 = Luna 已过、其他 agent 不再跑。"}</p>${tbl(M.status, "状态")}`;
    /* end */
    h += `<h2>任务集</h2><p>本页是<b>${esc(s.sets[s.set].name)}</b>。${s.set_switch ? `另一个版本：<a href="${esc(s.set_switch)}#method">${esc(s.sets[s.set === "core" ? "all" : "core"].name)}</a>。` : ""}</p><dl class="kv">${["core", "all"].map(k => `<dt>${esc(s.sets[k].name)}</dt><dd>${esc(s.sets[k].desc)}</dd>`).join("")}</dl><p class="note">${esc(s.sets.left_out)}</p>`;
    h += `<h2>成功数</h2><p>${esc(s.perf_note || "")}${s.perf_time ? `（看板快照 ${esc(s.perf_time)}）` : ""}</p>`;
    h += `<h2>分析</h2><p>随机抽样：每个评测项先给一个固定随机号，小于 0.30 就抽中；按 agent × benchmark × 模式 × 成败分层，每层至少抽到 30%。另有特意挑的 trial（越界排查、假设验证、差一点成功），只作案例和深读。共 ${s.n_reviews} 条分析记录，深读 ${s.n_deep} 份。分类表 v${esc(CB.version)}。</p>${s.sample_note ? `<p class="note">${esc(s.sample_note)}</p>` : ""}`;
    h += `<h3>失败根因分类</h3><div class="scroll"><table class="t"><tr><th>大类</th><th>原因</th><th>含义</th><th>代码</th></tr>${Object.entries(CB.cause).map(([g, cs]) => Object.keys(cs).map((c, i) => `<tr><td>${i ? "" : esc(GROUP[g] || g)}</td><td>${esc(causeName(c))}</td><td>${esc(causeDesc(c))}</td><td class="mono note">${esc(c)}</td></tr>`).join("")).join("")}</table></div>`;
    const vocab = (title, obj) => `<h3>${title}</h3><div class="scroll"><table class="t">${Object.entries(obj).map(([c, d]) => `<tr><td class="mono">${esc(c)}</td><td>${esc(d)}</td></tr>`).join("")}</table></div>`;
    if (CB.approach) h += `<h2>解题方式标注</h2><p>每条分析记录再按下面的词表标一次「谁在决定动作、用了什么技术、怎么感知、交付物怎么生成」（标注 approach-1）。</p>` + vocab("谁在决定动作", CB.approach.loop) + vocab("技术", CB.approach.tech) + vocab("感知来源", CB.approach.perception) + vocab("越界行为", CB.approach.integrity);
    return h;
  },
};

/* audience-switch:internal */
// #samples (internal build only): one real example of every chart type, one finding block, one child section, one case
// card and one legend, taken from the report itself; the reference page for restyling.
pages.samples = () => {
  const S = DATA.samples; if (!S) return pages.home();
  const pick = (fid, sel) => { const f = DATA.findings[fid]; if (!f) return ""; const d = document.createElement("div"); d.innerHTML = pages.topic(f.topic); return d.querySelector(sel)?.outerHTML || ""; };
  let h = `<div class="crumb">数据与证据</div><h1>图表样例</h1><p class="lead">每种图各取报告里的一个真实例子，另有结论块、展开节、案例卡和图例各一个；改版式时对照这一页。</p>`;
  h += `<nav class="toc" aria-label="本页目录"><ul>${S.charts.map((c, i) => `<li><a class="fid" href="#samples" data-sec="smp-${c.kind}">${i + 1}</a><span>${esc(c.kind)} <span class="mono note">${esc(c.fig)}</span></span></li>`).join("")}</ul></nav>`;
  for (const c of S.charts) h += `<h2 class="sec" id="smp-${c.kind}">${esc(c.kind)}</h2><p class="note">${c.from ? `来自 <a class="fid" href="#f-${c.from}">§${c.from}</a> · ` : ""}<span class="mono">${esc(c.fig)}</span></p>${c.html}`;
  h += `<h2 class="sec">结论块</h2>${pick(S.finding, `article[id="f-${S.finding}"]`)}<h2 class="sec">展开节</h2>${pick(S.child, `section[id="f-${S.child}"]`)}`;
  h += `<h2 class="sec">案例卡</h2><div class="grid">${caseCard(S.case, 1, S.case_label)}</div><h2 class="sec">图例</h2>${S.legend}`;
  setTimeout(() => document.querySelectorAll("a[data-sec]").forEach(a => a.onclick = e => { e.preventDefault(); document.getElementById(a.dataset.sec)?.scrollIntoView(); }));
  return h;
};
/* end */

function route() {
  const h = location.hash.slice(1) || "home";
  let page = "home", arg = "", focus = "";
  if (h.startsWith("f-") && DATA.findings[h.slice(2)]) { page = "topic"; arg = DATA.findings[h.slice(2)].topic; focus = h; }
  /* audience-switch:internal */
  else if (h.startsWith("issue-")) { page = "issues"; focus = h; }
  /* end */
  else { const m = h.match(/^(topic|bench|agent|case)-(.+)$/); if (m) [page, arg] = [m[1], m[2]]; else if (pages[h]) page = h; }
  const key = page + ":" + arg;
  $("#nav").classList.remove("open"); $("#navtoggle")?.setAttribute("aria-expanded", false);
  if (focus && key === route.last) { document.getElementById(focus)?.scrollIntoView(); return; }   // same page: just scroll
  route.last = key;
  nav(page === "home" ? "home" : ["cases", "method", "results", "issues", "search", /* audience-switch:internal */ "samples", /* end */].includes(page) ? page : `${page}-${arg}`);
  $("#main .col").innerHTML = pages[page](arg);
  document.body.dataset.page = page;
  if (page === "home") setTimeout(() => document.querySelectorAll(".sblock .sbody").forEach(u => markTerms(u)));
  if (focus) setTimeout(() => { document.getElementById(focus)?.scrollIntoView(); spy(); }); else { window.scrollTo(0, 0); setTimeout(spy); }
}
addEventListener("hashchange", route);
route();
/* audience-switch */
// Links to the same route in the other builds: 核心集 ⇄ 全部任务 (with build.py --both) and 内部版 ⇄ 分享版 (with --switch).
if (DATA.site.switch || DATA.site.set_switch) {
  const bar = document.createElement("div"), share = DATA.site.audience === "share", S = DATA.site.sets, core = DATA.site.set === "core";
  bar.className = "swbar";
  const link = (href, title, html) => { const a = document.createElement("a"); a.className = "audsw"; a.title = title; a.innerHTML = html;
    const sync = () => { a.href = href + location.hash; }; addEventListener("hashchange", sync); sync(); bar.appendChild(a); };
  if (DATA.site.set_switch) link(DATA.site.set_switch, core ? `切到${S.all.name}` : `切到${S.core.name}`,
    core ? `<b>${esc(S.core.name)}</b> ⇄ ${esc(S.all.name)}` : `${esc(S.core.name)} ⇄ <b>${esc(S.all.name)}</b>`);
  if (DATA.site.switch) link(DATA.site.switch, share ? "切到内部版" : "切到分享版", share ? `内部版 ⇄ <b>分享版</b>` : `<b>内部版</b> ⇄ 分享版`);
  document.body.appendChild(bar);
}
/* end */
