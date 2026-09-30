"""The small HTML pieces the pages share: Markdown (notes.md, the analysis), KPI tiles, bar cells, stacked bars, the
pass/fail chip."""
from __future__ import annotations

import re

from common import esc


def md(src: str) -> str:
    """Enough Markdown for notes.md: headings, paragraphs, lists, tables, code blocks, `code`, **bold**, [links]()."""
    def inline(s):
        s = esc(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        # links only to the web, a relative file or an anchor: notes.md is written from what an agent wrote
        return re.sub(r"\[([^\]]+)\]\(((?:https?://|\.{0,2}/|#)[^)\s]*)\)", r'<a href="\2">\1</a>', s)
    out, L, i = [], src.splitlines(), 0
    item = re.compile(r"\s*([-*]|\d+\.)\s+")
    while i < len(L):
        line = L[i]
        if line.startswith("```"):
            j = i + 1
            while j < len(L) and not L[j].startswith("```"):
                j += 1
            out.append(f"<pre>{esc(chr(10).join(L[i + 1:j]))}</pre>"); i = j + 1
        elif m := re.match(r"(#{1,4})\s+(.*)", line):
            h = max(3, len(m.group(1))); out.append(f"<h{h}>{inline(m.group(2))}</h{h}>"); i += 1
        elif item.match(line):
            items = []
            while i < len(L) and (item.match(L[i]) or (items and L[i].startswith("  ") and L[i].strip())):
                if item.match(L[i]):
                    items.append(item.sub("", L[i], count=1))
                else:
                    items[-1] += " " + L[i].strip()
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
        elif line.startswith("|"):
            rows = []
            while i < len(L) and L[i].startswith("|"):
                rows.append([c.strip() for c in L[i].strip().strip("|").split("|")]); i += 1
            body = [r for r in rows[1:] if not all(re.fullmatch(r":?-+:?", c) for c in r)]
            out.append('<div class="tw"><table><thead><tr>' + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</tbody></table></div>")
        elif not line.strip():
            i += 1
        else:
            buf = []
            while i < len(L) and L[i].strip() and not re.match(r"#{1,4}\s|```|\|", L[i]) and not item.match(L[i]):
                buf.append(L[i].strip()); i += 1
            out.append(f"<p>{inline(' '.join(buf))}</p>")
    return "\n".join(out)


def kpi(k: str, v: str, s: str = "", bar=None, cls: str = "", wide: bool = False, extra: str = "") -> str:
    b = ""
    if bar is not None:
        frac, bc = bar
        b = f'<div class="pbar lg {bc}"><i style="width:{max(0.0, min(1.0, frac)) * 100:.1f}%"></i></div>'
    return f'<div class="kpi{" wide" if wide else ""}"><div class="k">{k}</div><div class="v {cls}">{v}</div>{b}{extra}<div class="s">{s}</div></div>'


def pcell(frac, text: str, cls: str = "", t: str = "") -> str:
    w = 0.0 if frac is None else max(0.0, min(1.0, frac)) * 100
    if frac is not None and frac > 0 and w < 1.5:
        w = 1.5   # a sliver stays visible
    return f'<div class="cell"{f" data-tip={chr(34)}{t}{chr(34)}" if t else ""}><div class="pbar {cls}"><i style="width:{w:.1f}%"></i></div><span class="t">{text}</span></div>'


def stackbar(parts: list, total: float | None = None, lg: bool = False) -> str:
    tot = total or sum(v for v, _, _ in parts) or 1
    return (f'<div class="stack{" lg" if lg else ""}">' + "".join(f'<i class="{c}" style="width:{v / tot * 100:.2f}%" data-tip="{t}"></i>'
                                                           for v, c, t in parts if v > 0) + "</div>")


def status_chip(r: dict | None, big: bool = False) -> str:
    b = " big" if big else ""
    if r is None:
        return f'<span class="chip na{b}">未跑</span>'
    return f'<span class="chip ok{b}">✓ 通过</span>' if r["d"]["pass"] else f'<span class="chip bad{b}">✗ 未通过</span>'
