"""Collect the evidence of one run directory into evidence.json + a frame-strip stand-in (matplotlib).

usage: python evidence.py <tier> <run_dir> <layout.json>
Reads metrics.json and states.npz; runs the offline penetration audit (every 3rd step) and the in-hand slip
summary; writes <run_dir>/evidence.json and <run_dir>/strip.png (top/front/side views at phase starts).
"""
import json
import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
tier, run, lay = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
m = json.loads((run / "metrics.json").read_text())
pen = json.loads(subprocess.run([sys.executable, str(here / "penetration_audit.py"), tier, str(run / "states.npz"), "3"],
                                capture_output=True, text=True, check=True).stdout)
slip = subprocess.run([sys.executable, str(here / "grasp_slip.py"), str(run)], capture_output=True, text=True).stdout
steps = [p["start_step"] for p in m.get("phases", [])][2:] + [-1]
subprocess.run([sys.executable, str(here / "plot_state.py"), str(run / "states.npz"), lay, str(run / "strip.png")]
               + [str(s) for s in steps[:8]], check=True, capture_output=True)
ev = dict(metrics={k: m[k] for k in ("task", "variant", "status", "success", "first_success_step", "steps",
                                     "sim_time_s", "wall_time_s", "final_check", "final_state_hash") if k in m},
          penetration_audit=pen, slip_report=slip.splitlines())
(run / "evidence.json").write_text(json.dumps(ev, indent=1, default=float))
print(json.dumps(ev["metrics"], default=float)[:600]); print(json.dumps(pen))
