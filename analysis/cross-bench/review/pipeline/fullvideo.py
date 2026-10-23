"""The whole trial as one annotated video on the agent's wall clock (code only, no model).

Robot motion comes from the graded replay (verifier/replay.mp4). The service log (service/K/episode.jsonl) says when
each call ran and how many physics steps it took, so every replay frame gets its wall time. The output is a list of
beats: `move` (a call that ran physics: its replay frames at native speed), `call` (a call without physics, 0.3 s),
`idle` (the agent only thinking: the last frame held, the gap compressed to [0.25, 1] s). Every output frame gets an
overlay (Band): clock, the agent's last message and current action, the robot call, the image the agent last
received, the recap mark near this moment, and a strip of the whole trial. Steps before the last reset are not in
the replay and show a placeholder. The manifest (fullvideo/K.json: beats as [video s0, s1, wall min0, min1, kind])
lets the review page map video time and wall time both ways.
usage: python -m pipeline video [--keys K ...] [--max-idle 1.0]  ->  fullvideo/K.mp4, K.jpg (poster), K.json (manifest)"""
from __future__ import annotations
import argparse, bisect, json, os, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .paths import DATA, RAW, FONT, FONT_BOLD, FONT_INDEX, keys, load, jdump
from .logs import stamp, agent_t0
from .sync import duration

FPS, BAND = 25, 176
SQUEEZE, IDLE_MIN, IDLE_MAX, CALL_S = 40.0, 0.25, 1.0, 0.3    # an idle gap of g s plays for g/40 s within [0.25, 1] s
MARK = {"progress": (31, 138, 76), "failure": (210, 58, 44), "decision": (232, 113, 10), "no_return": (20, 20, 20)}
KIND = {"message": "消息", "thought": "推理", "shell": "命令", "write": "写文件", "read": "读文件", "image": "看图", "plan": "计划", "other": "工具"}
INK, MUTE, BLUE, BG = (27, 29, 33), (102, 107, 115), (42, 120, 214), (248, 249, 251)


def calls(episode: list[dict]) -> list[dict]:
    """One row per service call: wall start/end (absolute s), physics steps, a short label; resets marked."""
    out, open_ = [], {}
    for e in episode:
        ev, ts = e.get("ev"), float(e["ts"])
        if ev == "call_begin":
            open_[e.get("call")] = {"call": e.get("call"), "path": e.get("path", ""), "t0": ts, "t1": ts, "steps": 0, "label": e.get("path", "").strip("/")}
        elif ev == "call_end":
            c = next((c for c in reversed(list(open_.values())) if c["path"] == e.get("path")), None)
            if c:
                c["t1"] = ts
                out.append(open_.pop(c["call"]))
        elif e.get("call") in open_:
            c = open_[e["call"]]
            if isinstance(e.get("physics_steps"), int) and ev != "observe":
                c["steps"] += e["physics_steps"]
            if ev == "submit":
                c["label"] = f"submit {e.get('type', '')} ×{e.get('rows', '')}".strip()
            if ev in ("reset", "episode_start", "new_episode"):
                c["label"], c["reset"] = "reset", True
    return sorted(out, key=lambda c: c["t0"])


def beats(cs: list[dict], nframes: int, t_start: float, t_end: float) -> list[tuple]:
    """[(kind, frame0, frame1, wall0, wall1)] in absolute seconds; frame None = not in the replay."""
    last_reset = max((i for i, c in enumerate(cs) if c.get("reset")), default=-1)
    total = sum(c["steps"] for c in cs[last_reset + 1:]) or 1
    out, cum, prev = [], 0, t_start
    for i, c in enumerate(cs):
        f_now = round(cum / total * (nframes - 1)) if i > last_reset else None
        if c["t0"] > prev:
            out.append(("idle", f_now, f_now, prev, c["t0"]))
        if c["steps"] and i > last_reset:
            f1 = round((cum + c["steps"]) / total * (nframes - 1))
            out.append(("move", f_now, f1, c["t0"], c["t1"]))
            cum += c["steps"]
        else:
            out.append(("call", f_now, f_now, c["t0"], c["t1"]))
        prev = max(prev, c["t1"])
    f_end = round(cum / total * (nframes - 1))
    if t_end > prev:
        out.append(("idle", f_end, f_end, prev, t_end))
    return out


def frames_of(kind: str, fa, fb, wa: float, wb: float, max_idle: float = IDLE_MAX) -> int:
    """Output frames of one beat; max_idle 0 drops the thinking pauses (the beat stays in the manifest, 0 s long)."""
    if kind == "move":
        return max(1, fb - fa)
    if kind == "idle":
        return 0 if max_idle <= 0 else max(1, round(min(max_idle, max(IDLE_MIN, (wb - wa) / SQUEEZE)) * FPS))
    return max(1, round(CALL_S * FPS))


def marks(recap: dict | None) -> list[tuple]:
    """(minute, kind, text) from a checked recap: progress steps, failures, decisions, the point of no return."""
    if not recap:
        return []
    t = lambda q: (q or {}).get("t")
    out = [(t(s.get("ev")), "progress", f"进展 第{s.get('level')}级：{s.get('what', '')}") for s in recap["progress"]["steps"]]
    out += [(t(f.get("ev")), "failure", f"{'主因' if f.get('primary') else '失败'}：{f.get('what', '')}") for f in recap["failures"]]
    out += [(t(d.get("decision")), "decision", f"决定：{d.get('what', '')}") for d in recap["decisions"] if d.get("ok")]
    nr = recap.get("no_return") or {}
    if nr.get("type") not in (None, "none"):
        out.append((t(nr.get("ev")), "no_return", f"不可挽回：{nr.get('note', '')}"))
    return [m for m in out if m[0] is not None]


class Replay:
    """Sequential frame reader (indices never go back)."""
    def __init__(self, mp4: str):
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height", "-of", "csv=p=0", mp4],
                           capture_output=True, text=True)
        self.w, self.h = map(int, r.stdout.strip().split(",")[:2])
        self.p = subprocess.Popen(["ffmpeg", "-v", "quiet", "-i", mp4, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        self.i, self.cur = -1, np.zeros((self.h, self.w, 3), np.uint8)

    def frame(self, i: int) -> np.ndarray:
        while self.i < i:
            buf = self.p.stdout.read(self.w * self.h * 3)
            if len(buf) < self.w * self.h * 3:
                break
            self.cur, self.i = np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3), self.i + 1
        return self.cur

    def close(self):
        self.p.kill(); self.p.wait()


class Band:
    """Draws everything that is not the replay picture onto one output frame."""
    def __init__(self, key: str, ev: list[dict], mk: list[tuple], budget: float, span: float, pic_w: int, pic_h: int):
        self.key, self.ev, self.mk, self.budget, self.span, self.pw, self.ph = key, ev, mk, budget, span, pic_w, pic_h
        self.times = [e["t"] if e["t"] is not None else 0 for e in ev]
        self.msgs = [i for i, e in enumerate(ev) if e["kind"] == "message"]
        self.looks, self.cache = load(f"{DATA}/looks/{key}/index.json", {}), {}
        self.big, self.txt, self.small = (ImageFont.truetype(FONT_BOLD, 20, index=FONT_INDEX), ImageFont.truetype(FONT, 17, index=FONT_INDEX),
                                          ImageFont.truetype(FONT, 14, index=FONT_INDEX))

    @staticmethod
    def fit(d, text, font, width):
        if d.textlength(text, font=font) <= width:
            return text
        while text and d.textlength(text + "…", font=font) > width:
            text = text[:-1]
        return text + "…"

    def look(self, i: int):
        """the newest image the agent received up to event i (within 2 minutes), as a thumbnail"""
        for e in reversed(self.ev[max(0, i - 12):i + 1]):
            if e["id"] in self.looks and (e["t"] or 0) >= (self.ev[i]["t"] or 0) - 2:
                if e["id"] not in self.cache:
                    im = Image.open(f"{DATA}/looks/{self.key}/{self.looks[e['id']][0]}")
                    self.cache[e["id"]] = im.resize((240, round(im.height * 240 / im.width)))
                return self.cache[e["id"]]
        return None

    def draw(self, img: Image.Image, m: float, label: str):
        d, W = ImageDraw.Draw(img), img.width
        i = max(0, bisect.bisect_right(self.times, m) - 1)
        e = self.ev[i]
        th = self.look(i)
        if th is not None:                                         # picture-in-picture: what the agent saw
            img.paste(th, (self.pw - th.width - 10, 10))
            d.rectangle((self.pw - th.width - 10, 10 + th.height, self.pw - 10, 30 + th.height), fill=INK)
            d.text((self.pw - th.width - 4, 12 + th.height), "agent 看到的画面", font=self.small, fill=(255, 255, 255))
        y = self.ph + 10                                           # band: clock, event, robot call
        d.text((14, y), f"{stamp(m)} / {stamp(self.budget)}", font=self.big, fill=INK)
        d.text((150, y + 3), f"{KIND.get(e['kind'], e['kind'])} {e['id']}", font=self.txt, fill=MUTE)
        if label:
            tw = d.textlength(label, font=self.txt)
            d.rounded_rectangle((W - tw - 34, y, W - 14, y + 28), 8, fill=BLUE)
            d.text((W - tw - 24, y + 3), label, font=self.txt, fill=(255, 255, 255))
        mi = bisect.bisect_right(self.msgs, i) - 1                 # what it last said, what it is doing
        if mi >= 0:
            d.text((14, y + 34), self.fit(d, "说：" + " ".join(self.ev[self.msgs[mi]]["text"].split()), self.txt, W - 28), font=self.txt, fill=INK)
        if e["kind"] != "message":
            cmd = next((l.strip() for l in (e["text"] or "").splitlines() if l.strip()), "")
            d.text((14, y + 60), self.fit(d, "做：" + cmd, self.txt, W - 28), font=self.txt, fill=(80, 86, 96))
        near = [x for x in self.mk if abs(x[0] - m) <= 0.4]          # the recap mark near this moment
        if near:
            _, kind, text = min(near, key=lambda x: abs(x[0] - m))
            text = self.fit(d, text, self.txt, W - 60)
            d.rounded_rectangle((10, 10, min(W - 10, 30 + d.textlength(text, font=self.txt)), 44), 8, fill=MARK[kind])
            d.text((20, 14), text, font=self.txt, fill=(255, 255, 255))
        ys, x0, x1 = self.ph + 124, 14, W - 14                     # strip of the whole trial
        d.rounded_rectangle((x0, ys, x1, ys + 10), 5, fill=(227, 229, 233))
        d.rounded_rectangle((x0, ys, x0 + (x1 - x0) * min(1, m / self.span), ys + 10), 5, fill=BLUE)
        for tm, kind, _ in self.mk:
            x = x0 + (x1 - x0) * min(1, tm / self.span)
            d.ellipse((x - 4, ys - 9, x + 4, ys - 1), fill=MARK[kind])
        d.text((x0, ys + 14), "进展 ● 绿 · 失败 ● 红 · 决定 ● 橙 · 不可挽回 ● 黑", font=self.small, fill=MUTE)


def render(k: str, recaps: str = "verified_recaps", max_idle: float = IDLE_MAX) -> float:
    episode = [json.loads(l) for l in open(f"{DATA}/service/{k}/episode.jsonl")]
    ev = [json.loads(l) for l in open(f"{DATA}/events/{k}.jsonl")]
    fx = json.load(open(f"{DATA}/facts/{k}.json"))
    mp4 = f"{RAW}/{k}/verifier/replay.mp4"
    t0, cs = agent_t0(k), calls(episode)
    end_abs = t0 + 60 * (fx.get("used_min") or (ev[-1]["t"] or 0))
    bs = beats(cs, round(duration(mp4) * FPS), t0, max(end_abs, cs[-1]["t1"] if cs else end_abs))
    rd = Replay(mp4)
    W, H = rd.w + rd.w % 2, rd.h + BAND + (rd.h + BAND) % 2
    budget = fx.get("budget_min") or (end_abs - t0) / 60
    band = Band(k, ev, marks(load(f"{DATA}/{recaps}/{k}.json")), budget, max(budget, (end_abs - t0) / 60), rd.w, rd.h)
    placeholder = Image.new("RGB", (rd.w, rd.h), (40, 44, 52))
    ImageDraw.Draw(placeholder).text((rd.w // 2, rd.h // 2), "这一段在最后一次 reset 之前，不在评分回放里", font=band.txt, fill=(220, 220, 220), anchor="mm")
    path = f"{DATA}/fullvideo/{k}"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-movflags", "+faststart", f"{path}.mp4"], stdin=subprocess.PIPE)
    manifest, v = [], 0.0
    for kind, fa, fb, wa, wb in bs:
        n = frames_of(kind, fa, fb, wa, wb, max_idle)
        manifest.append([round(v, 3), round(v + n / FPS, 3), round((wa - t0) / 60, 3), round((wb - t0) / 60, 3), kind])
        label = next((c["label"] for c in cs if c["t0"] <= wa <= c["t1"] + 1e-6), "") if kind != "idle" else ""
        for j in range(n):
            img = Image.new("RGB", (W, H), BG)
            img.paste(placeholder if fa is None else Image.fromarray(rd.frame(fa + (j if kind == "move" else 0))), (0, 0))
            band.draw(img, (wa + (wb - wa) * j / n - t0) / 60, label)
            out.stdin.write(img.tobytes())
        v += n / FPS
    out.stdin.close(); out.wait(); rd.close()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(round(v / 3, 2)), "-i", f"{path}.mp4", "-frames:v", "1", f"{path}.jpg"])
    jdump({"key": k, "fps": FPS, "duration": round(v, 3), "beats": manifest}, f"{path}.json")
    print(f"全程视频 {v:.1f} s，{len(manifest)} 段，标记 {len(band.mk)} 个  {k}")
    return v


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline video")
    ap.add_argument("--keys", nargs="*")
    ap.add_argument("--recaps", default="verified_recaps")
    ap.add_argument("--max-idle", type=float, default=IDLE_MAX, help="longest thinking pause in the video (s); 0 drops them")
    a = ap.parse_args(argv)
    for k in keys(a.keys):
        if os.path.exists(f"{DATA}/service/{k}/episode.jsonl") and os.path.exists(f"{RAW}/{k}/verifier/replay.mp4"):
            render(k, a.recaps, a.max_idle)
        else:
            print(f"没有服务端记录或回放，跳过  {k}")
