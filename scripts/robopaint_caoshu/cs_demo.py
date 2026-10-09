#!/usr/bin/env python3
"""Review demo of a RoboPaint pair's reference solution (run in the base image, GPU for the cameras): replays
solution/oracle_qpos.npy from the graders' copy of the instance and writes
  <out>/<slug>_demo.mp4   target.png | the exact main sheet as it is written | scene_cam (the robot), one frame every 2 control steps
  <out>/<slug>_final.png  target.png | the reference's sheet | overlay (black both, green missing, red extra)
    python cs_demo.py <task dir (privileged)> <out dir>
"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw

task, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(task, "tests"))
os.environ.setdefault("RCB_SESSION_LOG", "")
import rcb_brush_strict as S  # noqa: E402
import imageio.v2 as imageio  # noqa: E402

slug = os.path.basename(task.rstrip("/")).replace("robopaint-caoshu-", "").replace("-i00-privileged", "")
os.makedirs(out, exist_ok=True)
s = S.Session(instance=os.path.join(task, "tests", "instance.json"), render=True)
A = np.load(os.path.join(task, "solution", "oracle_qpos.npy")).astype(np.float32)
tgt = np.asarray(Image.open(os.path.join(task, "tests", "target.png")).convert("RGB"))
T = 512


def tile(img, w=T, h=T):
    im = Image.fromarray(img)
    im.thumbnail((w, h), Image.LANCZOS)
    c = Image.new("RGB", (w, h), (255, 255, 255))
    c.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return c


def frame(step):
    canv = s.canvas("main")
    cam = s.render_frame("scene_cam")
    row = Image.new("RGB", (3 * T, T + 28), (250, 247, 240))
    row.paste(tile(tgt), (0, 28)); row.paste(tile(canv), (T, 28)); row.paste(tile(cam), (2 * T, 28))
    d = ImageDraw.Draw(row)
    d.text((8, 8), f"target.png ({slug})", fill=(60, 60, 60))
    d.text((T + 8, 8), f"main sheet, control step {step} / {len(A)}, contacts {sum(1 for x in s.painter.strokes if x['sheet'] == 'main' and x['inked'])}", fill=(60, 60, 60))
    d.text((2 * T + 8, 8), "scene_cam", fill=(60, 60, 60))
    return np.asarray(row)


s.reset()
path = os.path.join(out, f"{slug}_demo.mp4")
with imageio.get_writer(path, fps=20, format="FFMPEG", codec="libx264", macro_block_size=1, quality=7) as w:
    w.append_data(frame(0))
    for i, a in enumerate(A):
        s.step(a)
        if (i + 1) % 2 == 0 or i == len(A) - 1:
            if i == len(A) - 1:
                s.painter.finish()
            w.append_data(frame(i + 1))
    last = frame(len(A))
    for _ in range(30):
        w.append_data(last)
m = s.score()
ink = s.ink("main") >= 0.5
G = s.truth.mask
ov = np.full(G.shape + (3,), 255, np.uint8); ov[G & ink] = (35, 35, 35); ov[G & ~ink] = (60, 180, 60); ov[ink & ~G] = (220, 50, 50)
fin = Image.new("RGB", (3 * T, T + 28), (250, 247, 240))
fin.paste(tile(tgt), (0, 28)); fin.paste(tile(s.canvas("main")), (T, 28)); fin.paste(tile(ov), (2 * T, 28))
d = ImageDraw.Draw(fin)
d.text((8, 8), "target.png", fill=(60, 60, 60))
d.text((T + 8, 8), f"reference solution: IoU {m['iou']:.3f}  BF {m['boundary_f']:.3f}  min region {m['min_stroke_coverage']:.3f}", fill=(60, 60, 60))
d.text((2 * T + 8, 8), f"overlay: black both, green missing, red extra; strokes {int(m['n_strokes'])}/{int(m['max_strokes'])}", fill=(60, 60, 60))
fin.save(os.path.join(out, f"{slug}_final.png"))
Image.fromarray(s.canvas("main")).save(os.path.join(out, f"{slug}_oracle_canvas.png"))
json.dump({k: m[k] for k in ("success", "image_success", "strict_ok", "iou", "boundary_f", "min_stroke_coverage", "stray_frac", "n_strokes",
                             "max_strokes", "path_mm", "max_path_mm", "mark_width_mm", "min_mark_width_mm", "longest_stroke_mm") if k in m},
          open(os.path.join(out, f"{slug}_metrics.json"), "w"), indent=1)
print(json.dumps({"slug": slug, "video": path, "frames": len(A) // 2 + 31, "success": m["success"], "iou": m["iou"]}))
s.close()
