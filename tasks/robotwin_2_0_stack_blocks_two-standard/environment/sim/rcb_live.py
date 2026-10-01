"""Episode recording for the standard-mode sim service (runs inside the sidecar; the agent never sees its output).

Produces /data/live.mp4: a six-view grid of the episode, every frame stamped with what the agent had sent (call id,
action type, rows, note) plus simulated and wall-clock time, sampled only while physics runs (a /submit chunk or an
/observe watch window; the agent's thinking time takes no frames) and, in the default "moving" filter, skipped while
nothing in the scene moves.

Two capture modes (RCB_LIVE):
  replay (default)  During the episode only the call boundaries are logged (physics-step ranges, wall-clock times),
                    which costs nothing. At episode end the recorded trajectory is replayed once (the simulation is
                    bit-exact deterministic, so this is the same motion) and rendered. Zero overhead for the agent;
                    if the container dies first, /data/trajectory_live.f64 + /data/live_segments.jsonl still allow
                    rendering it offline.
  realtime          Frames are rendered while the episode runs (crash-proof video, but each frame costs ~150 ms of the
                    agent's wall clock: a 10 s chunk takes ~4x longer).
  off               No live.mp4.
Other knobs: RCB_LIVE_FILTER = moving | all, RCB_LIVE_FPS (default 10 frames per simulated second),
RCB_LIVE_SIZE (per-camera tile, default 213x160), RCB_LIVE_MOVE_EPS (default 1e-3), RCB_LIVE_MAX_FRAMES (default 1500), RCB_LIVE_BUDGET_S (replay mode:
rendering stops after this many seconds and the video ends there, default 240; live_truncated reports it).

Files: live.mp4 (fragmented MP4), live_timeline.jsonl (one line per frame: frame, wall_s, sim_step, sim_s, call, label),
live_segments.jsonl (one line per call: call, label, step0, step1, wall0, wall1).
"""
from __future__ import annotations
import json, os, time
import numpy as np

PHYS_HZ = 250
CAMS = ("world_camera1", "observer_camera", "head_camera", "front_camera", "left_camera", "right_camera")


def _font():
    from PIL import ImageFont
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(p):
            try: return ImageFont.truetype(p, 13)
            except Exception: pass  # noqa: BLE001
    return ImageFont.load_default()


class _Writer:
    def __init__(self, path, fps):
        import imageio.v2 as imageio
        self.w = imageio.get_writer(path, format="FFMPEG", mode="I", fps=fps, codec="libx264", macro_block_size=1,
                                    output_params=["-movflags", "frag_keyframe+empty_moov+default_base_moof", "-pix_fmt", "yuv420p", "-g", str(fps * 2)])
        self.font = _font()

    def add(self, img, text):
        from PIL import Image, ImageDraw
        bar = 18; canvas = Image.new("RGB", (img.shape[1], img.shape[0] + bar), (20, 20, 20))
        canvas.paste(Image.fromarray(np.ascontiguousarray(img[..., :3])), (0, bar))
        ImageDraw.Draw(canvas).text((4, 2), text[:130], fill=(235, 235, 235), font=self.font)
        out = np.asarray(canvas); self.w.append_data(out[: out.shape[0] // 2 * 2, : out.shape[1] // 2 * 2])

    def close(self):
        self.w.close()


def _text(call, label, sim_step, wall):
    return f"wall {int(wall // 60):02d}:{wall % 60:04.1f}  sim {sim_step / PHYS_HZ:6.1f}s  #{call} {label}"


class LiveRecorder:
    def __init__(self, session, data_dir: str = "/data", t0: float | None = None):
        self.S = session; self.dir = data_dir
        self.mode = os.environ.get("RCB_LIVE", "replay").strip().lower()
        self.filter = os.environ.get("RCB_LIVE_FILTER", "moving").strip().lower()
        self.fps = max(1, int(float(os.environ.get("RCB_LIVE_FPS", "10"))))
        w, h = (int(x) for x in os.environ.get("RCB_LIVE_SIZE", "213x160").lower().split("x"))
        self.size = (w, h); self.eps = float(os.environ.get("RCB_LIVE_MOVE_EPS", "1e-3"))
        self.max_frames = int(os.environ.get("RCB_LIVE_MAX_FRAMES", "1500"))
        self.budget_s = float(os.environ.get("RCB_LIVE_BUDGET_S", "240"))   # replay mode: stop rendering after this long
        self.every = max(1, PHYS_HZ // self.fps)
        self.path = os.path.join(data_dir, "live.mp4"); self.tl_path = os.path.join(data_dir, "live_timeline.jsonl")
        self.seg_path = os.path.join(data_dir, "live_segments.jsonl")
        self.t0 = t0 or time.time(); self.call = 0; self.label = "start"; self.seg = None
        self.n_frames = 0; self.n_skipped = 0; self.error = None; self._w = None; self._last = None; self._n = 0
        self.enabled = self.mode in ("replay", "realtime")

    # ---- during the episode
    def open(self) -> None:
        if self.mode == "realtime":
            try:
                self._w = _Writer(self.path, self.fps); self._frame(force=True)
            except Exception as exc:  # noqa: BLE001 — recording must never break the episode
                self.error = repr(exc); self._w = None

    def set_label(self, call: int, label: str) -> None:
        """A new call starts: close the previous segment, open one for this call."""
        self._end_seg()
        self.call = int(call); self.label = label
        self.seg = {"call": self.call, "label": label, "step0": int(self.S._sim_steps), "wall0": round(time.time() - self.t0, 3)}

    def end_call(self) -> None:
        """The call's physics is over: close its segment now, so idle time before the next call is not attributed to it."""
        self._end_seg()

    def _end_seg(self) -> None:
        if self.seg is None: return
        self.seg.update(step1=int(self.S._sim_steps), wall1=round(time.time() - self.t0, 3))
        if self.seg["step1"] > self.seg["step0"]:
            try:
                with open(self.seg_path, "a") as f: f.write(json.dumps(self.seg) + "\n")
            except OSError: pass
        self.seg = None

    def tick(self) -> None:
        if self.mode != "realtime" or self._w is None: return
        self._n += 1
        if self._n % self.every == 0: self._frame()

    def _moving(self) -> bool:
        if self.filter != "moving": return True
        v = self.S._state_vector()
        if self._last is not None and v.shape == self._last.shape and float(np.max(np.abs(v - self._last))) < self.eps:
            return False
        self._last = v; return True

    def _frame(self, force: bool = False) -> None:
        try:
            if not force and not self._moving(): self.n_skipped += 1; return
            if force and self.filter == "moving": self._last = self.S._state_vector()
            wall = time.time() - self.t0; sim = int(self.S._sim_steps)
            self._w.add(self.S.render_grid(CAMS, cols=3, size=self.size), _text(self.call, self.label, sim, wall))
            self._log(sim, wall, self.call, self.label)
        except Exception as exc:  # noqa: BLE001
            self.error = repr(exc); self._w = None

    def _log(self, sim, wall, call, label):
        with open(self.tl_path, "a") as f:
            f.write(json.dumps({"frame": self.n_frames, "wall_s": round(wall, 3), "sim_step": sim, "sim_s": round(sim / PHYS_HZ, 3), "call": call, "label": label}) + "\n")
        self.n_frames += 1

    # ---- at episode end (before the verification replay)
    def close(self) -> dict:
        self._end_seg()
        if self._w is not None:
            try: self._frame(force=True); self._w.close()
            except Exception as exc: self.error = repr(exc)  # noqa: BLE001
            self._w = None
        return self.info()

    def info(self) -> dict:
        return {"live_video": self.n_frames > 0 and self.error is None, "live_frames": self.n_frames, "live_skipped": self.n_skipped,
                "live_mode": self.mode, "live_fps": self.fps, "live_error": self.error, "live_truncated": bool(getattr(self, "truncated", False))}

    def render_from_trajectory(self, acts: np.ndarray) -> dict:
        """Replay mode: rebuild the episode from the recorded trajectory and render the labelled video.
        Frames are sampled only inside call segments (physics that the agent caused), every `every` steps."""
        if self.mode != "replay": return self.info()
        try:
            segs = [json.loads(l) for l in open(self.seg_path)] if os.path.exists(self.seg_path) else []
        except Exception: segs = []  # noqa: BLE001
        every = max(self.every, int(np.ceil(len(acts) / max(1, self.max_frames))))
        try:
            self.S.reset(); w = _Writer(self.path, self.fps); self._last = None
            def seg_at(step):
                for sg in segs:
                    if sg["step0"] < step <= sg["step1"]: return sg
                return None
            def wall_at(sg, step):
                span = max(1, sg["step1"] - sg["step0"]); return sg["wall0"] + (sg["wall1"] - sg["wall0"]) * (step - sg["step0"]) / span
            w.add(self.S.render_grid(CAMS, cols=3, size=self.size), _text(0, "start", 0, 0.0)); self._log(0, 0.0, 0, "start")
            if self.filter == "moving": self._last = self.S._state_vector()
            t_start = time.time(); self.truncated = False
            for i, row in enumerate(np.asarray(acts, dtype=np.float64)):
                if time.time() - t_start > self.budget_s: self.truncated = True; break
                self.S.step(row); step = i + 1
                if step % every and step != len(acts): continue
                sg = seg_at(step)
                if sg is None and step != len(acts): continue
                if step != len(acts) and not self._moving(): self.n_skipped += 1; continue
                call, label = (sg["call"], sg["label"]) if sg else (self.call, "end")
                wall = wall_at(sg, step) if sg else (segs[-1]["wall1"] if segs else 0.0)
                w.add(self.S.render_grid(CAMS, cols=3, size=self.size), _text(call, label, step, wall)); self._log(step, wall, call, label)
            w.close()
        except Exception as exc:  # noqa: BLE001
            self.error = repr(exc)
        return self.info()
