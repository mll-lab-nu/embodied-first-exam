#!/usr/bin/env python3
"""QA picture of a caoshu exemplar against its scan: the scan crop with the target's outline (red) and the selection box (grey),
next to the target as the agent will see it; a strip of warnings (ink touching the crop edge = a clipped stroke, dash joints).
    python cs_qa.py --spec exemplars.json --slug wen --exemplar work/wen --source-dir <dir> --out wen_qa.png
"""
import argparse, json, os
import numpy as np
import cv2
from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True); ap.add_argument("--slug", required=True); ap.add_argument("--exemplar", required=True)
    ap.add_argument("--source-dir", required=True); ap.add_argument("--out", required=True); ap.add_argument("--height", type=int, default=900)
    a = ap.parse_args()
    spec = json.load(open(a.spec, encoding="utf-8"))
    t = next(x for x in spec["targets"] if x["slug"] == a.slug)
    st = json.load(open(os.path.join(a.exemplar, f"{a.slug}.contacts.json"), encoding="utf-8"))["stats"]
    X0, Y0, X1, Y1 = st["source_crop"]
    scan = Image.open(os.path.join(a.source_dir, spec["source"]["file"])).convert("RGB").crop((X0, Y0, X1, Y1))
    ink = np.asarray(Image.open(os.path.join(a.exemplar, f"{a.slug}_ink.png")).convert("L")) < 128     # em raster
    A = np.asarray(st["transform"], np.float64)
    Ainv = cv2.invertAffineTransform(A)
    k = 4                                                        # the outline on a 4x crop grid (smooth)
    Ak = Ainv.copy(); Ak *= 1.0; S = np.array([[k, 0, 0], [0, k, 0], [0, 0, 1]], np.float64)
    M = (S @ np.vstack([Ainv, [0, 0, 1]]))[:2]
    back = cv2.warpAffine(ink.astype(np.uint8) * 255, M, (scan.width * k, scan.height * k), flags=cv2.INTER_LINEAR) >= 128
    cs, _ = cv2.findContours(back.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    big = scan.resize((scan.width * k, scan.height * k), Image.LANCZOS)
    d = ImageDraw.Draw(big)
    for c in cs:
        pts = [tuple(p[0]) for p in c]
        if len(pts) > 2:
            d.line(pts + [pts[0]], fill=(230, 20, 20), width=k)
    bx = t["box"]
    d.rectangle([(bx[0] - X0) * k, (bx[1] - Y0) * k, (bx[2] - X0) * k, (bx[3] - Y0) * k], outline=(140, 140, 140), width=k)
    sc = a.height / big.height
    left = big.resize((int(big.width * sc), a.height), Image.LANCZOS)
    tgt = Image.fromarray(np.where(ink, 20, 248).astype(np.uint8)).convert("RGB")
    bb = np.argwhere(ink); r0, c0 = bb.min(0); r1, c1 = bb.max(0)
    m = 30
    tgt = tgt.crop((max(0, c0 - m), max(0, r0 - m), min(1024, c1 + m), min(1024, r1 + m)))
    tgt = tgt.resize((int(tgt.width * a.height / tgt.height), a.height), Image.LANCZOS)
    W = Image.new("RGB", (left.width + tgt.width + 30, a.height + 60), (255, 255, 255))
    W.paste(left, (0, 60)); W.paste(tgt, (left.width + 30, 60))
    d = ImageDraw.Draw(W)
    warn = []
    if st.get("touches_edge"):
        warn.append("INK TOUCHES THE CROP EDGE (a stroke may be clipped)")
    d.text((6, 6), f"{a.slug} {st['chars']}: contacts {st['n_contacts']}, regions {st['n_regions']}, dash joints {st.get('joints', 0)}; "
                   f"scan {st['src_bbox_rc'][1] - st['src_bbox_rc'][0]} px tall, {st['scale_em_per_src_px']} em/px", fill=(0, 0, 0))
    d.text((6, 24), "left: scan with the target outline (red), selection box (grey); right: target.png as the agent sees it", fill=(60, 60, 60))
    d.text((6, 42), " / ".join(warn) if warn else "no ink at the crop edge", fill=(200, 0, 0) if warn else (0, 120, 0))
    W.save(a.out)
    print(a.out, "warnings:", warn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
