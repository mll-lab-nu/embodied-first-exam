"""Development helper: resume the oracle from a saved stage snapshot (sim state + stage variables).
  python resume.py --ckpt <run>/ckpt_regrip.pt --out <dir> [oracle args...]
Executes oracle.py's setup (env, helpers), restores the snapshot, then runs oracle.py from the '# @@RESUME regrip'
marker on. Results are for debugging the later stages only (no actions from reset; never a deliverable)."""
import os, sys
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle.py")
src = open(src_path).read()
argv = sys.argv[1:]
ck = argv[argv.index("--ckpt") + 1]
del argv[argv.index("--ckpt"):argv.index("--ckpt") + 2]
sys.argv = [src_path] + argv
head = src[:src.index("# ======================================================================== ready")]
tail = src[src.index("# @@RESUME regrip"):]
g = {"__name__": "__main__", "__file__": src_path}
exec(compile(head, src_path, "exec"), g)
extra = g["R"].restore(ck)
g.update(extra)
g["R"].hold(5)
# helpers defined inside later stages that the tail needs
pre = src[src.index("# ======================================================================== pick (left): ledge regrasp"):src.index("# drag 1:")]
exec(compile(pre, src_path, "exec"), g)
mid = src[src.index("# ======================================================================== regrip by the right alone"):src.index("GF2 = None")]
mid = mid.split("off_r, _ = held_offset")[0]          # constants only (a3, gp_mid2, gp_end2)
exec(compile(mid, src_path, "exec"), g)
exec(compile(src[src.index("def feed2_ok(zs):"):src.index("GF2 = None")], src_path, "exec"), g)
g["say"]("RESUMED from", ck, "vars", extra)
exec(compile(tail, src_path, "exec"), g)
