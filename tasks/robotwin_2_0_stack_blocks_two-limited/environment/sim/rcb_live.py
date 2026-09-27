"""Live episode recorder for the limited-mode sim service (runs inside the sidecar; the agent never sees its output).

While physics runs (a /submit chunk or an /observe watch window) it grabs a six-view grid every `250 / fps` physics
steps, stamps it with what the agent asked for (call id, action type, rows, note) plus simulated and wall-clock time,
and appends it to a fragmented MP4 that stays playable even if the container is killed mid-episode. The agent's
thinking time is not recorded (physics does not advance then). In mode "moving" (default) frames are also skipped while
nothing in the scene moves, so long settled watch windows collapse to a frame or two.

Files (all under the sidecar's /data):
  live.mp4               the recording (fragmented MP4, H.264)
  live_timeline.jsonl    one line per written frame: frame index, wall time, sim step, call id, label
Config (environment): RCB_LIVE = moving | active | off, RCB_LIVE_FPS (default 10, frames per simulated second),
RCB_LIVE_SIZE (per-camera tile, default 213x160), RCB_LIVE_MOVE_EPS (default 1e-3).
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
            except Exception: pass
    return ImageFont.load_default()


class LiveRecorder:
    def __init__(self, session, data_dir: str = "/data", t0: float | None = None):
        self.S = session
        self.mode = os.environ.get("RCB_LIVE", "moving").strip().lower()
        self.fps = max(1, int(float(os.environ.get("RCB_LIVE_FPS", "10"))))
        w, h = (int(x) for x in os.environ.get("RCB_LIVE_SIZE", "213x160").lower().split("x"))
        self.size = (w, h); self.eps = float(os.environ.get("RCB_LIVE_MOVE_EPS", "1e-3"))
        self.every = max(1, PHYS_HZ // self.fps)
        self.path = os.path.join(data_dir, "live.mp4"); self.tl_path = os.path.join(data_dir, "live_timeline.jsonl")
        self.t0 = t0 or time.time(); self.n_steps = 0; self.n_frames = 0; self.n_skipped = 0; self.label = "start"
        self.call = 0; self._last_vec = None; self._w = None; self._font = None; self.error = None
        self.enabled = self.mode in ("moving", "active")

    # ---- control
    def set_label(self, call: int, label: str) -> None:
        self.call = int(call); self.label = label

    def open(self) -> None:
        if not self.enabled: return
        try:
            import imageio.v2 as imageio
            self._w = imageio.get_writer(self.path, format="FFMPEG", mode="I", fps=self.fps, codec="libx264", macro_block_size=1,
                                         output_params=["-movflags", "frag_keyframe+empty_moov+default_base_moof", "-pix_fmt", "yuv420p",
                                                        "-g", str(self.fps * 2)])
            self._font = _font()
            self.frame(force=True)
        except Exception as exc:  # noqa: BLE001 — recording must never break the episode
            self.error = repr(exc); self.enabled = False

    def close(self) -> dict:
        if self._w is not None:
            try: self.frame(force=True)
            except Exception: pass
            try: self._w.close()
            except Exception as exc: self.error = repr(exc)
            self._w = None
        return {"live_video": self.n_frames > 0 and self.error is None, "live_frames": self.n_frames, "live_skipped": self.n_skipped,
                "live_mode": self.mode, "live_fps": self.fps, "live_error": self.error}

    # ---- per physics step (called by the server after every S.step())
    def tick(self) -> None:
        if not self.enabled or self._w is None: return
        self.n_steps += 1
        if self.n_steps % self.every: return
        if self.mode == "moving":
            v = self.S._state_vector()
            if self._last_vec is not None and v.shape == self._last_vec.shape and float(np.max(np.abs(v - self._last_vec))) < self.eps:
                self.n_skipped += 1; return
        self.frame()

    def frame(self, force: bool = False) -> None:
        if self._w is None: return
        try:
            img = self.S.render_grid(CAMS, cols=3, size=self.size)[..., :3]
            img = self._stamp(np.ascontiguousarray(img))
            self._w.append_data(img)
            if self.mode == "moving": self._last_vec = self.S._state_vector()
            sim = int(self.S._sim_steps)
            with open(self.tl_path, "a") as f:
                f.write(json.dumps({"frame": self.n_frames, "wall_s": round(time.time() - self.t0, 3), "sim_step": sim,
                                    "sim_s": round(sim / PHYS_HZ, 3), "call": self.call, "label": self.label, "forced": force}) + "\n")
            self.n_frames += 1
        except Exception as exc:  # noqa: BLE001
            self.error = repr(exc); self.enabled = False

    def _stamp(self, img: np.ndarray) -> np.ndarray:
        from PIL import Image, ImageDraw
        sim = int(self.S._sim_steps); wall = time.time() - self.t0
        text = f"call {self.call}  {self.label}   sim {sim / PHYS_HZ:7.2f}s   wall {int(wall // 60):02d}:{wall % 60:05.2f}"
        bar = 18
        canvas = Image.new("RGB", (img.shape[1], img.shape[0] + bar), (20, 20, 20))
        canvas.paste(Image.fromarray(img), (0, bar))
        ImageDraw.Draw(canvas).text((4, 2), text[:120], fill=(235, 235, 235), font=self._font)
        out = np.asarray(canvas)
        return out[: out.shape[0] // 2 * 2, : out.shape[1] // 2 * 2]   # H.264 needs even dimensions
