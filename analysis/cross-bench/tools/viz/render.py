#!/usr/bin/env python3
"""Annotated replay of a standard-mode trial: the sim replay, synced to every command and look of the agent.

usage: render.py RAWDIR EVENTS.json OUT.mp4 [--from MM:SS --to MM:SS]
The replay has one frame per 25 physics steps (10 Hz at 250 Hz physics); each command's motion is the replay
between the physics step before it and the one its RESULT reports. The picture stops while the agent looks or
thinks; the clock shows the agent's wall-clock time.
"""
import argparse, json, os, re, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ap = argparse.ArgumentParser()
ap.add_argument("raw"); ap.add_argument("events"); ap.add_argument("out")
ap.add_argument("--from", dest="t0", default=None); ap.add_argument("--to", dest="t1", default=None)
ap.add_argument("--rate", type=float, default=20, help="replay frames per video second (replay is 10 Hz sim)")
ap.add_argument("--scale", type=int, default=1, help="2: 2560x1440 (the layout is designed at 1280x720)")
ap.add_argument("--views", help="frames rendered elsewhere: VIEWS/<camera>/<replay frame:04d>.png (else the replay grid)")
ap.add_argument("--service", help="the service's episode.jsonl: when each command's images were really taken")
ap.add_argument("--main-cam", default="world_camera1", help="the big view: an agent camera, or 'cinema' (a studio view from --views)")
ap.add_argument("--list-frames", help="write the replay frames the video uses (JSON) and stop after rendering")
args = ap.parse_args()

HERE = os.path.dirname(os.path.abspath(__file__))
FPS, LW, LH = 30, 1280, 720
K = args.scale
W, H = LW * K, LH * K
PHYS_PER_FRAME = 25
LIMIT_S = 1800
FONT = lambda n, w="SemiBold": ImageFont.truetype(f"{HERE}/fonts/Inter-{w}.ttf", n * K)
MONO = lambda n, w="Regular": ImageFont.truetype(f"{HERE}/fonts/JetBrainsMono-{w}.ttf", n * K)


class SD:
    """ImageDraw in layout coordinates (1280x720): every coordinate and width times K."""
    def __init__(self, im): self.d = ImageDraw.Draw(im)
    def _b(self, b): return [v * K for v in b]
    def rectangle(self, b, fill=None, outline=None, width=1): self.d.rectangle(self._b(b), fill=fill, outline=outline, width=width * K)
    def rounded_rectangle(self, b, r, fill=None): self.d.rounded_rectangle(self._b(b), r * K, fill=fill)
    def ellipse(self, b, fill=None): self.d.ellipse(self._b(b), fill=fill)
    def line(self, b, fill=None, width=1): self.d.line(self._b(b), fill=fill, width=width * K)
    def text(self, xy, s, font=None, fill=None): self.d.text(self._b(xy), s, font=font, fill=fill)
    def textlength(self, s, font=None): return self.d.textlength(s, font=font) / K
COL = {"MOVE": (79, 140, 255), "GRIP": (255, 159, 67), "LOOK": (255, 203, 71), "PIXELS → 3-D": (46, 196, 182),
       "WATCH": (167, 139, 250), "CODE": (156, 163, 175), "REJECTED": (255, 90, 95), "ERROR": (255, 90, 95),
       "SUCCESS": (34, 197, 94)}
TILE = {"world_camera1": (0, 0), "observer_camera": (0, 1), "head_camera": (0, 2), "front_camera": (1, 0),
        "left_camera": (1, 1), "right_camera": (1, 2)}
SIDE_LABEL = {"head_camera": "agent's head camera", "front_camera": "agent's front camera", "left_camera": "agent's left wrist",
              "right_camera": "agent's right wrist"}

# ---------- replay frames ----------
rp = os.path.join(args.raw, "verifier/replay.mp4")
buf = subprocess.run(["ffmpeg", "-v", "error", "-i", rp, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                     capture_output=True, check=True).stdout
V = np.frombuffer(buf, np.uint8).reshape(-1, 480, 960, 3)
NF = len(V)


def view(f, cam, size):
    """A frame rendered elsewhere (--views); every frame the video uses must exist."""
    return Image.open(os.path.join(args.views, cam, f"{min(f, NF - 1):04d}.png")).convert("RGB").resize(size, Image.LANCZOS)


def tile(f, cam):
    if args.views:
        return view(f, cam, (320 * K, 240 * K))
    r, c = TILE[cam]
    im = Image.fromarray(V[min(f, NF - 1), r * 240:(r + 1) * 240, c * 320:(c + 1) * 320])
    return im if K == 1 else im.resize((320 * K, 240 * K), Image.LANCZOS)


_main = {}


def main_view(f):
    if f not in _main:
        if len(_main) > 64:
            _main.clear()
        _main[f] = view(f, args.main_cam, (960 * K, 720 * K)) if args.views else \
            Image.fromarray(V[min(f, NF - 1), :240, :320]).resize((960 * K, 720 * K), Image.LANCZOS).filter(
                ImageFilter.UnsharpMask(radius=2 * K, percent=70, threshold=2))
    return _main[f]


# ---------- events -> beats ----------
ev = json.load(open(args.events))
looks_dir = os.path.join(os.path.dirname(os.path.abspath(args.events)), "looks")
traj = json.load(open(os.path.join(args.raw, "agent/trajectory.json")))["steps"]
error_steps = {s["step_id"] for s in traj for r in (s.get("observation") or {}).get("results", [])
               if "Traceback" in str(r.get("content", ""))}

queues = {"ee_pose": [], "joint_position": [], "obs": []}
saved_at = {e["n"]: e["t"] for e in ev if e["kind"] == "result"}   # run<NNN>/ = what result NNN saved (as the agent read it)
res_rows = {e["n"]: e["physics_steps"] for e in ev if e["kind"] == "result"}
if args.service:   # the true capture time: the service's own record of the call that reached those physics steps
    import datetime
    t_first = next(datetime.datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00")).timestamp()
                   for s in traj if s.get("source") == "agent")
    svc = [json.loads(line) for line in open(args.service)]
    done_ts = {e["call"]: e["ts"] for e in svc if e.get("ev") in ("submit", "observe")}
    by_rows = {e["rows"]: done_ts.get(e["call"]) for e in svc if e.get("ev") == "checkpoint"}
    saved_at = {n: by_rows[r] - t_first if by_rows.get(r) else saved_at[n] for n, r in res_rows.items()}


def taken(path):
    m = re.search(r"/run(\d+)/", path)
    return saved_at.get(int(m.group(1))) if m else 0.0 if "/initial/" in path else None


def taken_frame(path):
    m = re.search(r"/run(\d+)/", path)
    return round(res_rows[int(m.group(1))] / PHYS_PER_FRAME) if m and int(m.group(1)) in res_rows else None
for e in ev:
    if e["kind"] == "result":
        queues[e["type"]].append(e)


def mmss(t):
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def fnum(x):
    try:
        return f"{float(eval(x, {'np': np})):.2f}"
    except Exception:
        return x.strip()


def describe(cmd):
    """(tag, title, arm, result_type) for one command line."""
    arm_name = {"l": "left", "r": "right"}
    m = re.match(r"move\('(\w)',\[([^\]]+)\],(\[[^\]]*\]|[^,()]+)(?:,([^)]+))?\)", cmd)
    if m:
        xyz = ", ".join(fnum(x) for x in m.group(2).split(","))
        g = m.group(4)
        grip = {"1": " · open", "0": " · closed"}.get((g or "").strip(), f" · gripper {fnum(g)}" if g else "")
        return "MOVE", f"{arm_name[m.group(1)]} hand to ({xyz}){grip}", m.group(1), "ee_pose"
    m = re.match(r"grip\('(\w)',([^)]+)\)", cmd)
    if m:
        g = m.group(2).strip()
        what = {"0": "close", "1": "open"}.get(g, f"open to {fnum(g)}")
        return "GRIP", f"{arm_name[m.group(1)]} gripper · {what}", m.group(1), "joint_position"
    m = re.match(r"points\('(\w+)',\[(.*)\]\)", cmd)
    if m:
        n = m.group(2).count("(")
        return "PIXELS → 3-D", f"{n} pixels picked on the {m.group(1).replace('_', ' ')}, depth → world xyz", None, None
    if cmd.startswith("save(r.get_obs"):
        s = re.search(r"seconds=([\d.]+)", cmd)
        return "WATCH", f"hold still {s.group(1) if s else ''} s, grab cameras + depth", None, "obs"
    return "CODE", "set a variable / patch a helper", None, None


beats = []  # each: dict(t, frames(list of replay idx) or hold n, state updates)
cur_f = 0
counts = {"MOVE": 0, "GRIP": 0, "LOOK": 0}
for i, e in enumerate(ev):
    if e["kind"] == "say":
        beats.append({"t": e["t"], "say": e["text"], "hold": int(0.7 * FPS)})
    elif e["kind"] == "look":
        imgs = [(p.split("/")[-1][:-4], os.path.join(looks_dir, f), taken(p)) for p, f in zip(e["paths"], e["files"])]
        if not imgs:
            continue
        counts["LOOK"] += 1
        cams = ", ".join(c for c, _, _ in imgs)
        frames_seen = [taken_frame(p) for p in e["paths"]]
        moved_on = any(x is not None and x < cur_f for x in frames_seen)   # a command sent before these came back
        beats.append({"t": e["t"], "look": imgs, "count": dict(counts), "moved_on": moved_on,
                      "hold": int((1.2 if len(imgs) == 1 else 1.6) * FPS),
                      "chip": ("LOOK", f"agent views {len(imgs)} image{'s' if len(imgs) > 1 else ''}", cams)})
    elif e["kind"] == "cmd":
        tag, title, arm, rtype = describe(e["text"])
        b = {"t": e["t"], "chip": (tag, title, e["text"]), "arm": arm}
        if rtype:
            if rtype == "joint_position" and e["step"] in error_steps:
                beats.append(dict(b, hold=int(0.9 * FPS), chip=("ERROR", "command raised an error, nothing sent", e["text"])))
                continue
            r = queues[rtype].pop(0)
            if tag in counts:
                counts[tag] += 1
            f_to = min(round(r["physics_steps"] / PHYS_PER_FRAME), NF - 1)
            frames = list(range(cur_f, f_to + 1))
            n = max(int(len(frames) / args.rate * FPS), int(0.7 * FPS))
            b.update(count=dict(counts), motion=(cur_f, f_to), hold=n)
            beats.append(b)
            cur_f = f_to
            fails = [a for a, s in r["plan"] if s != "Success" and arm and a == {"l": "left", "r": "right"}[arm]]
            if fails:
                beats.append({"t": r["t"], "hold": int(1.0 * FPS), "arm": arm,
                              "chip": ("REJECTED", f"planner found no path · {fails[0]} arm did not move", e["text"])})
            if r["done"]:
                beats.append({"t": r["t"], "hold": int(3.5 * FPS), "chip": ("SUCCESS", "service reports success: all three bottles in the bin", ""), "end": True})
        else:
            beats.append(dict(b, hold=int((0.8 if tag == "PIXELS → 3-D" else 0.35) * FPS)))

# wall clock runs from each beat's time to the next one's
for a, b in zip(beats, beats[1:]):
    a["t1"] = max(b["t"], a["t"])
beats[-1]["t1"] = beats[-1]["t"]
end_t = next(b["t"] for b in beats if b.get("end"))
beats = beats[:next(i for i, b in enumerate(beats) if b.get("end")) + 1]
beats[-1]["t1"] = beats[-1]["t"]

t_from = sum(int(x) * k for x, k in zip(args.t0.split(":"), (60, 1))) if args.t0 else None
t_to = sum(int(x) * k for x, k in zip(args.t1.split(":"), (60, 1))) if args.t1 else None

# ticks for the timeline bar
ticks = []
for b in beats:
    if "chip" in b and b["chip"][0] in ("MOVE", "GRIP", "LOOK", "REJECTED"):
        ticks.append((b["t"], b["chip"][0]))


# ---------- drawing ----------
def rrect(d, box, r, fill):
    d.rounded_rectangle(box, r, fill=fill)


def wrap(text, font, width, d):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if d.textlength(test, font=font) <= width:
            cur = test
        else:
            lines.append(cur); cur = w
    return lines + [cur] if cur else lines


F_CLOCK, F_SMALL, F_SAY, F_TAG, F_TITLE = FONT(40, "Bold"), FONT(17), FONT(22), FONT(18, "Bold"), FONT(27)
F_CODE, F_LABEL, F_COUNT = MONO(18), FONT(15), FONT(19)


def draw(f, clock, st, age, look=None, look_age=0, intro=None, mode=None, moved_on=False):
    img = Image.new("RGB", (W, H), (12, 15, 20))
    mv = main_view(f)
    if look is not None:
        mv = Image.blend(mv, Image.new("RGB", mv.size, (0, 0, 0)), 0.38)
    img.paste(mv, (0, 0))
    wrist = "left_camera" if st.get("arm") == "l" else "right_camera"
    looked = {c for c, _, _ in look} if look else set()
    for k, cam in enumerate(["head_camera", "front_camera", wrist]):
        y = k * 240
        img.paste(tile(f, cam), (960 * K, y * K))
    o = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = SD(o)
    for k, cam in enumerate(["head_camera", "front_camera", wrist]):
        y = k * 240
        rrect(d, (968, y + 8, 968 + d.textlength(SIDE_LABEL[cam], font=F_LABEL) + 16, y + 32), 8, (10, 14, 20, 170))
        d.text((976, y + 11), SIDE_LABEL[cam], font=F_LABEL, fill=(230, 233, 239))
        if cam in looked:
            d.rectangle((961, y + 1, 1278, y + 238), outline=COL["LOOK"] + (255,), width=5)
    d.line((960, 0, 960, LH), fill=(12, 15, 20, 255), width=2)
    if args.main_cam in looked:
        d.rectangle((2, 2, 957, LH - 3), outline=COL["LOOK"] + (255,), width=5)
    if args.main_cam == "cinema":   # say so: the agent never saw this view
        lab = "studio view · not seen by the agent"
        rrect(d, (16, 120, 16 + d.textlength(lab, font=F_LABEL) + 16, 144), 8, (10, 14, 20, 150))
        d.text((24, 123), lab, font=F_LABEL, fill=(200, 205, 212))

    # clock + counters (top-left)
    rrect(d, (16, 16, 336, 112), 14, (10, 14, 20, 190))
    d.text((32, 22), mmss(clock), font=F_CLOCK, fill=(255, 255, 255))
    d.text((32 + d.textlength(mmss(clock), font=F_CLOCK) + 10, 42), f"/ {mmss(LIMIT_S)} agent time", font=F_SMALL, fill=(170, 176, 186))
    c = st.get("count", {"MOVE": 0, "GRIP": 0, "LOOK": 0})
    x = 32
    for tag, name in (("MOVE", "move"), ("GRIP", "grip"), ("LOOK", "look")):
        d.ellipse((x, 85, x + 10, 95), fill=COL[tag])
        s = f"{name} {c[tag]}"
        d.text((x + 15, 78), s, font=F_COUNT, fill=(230, 233, 239))
        x += 15 + d.textlength(s, font=F_COUNT) + 18

    # agent's own words (top, right of the clock)
    if st.get("say") and age["say"] < 6.0 * FPS:
        a = min(1, age["say"] / 6) * (1 if age["say"] < 5.5 * FPS else max(0, (6.0 * FPS - age["say"]) / (0.5 * FPS)))
        lines = wrap("“" + st["say"] + "”", F_SAY, 562, d)[:4]
        h = 34 + 30 * len(lines)
        rrect(d, (350, 16, 944, 16 + h), 14, (10, 14, 20, int(190 * a)))
        d.text((366, 22), "AGENT", font=F_TAG, fill=(170, 176, 186, int(255 * a)))
        for k, ln in enumerate(lines):
            d.text((366, 46 + 30 * k), ln, font=F_SAY, fill=(255, 255, 255, int(255 * a)))

    # command chip (bottom)
    if st.get("chip"):
        tag, title, code = st["chip"]
        a = min(1, age["chip"] / 5)
        col = COL[tag]
        y0 = LH - 40 - (88 if code else 56) + int((1 - a) * 12)
        rrect(d, (16, y0, 944, LH - 40), 14, (10, 14, 20, int(210 * a)))
        tw = d.textlength(tag, font=F_TAG)
        rrect(d, (30, y0 + 13, 30 + tw + 22, y0 + 43), 9, col + (int(255 * a),))
        d.text((41, y0 + 17), tag, font=F_TAG, fill=(12, 15, 20, int(255 * a)))
        d.text((30 + tw + 36, y0 + 11), title, font=F_TITLE, fill=(255, 255, 255, int(255 * a)))
        if code:
            code = code if len(code) <= 82 else code[:80] + "…"
            d.text((32, y0 + 54), "> " + code, font=F_CODE, fill=(150, 160, 175, int(255 * a)))
    # robot / agent status, a small pill above the chip's right end
    if mode:
        label = {"move": "robot moving · 2×", "hold": "robot holds · agent thinking", "look": "robot holds · agent looking"}[mode]
        lw = d.textlength(label, font=F_SMALL)
        ys = LH - 40 - (88 if st.get("chip") and st["chip"][2] else 56 if st.get("chip") else 0) - 40
        rrect(d, (944 - lw - 40, ys, 944, ys + 30), 15, (10, 14, 20, 200))
        dot = (34, 197, 94) if mode == "move" else COL["LOOK"] if mode == "look" else (170, 176, 186)
        d.ellipse((944 - lw - 26, ys + 10, 944 - lw - 16, ys + 20), fill=dot + (255,))
        d.text((944 - lw - 10, ys + 5), label, font=F_SMALL, fill=(230, 233, 239))

    # timeline (bottom strip)
    d.rectangle((0, LH - 28, 959, LH), fill=(10, 14, 20, 225))
    x0, x1, yb = 16, 944, LH - 14
    span = LIMIT_S
    d.line((x0, yb, x1, yb), fill=(70, 76, 88, 255), width=2)
    for t, tag in ticks:
        x = x0 + (x1 - x0) * t / span
        hh = 7 if tag == "LOOK" else 5
        d.line((x, yb - hh, x, yb + hh), fill=COL[tag] + ((255,) if t <= clock else (90,)), width=2)
    px = x0 + (x1 - x0) * min(clock, span) / span
    d.line((x0, yb, px, yb), fill=(235, 238, 243, 255), width=3)
    d.ellipse((px - 6, yb - 6, px + 6, yb + 6), fill=(255, 255, 255, 255))

    img = Image.alpha_composite(img.convert("RGBA"), o)

    # what the agent looked at
    if look:
        a = min(1, look_age / 6)
        n = len(look)
        size = (560, 420) if n == 1 else (420, 315) if n == 2 else (290, 218) if n == 3 else (230, 172)
        cols = n if n <= 3 else 2
        rows = (n + cols - 1) // cols
        gw, gh = cols * size[0] + (cols - 1) * 18, rows * (size[1] + 34) + (rows - 1) * 14
        ox, oy = (960 - gw) // 2, 130 + (480 - gh) // 2 if n <= 3 else 150
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = SD(layer)
        forms = (lambda c, w: f"agent saw · {c}{w}", lambda c, w: f"{c}{w}", lambda c, w: c)
        when = lambda t_img: (f" · taken {mmss(t_img)}, {round(clock - t_img)} s earlier" if t_img is not None
                              and clock - t_img >= 1 else f" · taken {mmss(t_img)}" if t_img is not None else "")  # noqa: E731
        form = next((fm for fm in forms if all(ld.textlength(fm(c, when(t)), font=F_TAG) <= size[0] - 4
                                                for c, _, t in look)), forms[-1])   # one label style per group
        for k, (cam, fn, t_img) in enumerate(look):
            r_, c_ = divmod(k, cols)
            x, y = ox + c_ * (size[0] + 18), oy + r_ * (size[1] + 48) + int((1 - a) * 16)
            pic = Image.open(fn).convert("RGB").resize((size[0] * K, size[1] * K), Image.LANCZOS)
            ld.rounded_rectangle((x - 5, y + 29, x + size[0] + 5, y + 34 + size[1] + 5), 10, fill=COL["LOOK"] + (255,))
            layer.paste(pic, (x * K, (y + 34) * K))
            lab = form(cam, when(t_img))
            ld.rounded_rectangle((x - 5, y, x + ld.textlength(lab, font=F_TAG) + 19, y + 28), 8, fill=COL["LOOK"] + (255,))
            ld.text((x + 6, y + 4), lab, font=F_TAG, fill=(12, 15, 20))
        if moved_on:
            note = "The robot has moved since: the agent sent its next command before this image came back."
            ny = oy + (rows - 1) * (size[1] + 48) + 34 + size[1] - 34   # inside the last row's bottom edge
            ld.rounded_rectangle((ox - 5, ny, ox + ld.textlength(note, font=F_LABEL) + 17, ny + 26), 8, fill=(10, 14, 20, 220))
            ld.text((ox + 6, ny + 4), note, font=F_LABEL, fill=COL["LOOK"] + (255,))
        if a < 1:
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * a)))
        img = Image.alpha_composite(img, layer)

    if intro:
        a = intro
        layer = Image.new("RGBA", (W, H), (8, 10, 14, int(215 * a)))
        ld = SD(layer)
        fa = int(255 * a)
        ld.text((80, 200), "Direct control", font=FONT(64, "Bold"), fill=(255, 255, 255, fa))
        for k, ln in enumerate(["The agent is the policy. It sends one command to the robot,",
                                "looks at the cameras, and then decides the next one."]):
            ld.text((80, 300 + 40 * k), ln, font=FONT(30, "Regular"), fill=(220, 224, 230, fa))
        ld.text((80, 420), "RoboTwin 2.0 · put three bottles in the dustbin · GPT-6 Astra · standard mode",
                font=FONT(22), fill=(170, 176, 186, fa))
        ld.text((80, 456), "Robot motion at 2× speed. The picture stops while the agent looks or thinks;",
                font=FONT(20, "Regular"), fill=(140, 146, 156, fa))
        ld.text((80, 484), "the clock shows the agent's real time.", font=FONT(20, "Regular"), fill=(140, 146, 156, fa))
        img = Image.alpha_composite(img, layer)
    return img.convert("RGB")


# ---------- render ----------
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                        "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", args.out], stdin=subprocess.PIPE)
st, age = {}, {"say": 999, "chip": 999}
used = set()
f = 0
written = 0
started = t_from is None


def emit(im):
    global written
    enc.stdin.write(im.tobytes()); written += 1


if t_from is None:  # title card over the first frame
    for k in range(int(3.2 * FPS)):
        a = 1 if k < 2.6 * FPS else max(0, (3.2 * FPS - k) / (0.6 * FPS))
        emit(draw(0, 0, st, age, intro=a))

for b in beats:
    if "say" in b:
        st["say"] = b["say"]; age["say"] = 0
    if "chip" in b:
        st["chip"] = b["chip"]; age["chip"] = 0
    if b.get("arm"):
        st["arm"] = b["arm"]
    if "count" in b:
        st["count"] = b["count"]
    in_window = (t_from is None or b["t"] >= t_from) and (t_to is None or b["t"] <= t_to)
    n = b["hold"]
    m0, m1 = b.get("motion", (f, f))
    for k in range(n):
        if "motion" in b:
            f = m0 + round((m1 - m0) * min(1, k / max(1, (m1 - m0) / args.rate * FPS)))
        clock = b["t"] if b.get("look") else b["t"] + (b["t1"] - b["t"]) * k / n   # the clock stops on a look
        moving = "motion" in b and m1 > m0 and k < (m1 - m0) / args.rate * FPS
        mode = None if b.get("end") else "look" if b.get("look") else "move" if moving else "hold"
        if in_window:
            used.add(f)
            emit(draw(f, clock, st, age, look=b.get("look"), look_age=k, mode=mode, moved_on=b.get("moved_on", False)))
        age["say"] += 1; age["chip"] += 1
    f = m1
    if b.get("look"):
        st["chip"] = None
enc.stdin.close(); enc.wait()
print(f"{args.out}: {written} frames, {written / FPS:.1f} s; success at {mmss(end_t)}")
if args.list_frames:
    json.dump(sorted(used), open(args.list_frames, "w"))
    print(f"{len(used)} replay frames used: {min(used)}..{max(used)}")
