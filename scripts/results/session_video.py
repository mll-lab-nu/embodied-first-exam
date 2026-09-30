"""Verifier-side, inside the sim image (for imageio, PIL and a font): one limited-mode session as one video, idle time
cut -- every episode's replay (the benchmark's scripts/<name>/replay.py) back to back, and beside it where the session
is: the episode and how it ended; the command driving the robot (which one, what changed since the one before, as
attempts.py read it from the agent's log, and what the agent did off camera in between); the last thing the agent said
or thought; the last image the model looked at; and the whole session on one strip (episodes above, the agent's tool
calls below, the moment marked) with its colours explained. Run by collect.py once summary.json is written (not with --no-video):
  python session_video.py <report_dir> <benchmark>   -> <report_dir>/session.mp4, session.jpg
Reads summary.json and the files it names, nothing else (no simulator, no model); it shows no score."""
from __future__ import annotations

import bisect
import collections
import functools
import json
import os
import sys
import textwrap

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench  # noqa: E402
from bench import B  # noqa: E402
from calls import tool_kinds  # noqa: E402
from charts import ep_kind  # noqa: E402
from common import TOOLS  # noqa: E402

W, H, FPS = 1280, 720, 25   # the robot, H x H, on the left; the panel on the right
PAD, PW = 28, W - H - 2 * 28   # the panel's margin and text width
HOLD = 3 * FPS              # an image the model looked at stays up at most this long
TAIL = FPS // 2             # an episode's last frames say how it ended
LANE_W, STRIP_Y = 70, 590   # the session strip: its label column, and where it sits in the panel
BG, FG, MUTED, GOLD, LANE, GREEN, RED = "#111418", "#eceef0", "#8b9199", "#f5c451", "#262b33", "#4cc38a", "#ff7070"
ENDED = {"success": ("success", "#30a46c"), "failed": ("fell / failed", "#e5484d"), "endup": ("ended, robot still up", "#e0508a"),
         "steplimit": ("step limit", "#f5a524"), "downlimit": ("step limit", "#b8662e"),   # its label adds "robot down"
         "timeout": ("time's up", "#8b9199"), "error": ("simulator error", "#e5484d"), "reset": ("reset by the agent", "#5b6472"),
         "running": ("still running when the agent stopped", "#8b9199")}
SHORT = {"success": "success", "failed": "fell / failed", "endup": "ended, still up", "steplimit": "step limit",
         "downlimit": "step limit, down", "timeout": "time's up", "error": "sim error", "reset": "reset by the agent",
         "running": "running at the end"}   # the legend's words for ENDED
TOOL_EN = {"robot": "drives the robot", "net": "network", "python": "other Python", "write": "writes files",
           "view": "views an image", "read": "reads files", "other": "other"}   # TOOLS, in the video's language
OFF = {"write": "file edit", "read": "read", "python": "other Python run", "net": "network call", "other": "other call",
       "robot": "robot call"}   # what the agent did off camera, one of each


@functools.lru_cache
def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans" + ("Mono" if mono else "") + ("-Bold" if bold else "")
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}.ttf", size)


@functools.lru_cache
def thumb(path: str) -> Image.Image:
    im = Image.open(path).convert("RGB")
    im.thumbnail((PW, 96))
    return im


def latest(items: list, key):
    """point -> the last of `items` at or before that point of the session, or None."""
    items = sorted(items, key=key)
    keys = [key(x) for x in items]
    return lambda point: items[i - 1] if (i := bisect.bisect_right(keys, point)) else None


MEASURE = ImageDraw.Draw(Image.new("RGB", (1, 1)))


@functools.lru_cache(maxsize=8192)
def fit(text: str, f, width: float) -> str:
    """`text` cut to fit `width` pixels in font `f`, with an ellipsis if it had to be (cached: a line stays up for
    thousands of frames)."""
    if MEASURE.textlength(text, font=f) <= width:
        return text
    lo, hi = 0, len(text)   # the longest start of it that fits with the ellipsis
    while lo < hi:
        mid = (lo + hi + 1) // 2
        lo, hi = (mid, hi) if MEASURE.textlength(text[:mid] + "…", font=f) <= width else (lo, mid - 1)
    return text[:lo] + "…"


def ending(e: dict, s: dict) -> tuple[str, str]:
    """How an episode ended, and whether the robot was still up then (where the benchmark says, Bench.down): an
    episode can end without a fall (a tool dropped) and a fallen robot can run to the step limit."""
    n, ms = len(s["episodes"]), s["spec"]["max_steps"]
    kind = ep_kind(e, e["ep"] == n - 1, ms)   # "endup" once the replay knows the robot was still up
    label, color = ENDED.get(kind, (kind, MUTED))
    down = B.down(e)
    if down is not None and kind == "failed":
        label = "fell"
    elif down is not None and kind in ("steplimit", "downlimit", "running", "reset", "timeout"):
        label += " · robot down" if down else " · robot up"
    return label, color


def when(e: dict, step: int) -> float:
    """The agent-clock moment of an episode's `step`: its steps spread evenly from its start to its last step."""
    t0, t1 = e.get("t0") or 0, e.get("t_last") or e.get("t0") or 0
    return t0 + (t1 - t0) * min(step / max(e["steps"], 1), 1)


def strip(s: dict, width: int) -> tuple[Image.Image, callable]:
    """The whole session on one picture, drawn once: episodes (coloured by how they ended) above, tool calls
    (coloured as the pages colour them) below, on the agent's clock over its whole budget; and t -> x."""
    a0, span = s["a0"], max(s.get("budget_s") or 0, s["a1"] - s["a0"], 1)
    x = lambda t: LANE_W + (width - LANE_W) * min(max((t - a0) / span, 0), 1)
    img = Image.new("RGB", (width, 58), BG)
    d = ImageDraw.Draw(img)
    d.text((0, 2), "episodes", font=font(12), fill=MUTED)
    d.text((0, 22), "tool calls", font=font(12), fill=MUTED)
    d.rectangle((LANE_W, 0, width - 1, 16), fill=LANE); d.rectangle((LANE_W, 20, width - 1, 34), fill=LANE)
    eps = s["episodes"]
    for i, e in enumerate(eps):
        t_next = eps[i + 1]["t0"] if i + 1 < len(eps) else s["a1"]
        x0, x1 = x(e["t0"] or a0), x(max(e.get("t_end") or 0, e.get("t_last") or 0) or t_next)
        d.rectangle((x0, 0, max(x1, x0 + 1), 16), fill=ending(e, s)[1])
    for c in s["calls"]:
        x0, x1 = x(c["t0"]), x(c["t1"])
        d.rectangle((x0, 20, max(x1, x0 + 1), 34), fill=TOOLS[tool_kinds(c)[0]][1])
    for m in range(0, int(span // 60) + 1, 15):
        tx = x(a0 + 60 * m)
        d.line((tx, 36, tx, 40), fill=MUTED)
        lab = f"{m} min" if m == 0 else str(m)
        d.text((min(tx, width - d.textlength(lab, font=font(12))), 42), lab, font=font(12), fill=MUTED)
    return img, x


def legend(s: dict, width: int) -> Image.Image:
    """The strip's colours, for what this session has: how its episodes ended and what its tool calls did."""
    n, ms = len(s["episodes"]), s["spec"]["max_steps"]
    ends = dict.fromkeys(ep_kind(e, e["ep"] == n - 1, ms) for e in s["episodes"])
    used = {tool_kinds(c)[0] for c in s["calls"]}
    rows = [("episode", [(ENDED[k][1], SHORT[k]) for k in ends if k in ENDED]),
            ("tool call", [(TOOLS[k][1], TOOL_EN[k]) for k in TOOLS if k in used])]
    img = Image.new("RGB", (width, 72), BG)
    d, y = ImageDraw.Draw(img), 0
    for name, items in rows:
        d.text((0, y), name, font=font(12), fill=MUTED)
        x = LANE_W
        for color, label in items:
            w = 14 + d.textlength(label, font=font(12)) + 12
            if x + w > width and x > LANE_W:
                y += 16; x = LANE_W
            d.rectangle((x, y + 3, x + 9, y + 12), fill=color)
            d.text((x + 14, y), label, font=font(12), fill=FG)
            x += w
        y += 18
    return img.crop((0, 0, width, y))


def offcamera(s: dict, prev: dict | None, c: dict) -> str:
    """What the agent did between the robot command before `c` and `c`, which the video cuts: for how long, and
    its tool calls by kind."""
    if prev is None or c["t0"] - prev["t1"] < 1:
        return ""
    t0, t1 = prev["t1"], c["t0"]
    kinds = collections.Counter(tool_kinds(x)[0] for x in s["calls"] if t0 < x["t0"] < t1 and not x.get("attempt"))
    views = sum(t0 < v["t"] <= t1 for v in s["views"])
    parts = [f"{kinds[k]} {OFF[k]}{'s' * (kinds[k] > 1)}" for k in OFF if kinds[k]] + ([f"{views} image{'s' * (views > 1)} viewed"] if views else [])
    return "before it, off camera for %d:%02d: " % divmod(int(t1 - t0), 60) + (", ".join(parts) if parts else "thinking")


def panel(s: dict, e: dict, step: int, ending_now: bool, view: tuple | None, words: tuple | None, cmd: tuple | None,
          bar: tuple, key: Image.Image) -> Image.Image:
    """The right-hand side of one frame: where the session is, the command driving the robot and what changed in it,
    what the agent last said or thought, what the model last saw, and the session strip with the moment marked."""
    n, ms, graded = len(s["episodes"]), s["spec"]["max_steps"], e["ep"] == s["result"]["graded_ep"]
    clock = lambda t: "%02d:%02d" % divmod(int(max(t - s["a0"], 0)), 60)   # on the agent's clock
    now = when(e, step)
    img = Image.new("RGB", (W - H, H), BG)
    d, y = ImageDraw.Draw(img), 18
    family = B.family(s["task_name"])
    d.text((PAD, y), fit(f"{family} · limited · {s['model'].split('/')[-1]}", font(15), PW), font=font(15), fill=MUTED); y += 24
    d.text((PAD, y), f"ep{e['ep']}", font=font(36, True), fill=FG)
    d.text((PAD + d.textlength(f"ep{e['ep']} ", font=font(36, True)), y + 14), f"of {n}" + ("   ★ graded" if graded else ""),
           font=font(18), fill=GOLD if graded else MUTED); y += 50
    d.text((PAD, y), f"step {step}" + (f" / {ms}" if ms else "") + f"  ·  started at {clock(e['t0'] or s['a0'])}", font=font(18), fill=FG)
    if not e.get("exact"):
        d.text((PAD + d.textlength(f"step {step} / {ms}  ·  started at 00:00   ", font=font(18)), y + 3), "≈ replay", font=font(14), fill=MUTED)
    y += 30
    if ending_now:
        label, color = ending(e, s)
        label = fit(label, font(18, True), PW - 24)
        d.rounded_rectangle((PAD, y, PAD + d.textlength(label, font=font(18, True)) + 24, y + 30), 6, fill=color)
        d.text((PAD + 12, y + 5), label, font=font(18, True), fill="#ffffff")
    y += 42
    if cmd:
        c, background, first, prev, gap, total = cmd
        a, mono = c["attempt"], font(14, mono=True)
        eps = f"ep{first}" + (f"–{e['ep']}" if first != e["ep"] else "")
        head = f"ROBOT COMMAND {a['n']} OF {total}  ·  {clock(c['t0'])}  ·  {eps}" + ("  ·  left running" if background else "")
        d.text((PAD, y), fit(head, font(13, True), PW), font=font(13, True), fill=MUTED); y += 20
        d.text((PAD, y), fit(a["runs"], mono, PW), font=mono, fill=FG); y += 22
        note = ("the first command that moved the robot" if prev is None else f"same as command {a['n'] - 1}: a re-run"
                if a.get("same") else f"changed since command {a['n'] - 1}:" if a.get("changes") else "")
        if note:
            d.text((PAD, y), note, font=font(13), fill=MUTED); y += 19
        for kind, text in a.get("changes") or []:
            color = GREEN if kind == "+" or text.startswith("+ ") else RED if kind == "-" or text.startswith("− ") else \
                MUTED if kind == "…" else FG
            text = {"+": "+ ", "-": "− "}.get(kind, "") + text
            d.text((PAD + 10, y), fit(text, mono, PW - 10), font=mono, fill=color); y += 19
        if gap:
            d.text((PAD, y + 2), fit(gap, font(13), PW), font=font(13), fill=MUTED); y += 21
    y = max(y + 12, 330)
    if words:
        t, text, kind = words
        d.text((PAD, y), f"THE AGENT {'THOUGHT' if kind == 'think' else 'SAID'}  ·  {clock(t)}", font=font(13, True), fill=MUTED); y += 20
        rows = (428 - y) // 21
        lines = textwrap.wrap(" ".join(text.split()), width=int(PW / 9.4))
        if kind == "think" and len(lines) > rows:   # a thought ends with what it decided
            lines = ["… " + lines[-rows]] + lines[-rows + 1:]
        elif len(lines) > rows:
            lines = lines[:rows - 1] + [lines[rows - 1] + " …"]
        for line in lines:
            d.text((PAD, y), line, font=font(17), fill=FG); y += 21
    y = max(y + 10, 438)
    if view:
        v, pic = view
        d.text((PAD, y), f"THE MODEL LOOKED AT  ·  {clock(v['t'])}", font=font(13, True), fill=MUTED); y += 20
        img.paste(pic, (PAD, y))
    base, x = bar
    viewed = sum(v["t"] <= now for v in s["views"])
    d.text((PAD, STRIP_Y - 24), f"agent time {clock(now)} / {clock(s['a0'] + (s.get('budget_s') or 0))}   ·   "
                                f"resets used {e['ep']} / {s['spec']['reset_budget']}   ·   {viewed} images viewed", font=font(14), fill=FG)
    img.paste(base, (PAD, STRIP_Y))
    img.paste(key, (PAD, STRIP_Y + 62))
    eps = s["episodes"]
    t_end = max(e.get("t_end") or 0, e.get("t_last") or 0) or (eps[e["ep"] + 1]["t0"] if e["ep"] + 1 < len(eps) else s["a1"])
    d.rectangle((PAD + x(e["t0"] or s["a0"]) - 1, STRIP_Y - 1, PAD + max(x(t_end), x(e["t0"] or s["a0"]) + 1) + 1, STRIP_Y + 17), outline=FG)
    cx = PAD + x(now)
    d.line((cx, STRIP_Y - 4, cx, STRIP_Y + 38), fill=GOLD, width=2)
    return img


def main(report: str) -> None:
    s = json.load(open(f"{report}/summary.json"))
    at_key = lambda w: (w[2] if w[2] is not None else -1, w[3] if w[3] is not None else -1, w[0])   # [t, text, ep, step]
    words = latest([m[:4] + ["say"] for m in s["msgs"]] + [x[:4] + ["think"] for x in s.get("thinking") or [] if len(x) >= 4], key=at_key)
    seen = latest(s["views"], key=lambda v: (v["ep"], v["step"], v["t"]))
    cmds = sorted((c for c in s["calls"] if c.get("attempt")), key=lambda c: c["t0"])   # attempts.py: the calls that drove it
    started = latest(cmds, key=lambda c: c["t0"])
    before = {id(c): cmds[i - 1] if i else None for i, c in enumerate(cmds)}
    gaps = {id(c): offcamera(s, before[id(c)], c) for c in cmds}
    first = {}   # each command's first episode on screen
    bar, key = strip(s, PW), legend(s, PW)
    shown, poster, k = (None, 0), None, 0   # shown: the image up now, and the frame it went up at
    part = f"{report}/session.part.mp4"     # session.mp4 appears only once whole: collect.py caches it by existence
    with imageio.get_writer(part, fps=FPS, format="FFMPEG", codec="libx264", macro_block_size=1) as w:
        for e in (e for e in s["episodes"] if e.get("video")):
            clip_ = imageio.get_reader(os.path.join(report, e["video"]), format="FFMPEG")
            n = clip_.count_frames()   # frame by frame: a whole clip of 640x480 frames can take a GB
            for j, frame in enumerate(clip_):
                step = e["steps"] if j == n - 1 else j * e.get("video_every", B.video_every)
                at = (e["ep"], step, float("inf"))
                if (v := seen(at)) is not shown[0]:
                    shown = (v, k)
                view = (v, thumb(os.path.join(report, v["file"]))) if v and k - shown[1] < HOLD else None
                wd = words(at)
                c = started(when(e, step))           # the command the robot's steps came from: running then, or left behind
                if c is not None:
                    first.setdefault(id(c), e["ep"])
                cmd = (c, c["t1"] < when(e, step), first[id(c)], before[id(c)], gaps[id(c)], len(cmds)) if c else None
                out = Image.new("RGB", (W, H), BG)
                out.paste(ImageOps.pad(Image.fromarray(frame), (H, H), Image.BICUBIC, color=BG), (0, 0))   # square, or letterboxed
                out.paste(panel(s, e, step, j >= n - TAIL, view, (wd[0], wd[1], wd[4]) if wd else None, cmd, bar, key), (H, 0))
                w.append_data(np.asarray(out))
                if e["ep"] == s["result"]["graded_ep"] and j == int(0.6 * (n - 1)):
                    poster = out   # as the episodes' posters: late in the graded episode, before its end
                k += 1
            clip_.close()
    (poster or out).save(f"{report}/session.jpg", quality=90)
    os.replace(part, f"{report}/session.mp4")
    print(json.dumps({"session": "session.mp4", "frames": k, "seconds": round(k / FPS, 1)}))


if __name__ == "__main__":
    bench.use(sys.argv[2])
    main(sys.argv[1])
