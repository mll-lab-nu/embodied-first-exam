#!/usr/bin/env python3
"""Check the cheaper EpisodeIPCCoupler.diagnostics (image 0.2.8) against the np.linalg.det form it replaced, on the GPU.

    python scripts/check_ipc_diagnostics.py <family> <instance.json> [--steps 3] [--out report.json]

Holds for a few control steps; at every physics tick both forms run on the same state. Pass: attachment residuals equal and
volume-ratio minima / maxima equal within 1e-12 relative. Reports both times per tick."""
import argparse, json, sys, time
import numpy as np
from rcb_topogym import Session


def det_form(coupler):
    from topogym.world.physics.fem import read_vertices
    residuals = {}
    for name, entity, indices, slot, local in coupler.attachment_pairs:
        matrix = np.asarray(slot.geometry().instances().find("transform").view()).reshape(-1, 4, 4)[0]
        targets = local @ matrix[:3, :3].T + matrix[:3, 3]
        residuals[name] = float(np.max(np.linalg.norm(read_vertices(entity)["position_m"][indices] - targets, axis=1)))
    ratios = {}
    for entity in coupler.fem_solver.entities:
        p = read_vertices(entity)["position_m"][entity.elems]; r = entity.material_coordinates[entity.elems]
        jac = np.linalg.det(p[:, 1:] - p[:, :1]) / np.linalg.det(r[:, 1:] - r[:, :1])
        ratios[entity.name] = dict(minimum=float(jac.min()), maximum=float(jac.max()))
    return residuals, ratios


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("family"); ap.add_argument("instance"); ap.add_argument("--steps", type=int, default=3); ap.add_argument("--out")
    a = ap.parse_args()
    s = Session(a.family, instance=a.instance, strict=False)
    coupler = s.env._world.scene.sim.coupler; new = coupler.diagnostics
    log = dict(ticks=0, diffs=[], new_s=0.0, old_s=0.0, worst_rel=0.0)

    def compared():
        t = time.perf_counter(); d = new(); t1 = time.perf_counter(); res, rat = det_form(coupler); t2 = time.perf_counter()
        log["new_s"] += t1 - t; log["old_s"] += t2 - t1; log["ticks"] += 1
        if d["attachment_residual_m"] != res:
            log["diffs"].append(f"tick {log['ticks']}: residuals {d['attachment_residual_m']} != {res}")
        for n, v in rat.items():
            for k in ("minimum", "maximum"):
                rel = abs(d["volume_ratio"][n][k] - v[k]) / max(abs(v[k]), 1e-300)
                log["worst_rel"] = max(log["worst_rel"], rel)
                if rel > 1e-12:
                    log["diffs"].append(f"tick {log['ticks']}: {n} {k} {d['volume_ratio'][n][k]} != {v[k]}")
        return d

    coupler.diagnostics = compared
    for _ in range(a.steps):
        s.step(s.hold_action())
    report = dict(family=a.family, ticks=log["ticks"], identical=not log["diffs"], worst_relative=log["worst_rel"],
                  diffs=log["diffs"][:10], new_s_per_tick=round(log["new_s"] / max(log["ticks"], 1), 4),
                  old_s_per_tick=round(log["old_s"] / max(log["ticks"], 1), 4))
    print(json.dumps(report), flush=True)
    if a.out:
        open(a.out, "w").write(json.dumps(report, indent=1) + "\n")
    s.close()
    return 0 if report["identical"] and report["ticks"] else 1


if __name__ == "__main__":
    sys.exit(main())
