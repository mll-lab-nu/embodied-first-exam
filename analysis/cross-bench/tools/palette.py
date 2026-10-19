"""Chart colours: the one categorical palette every chart draws from, its aliases, and colour distance (OKLab ΔE×100,
plain and under protan / deutan simulation, Machado 2009 — the same maths as the dataviz skill's validate_palette.js).

Rule (meta/DESIGN.md → Colours): a chart's categories take CAT slots in fixed order (--cat1, --cat2, …, never cycled;
past eight they fold into 其他), and 其他 / none / n/a / 外部 is the grey --c0. CAT plus the grey passes FLOOR on every
pair in both themes, so any chart drawn from it has every legend colour clearly apart; check.py fails a page where a
chart's legend colours come closer than FLOOR (with declared groups: adjacent members, and every pair across groups)."""
from __future__ import annotations
import itertools
import math
import re
from functools import lru_cache

FLOOR = 15.0          # validate_palette.js NORMAL_FLOOR: normal-vision ΔE×100 below which two colours read as one
CVD_FLOOR = 6.0       # validate_palette.js CVD_FLOOR: protan / deutan ΔE×100 below which touching colours FAIL

MACHADO = {"protan": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
           "deutan": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881))}
HEX = re.compile(r"#[0-9a-f]{6}")


def _lin(h: str) -> list[float]:
    h = h.lstrip("#")
    return [(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4) for c in (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))]


def _lab(rgb) -> tuple[float, float, float]:
    r, g, b = rgb
    l, m, s = ((0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3),
               (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3),
               (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3))
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


@lru_cache(maxsize=None)
def lab(h: str, kind: str = "") -> tuple[float, float, float]:
    rgb = _lin(h)
    if kind:
        rgb = [max(0.0, min(1.0, sum(MACHADO[kind][i][j] * rgb[j] for j in range(3)))) for i in range(3)]
    return _lab(rgb)


def de(a: str, b: str, kind: str = "") -> float:
    """ΔE×100 between two hex colours; kind = '' (normal vision), 'protan' or 'deutan'."""
    return 100 * math.dist(lab(a, kind), lab(b, kind))


def cvd(a: str, b: str) -> float:
    """Colour-blind distance of two hex colours: the smaller of protan and deutan ΔE×100."""
    return min(de(a, b, "protan"), de(a, b, "deutan"))


# The categorical palette in slot order: (token, light hex, dark hex); surfaces #ffffff / #161a21. Each slot keeps its
# lightness tier in both themes (blue, magenta mid; rust, violet, green deep; aqua, gold, coral light), which keeps the
# warm hues apart. validate_palette.js in this order: ALL PASS in both themes (adjacent CVD ≥ 9.4 light / 8.6 dark,
# normal ≥ 16.7 / 16.5; light aqua, gold, coral and dark rust, violet are under 3:1 contrast, so every chart keeps its
# legend and table). Every pair of the eight and the grey is ≥ 16.5 apart in both themes. Two pairs are close for
# colour-blind readers and never touch in a chart: rust–green (slots 2 and 8) and, dark only, gold–coral.
CAT = [("--cat1", "#1384e4", "#0886e9"),     # blue
       ("--cat2", "#913b17", "#a83b02"),     # rust
       ("--cat3", "#0ccfb2", "#0cab93"),     # aqua
       ("--cat4", "#c7af2c", "#a08a00"),     # gold
       ("--cat5", "#b65caf", "#bd53b5"),     # magenta
       ("--cat6", "#5d4e9e", "#6242be"),     # violet
       ("--cat7", "#fe6558", "#e16a5e"),     # coral red
       ("--cat8", "#28661c", "#1c7902")]     # green
GREY = ("--c0", "#919694", "#525755")        # 其他 / none / n/a / 外部
SOFT = ("--c0s", "#c9ced6", "#4a505a")       # a lighter neutral for 都失败 (fig:modes): recedes behind the hues
BLUE, RUST, AQUA, GOLD, MAGENTA, VIOLET, RED, GREEN = (t for t, _, _ in CAT)
# The agents' own colours, the same in every chart (user 10-19): GPT-6 Astra red-orange, Gemini 4 Argon purple, Opus 5.5
# teal (the --cat3 values); every other agent is the grey --c0. validate_palette.js on the three: ALL PASS light (worst
# adjacent normal 29.7, CVD 26.7) and dark on #161a21 (24.5 / 15.7); each is ≥ 16.5 from the grey in both themes.
AGENT = {"GPT-6 Astra": ("--ag-astra", "#e4572e", "#e35b33"), "Gemini 4 Argon": ("--ag-argon", "#7b5cd6", "#9175e8"),
         "Opus 5.5": ("--ag-opus", "#0ccfb2", "#0cab93")}

# Names that valence charts and the page code (tools/site/app.js) use, as aliases of the slots. Valence keeps its
# meaning: success green (--ok), failure and 超时 blue (--n1; not red, which is GPT-6 Astra's colour since 10-19), the
# other failure kinds rust / magenta / gold / violet.
# Approach ways and tool calls (app.js LOOP / ACT) are slots in the charts' order; progress levels 0–5 run grey →
# violet → blue → aqua → gold → green (level 5, 做成, is the success green). The sequences figs.py draws from these
# (ENDS, LEVELS, modes, would-pass, claims) pass validate_palette.js in order in both themes.
ALIAS = {"--ok": GREEN, "--n1": BLUE, "--n2": RUST, "--n3": MAGENTA, "--n4": GOLD, "--n5": VIOLET,
         "--l1": BLUE, "--l2": RUST, "--l3": AQUA, "--lp2": GOLD, "--lp1": MAGENTA, "--c7": GOLD,
         "--lv0": GREY[0], "--lv1": VIOLET, "--lv2": BLUE, "--lv3": AQUA, "--lv4": GOLD, "--lv5": GREEN}


def slots(keys: list[tuple], grey=("none", "other", "_other", "n/a", "external")) -> list[tuple]:
    """Colour a chart's keys [(key, label[, definition])] in fixed order: --cat1, --cat2, … for the keys, --c0 for the
    grey ones (其他 / none / n/a / 外部). Returns [(key, label, colour[, definition])]. More keys than slots is an
    error: fold the rest into 其他 first."""
    out, i = [], 0
    for k in keys:
        if k[0] in grey:
            c = GREY[0]
        elif i < len(CAT):
            c, i = CAT[i][0], i + 1
        else:
            raise ValueError(f"more than {len(CAT)} coloured categories ({k[0]}): fold the rest into 其他")
        out.append((k[0], k[1], c, *k[2:]))
    return out


def css() -> str:
    """The chart colour tokens for the page (light values and aliases, then the two dark-theme blocks)."""
    t = CAT + [GREY, SOFT] + list(AGENT.values())
    light = "".join(f"{n}:{lo};" for n, lo, _ in t) + "".join(f"{a}:var({s});" for a, s in ALIAS.items())
    dark = "".join(f"{n}:{hi};" for n, _, hi in t)
    return (f':root{{{light}}}@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{{dark}}}}}'
            f':root[data-theme="dark"]{{{dark}}}')


def page_tokens(page: str) -> tuple[dict, dict]:
    """{token: hex} for the light and the dark theme, from the :root blocks of a built page (aliases resolved)."""
    light, dark = {}, {}
    for m in re.finditer(r'(:root(?:\[data-theme="dark"\]|:not\(\[data-theme="light"\]\))?)\s*\{([^{}]*)\}', page):
        (light if m.group(1) == ":root" else dark).update((k, v.strip()) for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;}]+)", m.group(2)))
    dark = {**light, **dark}
    def value(t, v, depth=0):
        m = re.fullmatch(r"var\((--[\w-]+)\)", v)
        return value(t, t.get(m.group(1), ""), depth + 1) if m and depth < 5 else v.lower()
    return {k: value(light, v) for k, v in light.items()}, {k: value(dark, v) for k, v in dark.items()}


def too_close(groups: list[list[tuple[str, str]]], tokens: dict) -> list[tuple]:
    """Legend colour pairs that read as one: [(ΔE, label a, label b, kind)], kind 'normal' (ΔE < FLOOR) or 'cvd'
    (touching entries, colour-blind ΔE < CVD_FLOOR). groups: a chart's legend, one [(label, token)] list per declared
    group (one list = no groups). Without groups every pair counts; with groups, adjacent members of a group and every
    pair across groups. A token the page does not define counts as ΔE 0."""
    hexes = lambda a, b: (tokens.get(a[1], ""), tokens.get(b[1], ""))
    ok = lambda x, y: HEX.fullmatch(x) and HEX.fullmatch(y)
    within = [p for g in groups for p in zip(g, g[1:])]
    pairs = (within + [(a, b) for g1, g2 in itertools.combinations(groups, 2) for a in g1 for b in g2] if len(groups) > 1
             else list(itertools.combinations(groups[0] if groups else [], 2)))
    out = [(de(*hexes(a, b)) if ok(*hexes(a, b)) else 0.0, a[0], b[0], "normal") for a, b in pairs]
    out = [o for o in out if o[0] < FLOOR]
    out += [(cvd(*hexes(a, b)), a[0], b[0], "cvd") for a, b in within
            if ok(*hexes(a, b)) and de(*hexes(a, b)) >= FLOOR and cvd(*hexes(a, b)) < CVD_FLOOR]
    return out
