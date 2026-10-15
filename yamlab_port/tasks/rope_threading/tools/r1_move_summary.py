"""Helpers for r1_move_eval results: step flags (loose / strict), displacement metric, one-line row."""
import numpy as np

STEPS = ("ready", "pick", "transition", "R3_feed", "R3_recv", "R3_hand", "R2_feed", "R2_recv", "R2_hand", "R1_feed", "R2_to_R1", "geometry", "entry_side")


def arms(d):
    return {k for k, v in d.items() if v > 0}


def flags(o, strict):
    """-> {step: bool}. R2_recv: static probe (either arm); strict also needs the cone-20 stroke (stroke_diag, 0.07..0.20 m) > 0.
    R2_to_R1: an arm that receives at R2 also feeds R1 (same arm continues), or a receiver->feeder pair of different arms clears."""
    tr = o["transition"].get("0.0", {})
    pr = {s[0]: o["R2_probe"][s]["poses"] for s in ("left", "right")}
    cs = {s: o["R2_recv_cone20"][s]["poses"] for s in ("l", "r")}
    rec = arms(pr) if not strict else (arms(pr) & arms(cs))
    f1 = arms(o["R1_feed"])
    pairs = sum(o["R2recv_R1feed_pairs"].values())
    g = o["geo"]
    return dict(ready=o["ready_ok"], pick=o["pick_ok"], transition=bool(tr.get("ok")),
                R3_feed=sum(o["R3_feed"].values()) > 0, R3_recv=sum(o["R3_recv"].values()) > 0, R3_hand=sum(o["R3_hand"].values()) > 0,
                R2_feed=sum(o["R2_feed"].values()) > 0, R2_recv=bool(rec), R2_hand=sum(o["R2_hand"].values()) > 0,
                R1_feed=bool(f1), R2_to_R1=bool(rec & f1) or (bool(rec) and pairs > 0),
                geometry=bool(g["fits"] and g["base_gap_min"] >= 0.02 and min(g["ring_gap"].values()) >= 0.02),
                entry_side=bool(g.get("r2_to_r1plane_normal", 1) > 0.02 and g.get("r3_to_r2_entry", 1) > 0.02))


def first_fail(f):
    return next((s for s in STEPS if not f[s]), None)


def disp(spec):
    """(sum of ring displacements in m, sum of |rot| deg)"""
    return sum(float(np.hypot(v[0], v[1])) for v in spec.values()), sum(abs(v[2]) for v in spec.values())


def label(spec):
    return "；".join("%s(%+.0f,%+.0f)cm %+.0f°" % (k, v[0] * 100, v[1] * 100, v[2]) for k, v in spec.items())


def lr(d):
    return "%d/%d" % (d["l"] if "l" in d else d["left"], d["r"] if "r" in d else d["right"])
