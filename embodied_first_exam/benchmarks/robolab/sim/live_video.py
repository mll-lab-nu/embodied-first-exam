"""The live video of a standard-mode episode (owner 2026-10-17: the standard modes are graded by the live
episode, so no replay films the trial any more): the sim service keeps frames of the episode it actually runs, from
images its simulator renders anyway, and the collect hook encodes them into live.mp4 after the verdict is written.
Nothing here decides anything: a frame that cannot be taken or written stops the video, never the control step, and an
encode that fails or runs out of time costs the video only.

In the service (a frame is taken only when the step opens a new slot, so most steps cost one integer division):

    import live_video
    V = live_video.LiveVideo(DATA, ctrl_hz=CTRL_HZ, frame=lambda: <uint8 (H, W, 3), or None: nothing rendered here>)
    V.offer(step)     # after every executed control step (also the steps a crash-recovery resume replays)
    V.truncate(step)  # after a resume: drop the frames of the call that was lost in the crash (rolled back)
    V.last(step)      # once, when the episode is over: the end state (`frame=` a callable that renders it if needed)

Frames are JPEG files <data>/live_video/<step>.jpg, written whole (a temporary file + rename): they survive a crash of
the service, and a resume that replays the journal skips the slots already on disk. A slot is `every` control steps
(ctrl_hz / FPS, 5 frames per simulated second); past MAX_FRAMES slots the slot doubles and the frames that no longer
open one are deleted, so a long episode becomes a time lapse of at most MAX_FRAMES frames (bounded disk, memory and
encode time whatever the episode's length).

In the collect hook, after final.json holds the verdict (CPU only, no simulator):

    python live_video.py encode <data dir> [--fps 5]   -> <data>/live.mp4 + live.last.png; one JSON line on stdout

The video is sim-time true at FPS frames per simulated second while the slot is `every` control steps (each slot shows
the newest frame taken by then, so a slot with no frame repeats the previous one), a time lapse after it doubled."""
from __future__ import annotations
import io, json, os, sys, time, traceback

FPS = 5                    # frames per simulated second (one slot = ctrl_hz / FPS control steps)
MAX_FRAMES = 3000          # slots one video may have: past it the slot doubles (a time lapse)
JPEG_QUALITY = 85
DIR = "live_video"


class LiveVideo:
    def __init__(self, data: str, ctrl_hz: float, frame, fps: int = FPS, max_frames: int = MAX_FRAMES, log=None):
        self.dir = os.path.join(data, DIR); self.frame = frame; self.max = int(max_frames); self.log = log
        self.base = max(1, int(round(float(ctrl_hz) / max(1, int(fps)))))
        self.every = self.base; self.kept: dict[int, int] = {}; self.error: str | None = None
        try:
            os.makedirs(self.dir, exist_ok=True)
            # the slot's base size, for the encode when no last.json is written (a service that never reached its dump)
            _write_json(os.path.join(self.dir, "meta.json"), {"base": self.base, "ctrl_hz": float(ctrl_hz), "fps": int(fps)})
            steps = sorted(int(f[:-4]) for f in os.listdir(self.dir) if f.endswith(".jpg") and f[:-4].isdigit())
            if steps:                            # a restarted service: the frames taken before the crash stay
                self._fit(steps[-1])
                self.kept = {s: s for s in steps}    # regrouped into slots of the current size by _thin()
            self._thin()
        except Exception as exc:  # noqa: BLE001 -- the video never stops the service
            self._fail(exc)

    def _fail(self, exc: BaseException) -> None:
        self.error = repr(exc)[:300]
        traceback.print_exc()
        if self.log:
            try:
                self.log({"ev": "live_video_stopped", "error": self.error})
            except Exception:  # noqa: BLE001
                pass

    def _fit(self, step: int) -> None:
        while step // self.every + 1 > self.max:
            self.every *= 2

    def _thin(self) -> None:
        """Keep the earliest frame of every slot of the current size; delete the rest."""
        keep: dict[int, int] = {}
        for s in sorted(self.kept.values()):
            keep.setdefault(s // self.every, s)
        for s in set(self.kept.values()) - set(keep.values()):
            try:
                os.remove(os.path.join(self.dir, f"{s:09d}.jpg"))
            except OSError:
                pass
        self.kept = keep

    def _write(self, name: str, img) -> None:
        from PIL import Image
        import numpy as np
        a = np.ascontiguousarray(np.asarray(img)[..., :3].astype(np.uint8))
        buf = io.BytesIO(); Image.fromarray(a).save(buf, format="JPEG", quality=JPEG_QUALITY)
        p = os.path.join(self.dir, name); tmp = f"{p}.{os.getpid()}.tmp"
        with open(tmp, "wb") as f:
            f.write(buf.getvalue())
        os.replace(tmp, p)

    def offer(self, step: int) -> None:
        """After an executed control step: a frame if `step` opens a slot that has none yet and `frame()` gives one."""
        if self.error is not None:
            return
        try:
            step = int(step)
            if step // self.every + 1 > self.max:
                self._fit(step); self._thin()
            slot = step // self.every
            if slot in self.kept:
                return
            img = self.frame()
            if img is None:                      # nothing rendered at this step: a later step of the slot may give one
                return
            self._write(f"{step:09d}.jpg", img)
            self.kept[slot] = step
        except Exception as exc:  # noqa: BLE001 -- a camera or disk problem ends the video, never the control step
            self._fail(exc)

    def truncate(self, step: int) -> None:
        """After a crash-recovery resume: the journal was replayed only up to the last checkpoint (the call in flight was
        lost and rolled back), so frames taken past `step` show states that no longer belong to the episode: delete them."""
        try:
            for slot, s in list(self.kept.items()):
                if s > int(step):
                    try:
                        os.remove(os.path.join(self.dir, f"{s:09d}.jpg"))
                    except OSError:
                        pass
                    del self.kept[slot]
            for n in ("last.jpg", "last.json"):              # a dump before the crash: its end state was rolled back too
                try:
                    os.remove(os.path.join(self.dir, n))
                except OSError:
                    pass
        except Exception as exc:  # noqa: BLE001
            self._fail(exc)

    def last(self, step: int, frame=None) -> None:
        """The end state (when the episode is over): the video's last frame and live.last.png. `frame`: a callable that
        renders the end state if `frame()` may give nothing there (a service that renders on demand)."""
        if self.error is not None:
            return
        try:
            img = (frame or self.frame)()
            if img is not None:
                self._write("last.jpg", img)
                _write_json(os.path.join(self.dir, "last.json"), {"step": int(step), "every": self.every, "base": self.base})
        except Exception as exc:  # noqa: BLE001
            self._fail(exc)


def _write_json(path: str, obj: dict) -> None:
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def _read_json(path: str) -> dict:
    try:
        v = json.load(open(path))
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def encode(data: str, fps: int = FPS) -> dict:
    """<data>/live_video/*.jpg -> <data>/live.mp4 (H.264, yuv420p) + live.last.png. The result: video (the mp4's path or
    None), frames (taken), slots (in the video), every (control steps per slot), error."""
    import numpy as np
    from PIL import Image
    import imageio.v2 as imageio
    d = os.path.join(data, DIR); out = os.path.join(data, "live.mp4"); t0 = time.time()
    names = sorted(f for f in os.listdir(d) if f.endswith(".jpg") and f[:-4].isdigit()) if os.path.isdir(d) else []
    steps = [int(f[:-4]) for f in names]
    meta = {**_read_json(os.path.join(d, "meta.json")), **_read_json(os.path.join(d, "last.json"))}
    last = os.path.join(d, "last.jpg") if os.path.exists(os.path.join(d, "last.jpg")) else None
    if not steps and not last:
        return {"video": None, "frames": 0, "slots": 0, "every": None, "error": "no frame was taken"}
    base = int(meta.get("base") or 1); end = max(steps + [int(meta.get("step") or 0)])
    every = max(base, int(meta.get("every") or base))
    while end // every + 1 > MAX_FRAMES:
        every *= 2
    by_slot: dict[int, str] = {}
    for s, n in zip(steps, names):
        by_slot.setdefault(s // every, n)
    size = None
    def load(path):
        nonlocal size
        im = Image.open(path).convert("RGB")
        if size is None:
            size = (im.width - im.width % 2, im.height - im.height % 2)   # yuv420p wants even sides
        if im.size != size:
            im = im.resize(size)
        return np.asarray(im)
    tmp = os.path.join(data, "live.part.mp4"); n_slots = 0; cur = None; last_img = None
    try:
        with imageio.get_writer(tmp, format="FFMPEG", mode="I", fps=int(fps), codec="libx264", macro_block_size=1,
                                pixelformat="yuv420p", output_params=["-movflags", "+faststart"]) as w:
            first = min(by_slot) if by_slot else None
            for slot in (range(first, end // every + 1) if first is not None else ()):
                if slot in by_slot:
                    cur = load(os.path.join(d, by_slot[slot]))
                w.append_data(cur); n_slots += 1
            if last:
                last_img = load(last); w.append_data(last_img); n_slots += 1
        Image.fromarray(last_img if last_img is not None else cur).save(os.path.join(data, "live.last.png"))
        os.replace(tmp, out)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        try:
            os.remove(tmp)
        except OSError:
            pass
        return {"video": None, "frames": len(steps), "slots": n_slots, "every": every, "error": repr(exc)[:300]}
    return {"video": out, "frames": len(steps) + (1 if last else 0), "slots": n_slots, "every": every,
            "fps": int(fps), "encode_s": round(time.time() - t0, 1), "error": None}


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "encode":
        fps = int(a[a.index("--fps") + 1]) if "--fps" in a else FPS
        try:
            res = encode(a[1], fps)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc(); res = {"video": None, "error": repr(exc)[:300]}
        print(json.dumps(res), flush=True)
        sys.exit(0 if res.get("video") else 1)
    print("usage: live_video.py encode <data dir> [--fps N]")
    sys.exit(2)
