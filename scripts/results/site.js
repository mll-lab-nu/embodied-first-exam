// The results pages (scripts/results/build.py): theme, tooltips, tabs, sortable tables, the video player, copy buttons.
function toggleTheme() {
  const r = document.documentElement;
  const cur = r.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  r.dataset.theme = cur === "dark" ? "light" : "dark";
  try { localStorage.setItem("rcb-theme", r.dataset.theme); } catch (e) {}
}

// a page can hold one run per tab (a task's main run in each mode): look things up inside the tab `from` is in
const scopeOf = (from) => (from && from.closest && from.closest("[data-pane]")) || document;

function play(src, label, from) {
  const scope = scopeOf(from);
  const v = scope.querySelector("video.pv");
  if (!v || !src) return;
  v.src = src; v.play().catch(() => {});
  const pick = scope.querySelector("select.pick");
  if (pick) { pick.value = src; }
  const cap = scope.querySelector(".pcap");
  if (cap) cap.textContent = label || (pick && pick.selectedOptions[0] ? pick.selectedOptions[0].text : "");
  v.scrollIntoView({ behavior: "smooth", block: "center" });
}

document.addEventListener("DOMContentLoaded", () => {
  const tip = document.getElementById("tip");
  let over = null;
  document.addEventListener("mouseover", (e) => {
    over = e.target.closest ? e.target.closest("[data-tip]") : null;
    if (!over) { tip.style.display = "none"; return; }
    tip.innerHTML = over.getAttribute("data-tip");
    tip.style.display = "block";
  });
  document.addEventListener("mousemove", (e) => {
    if (!over) return;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let x = e.clientX + 14, y = e.clientY + 16;
    if (x + w > innerWidth - 8) x = e.clientX - w - 14;
    if (y + h > innerHeight - 8) y = e.clientY - h - 12;
    tip.style.left = Math.max(8, x) + "px"; tip.style.top = Math.max(8, y) + "px";
  });
  // one tool call drawn in several places (time axis, call order, the command list): hover one, all of them light up
  let hl = null;
  document.addEventListener("mouseover", (e) => {
    const c = e.target.closest ? e.target.closest("[data-call]") : null;
    const k = c ? c.getAttribute("data-call") : null;
    if (k === hl) return;
    document.querySelectorAll(".hl").forEach((x) => x.classList.remove("hl"));
    hl = k;
    if (k !== null) scopeOf(c).querySelectorAll(`[data-call="${k}"]`).forEach((x) => x.classList.add("hl"));
  });
  document.addEventListener("click", (e) => {
    const v = e.target.closest ? e.target.closest("[data-video]") : null;
    if (v) { play(v.getAttribute("data-video"), v.getAttribute("data-label"), v); return; }
    const call = e.target.closest ? e.target.closest("[data-call]") : null;
    if (call && call.tagName !== "TR") {   // a call on a chart: open its row in the command list
      const row = scopeOf(call).querySelector(`tr[data-call="${call.getAttribute("data-call")}"]`);
      if (row) {
        for (let d = row.closest("details"); d; d = d.parentElement.closest("details")) d.open = true;
        const inner = row.querySelector("details"); if (inner) inner.open = true;
        row.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      return;
    }
    const c = e.target.closest ? e.target.closest("[data-copy]") : null;
    if (c && navigator.clipboard) {
      navigator.clipboard.writeText(c.getAttribute("data-copy")).then(() => {
        const t = c.textContent; c.textContent = "已复制"; setTimeout(() => (c.textContent = t), 1200);
      });
    }
  });
  // tabs: <div data-tabs="k"><button data-tab="a">..</button></div> ... <section data-pane="k:a">
  document.querySelectorAll("[data-tabs]").forEach((g) => {
    const key = g.getAttribute("data-tabs");
    g.querySelectorAll("button[data-tab]").forEach((b) => b.addEventListener("click", () => {
      g.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
      document.querySelectorAll(`[data-pane^="${key}:"]`).forEach((p) =>
        p.classList.toggle("on", p.getAttribute("data-pane") === `${key}:${b.getAttribute("data-tab")}`));
    }));
  });
  // sortable tables: <th data-sort>; a cell sorts by its data-v (a number) or its text
  document.querySelectorAll("table.data").forEach((t) => {
    t.querySelectorAll("th[data-sort]").forEach((th, i) => th.addEventListener("click", () => {
      const col = [...th.parentNode.children].indexOf(th);
      const asc = th.classList.contains("sorted") ? !th.classList.contains("asc") : th.getAttribute("data-sort") === "asc";
      t.querySelectorAll("th").forEach((x) => x.classList.remove("sorted", "asc"));
      th.classList.add("sorted"); if (asc) th.classList.add("asc");
      const body = t.tBodies[0], rows = [...body.rows];
      const val = (r) => { const c = r.children[col]; if (!c) return null; const v = c.getAttribute("data-v");
        return v === null || v === undefined ? (c ? c.textContent.trim() : "") : (v === "" ? null : parseFloat(v)); };
      rows.sort((a, b) => {
        const x = val(a), y = val(b);
        if (x === null && y === null) return 0; if (x === null) return 1; if (y === null) return -1;
        const d = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "zh");
        return asc ? d : -d;
      });
      rows.forEach((r) => body.appendChild(r));
    }));
  });
});
