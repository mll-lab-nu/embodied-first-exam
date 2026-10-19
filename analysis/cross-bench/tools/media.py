#!/usr/bin/env python3
"""Replay media for reviews and the site (needs `fetch.py --media` first).

usage: tools/media.py frames KEY...   # $RAW/KEY/frames/f1..f6.jpg (even spacing, last = final frame), for deep reviews
       BEL_TOKEN=... tools/media.py ensure KEY...   # fetch the replay if the server has one, then `video`; without a
                                      # replay, fetch one image the agent saved (artifacts/app/output) as KEY.agent.<ext>
       tools/media.py video KEY...    # $XB_MEDIA/KEY.mp4 (<= 640 px, 15 fps, CRF 32, at most 40 s: longer replays play
                                      # faster, the speed-up is written to KEY.json) and KEY.jpg poster, for case pages
"""
from __future__ import annotations
import glob, json, os, subprocess, sys
from common import RAW

MEDIA = os.environ.get("XB_MEDIA", "/data/pingyue/cross-bench/media")


def replay(key: str) -> str | None:
    for p in ("verifier/replay.mp4", "artifacts/data/replay.mp4", "artifacts/out/replay.mp4"):
        if os.path.exists(os.path.join(RAW, key, p)):
            return os.path.join(RAW, key, p)
    return None


def duration(src: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def frames(key: str, n: int = 6) -> str:
    src = replay(key)
    if not src:
        return "no replay"
    d = os.path.join(RAW, key, "frames")
    os.makedirs(d, exist_ok=True)
    dur = duration(src)
    for i in range(n):
        t = max(dur * (i + 1) / n - 0.05, 0)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1",
                        "-vf", "scale='min(640,iw)':-2", os.path.join(d, f"f{i + 1}.jpg")], check=False)
    return f"{len(glob.glob(os.path.join(d, '*.jpg')))} frames"


def video(key: str) -> str:
    src = replay(key)
    if not src:
        return "no replay"
    os.makedirs(MEDIA, exist_ok=True)
    dst = os.path.join(MEDIA, key + ".mp4")
    if not os.path.exists(dst):
        speed = max(1.0, duration(src) / 40)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", f"setpts=PTS/{speed:.3f},scale='min(640,iw)':-2,fps=15",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "32", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                        "-an", dst + ".part.mp4"], check=True)
        json.dump({"speed": round(speed, 1)}, open(os.path.join(MEDIA, key + ".json"), "w"))
        os.replace(dst + ".part.mp4", dst)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.1", "-i", dst, "-frames:v", "1", "-vf", "scale=480:-2",
                        os.path.join(MEDIA, key + ".jpg")], check=False)
    return f"{os.path.getsize(dst) // 1000} KB"


def ensure(key: str) -> str:
    import fetch, bel
    from common import read_csv
    if os.path.exists(os.path.join(MEDIA, key + ".mp4")):
        return "have video"
    row = next((t for t in read_csv("trials.csv") if t["key"] == key), None)
    if not row:
        return "unknown key"
    if not replay(key):
        fetch.fetch(row, media=True)
    if replay(key):
        return video(key)
    detail = json.load(open(os.path.join(RAW, key, "trial.json")))["detail"]
    imgs = [p for p in detail.get("files", []) if p.startswith("artifacts/app/output/") and p.lower().endswith((".png", ".jpg", ".jpeg"))]
    if not imgs:
        return "no replay, no image"
    pick = next((p for p in imgs if any(w in p.lower() for w in ("final", "result", "last", "end"))), imgs[-1])
    ext = os.path.splitext(pick)[1].lower()
    os.makedirs(MEDIA, exist_ok=True)
    open(os.path.join(MEDIA, key + ".agent" + ext), "wb").write(bel.get_file(row["id"], pick))
    return f"agent image {pick}"


if __name__ == "__main__":
    fn = {"frames": frames, "video": video, "ensure": ensure}[sys.argv[1]]
    for k in sys.argv[2:]:
        print(k, fn(k))
