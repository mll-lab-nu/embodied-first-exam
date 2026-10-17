"""From the last op checkpoint: the demo's tail (offsets ramped out), a rest hold, then save the reference + final_check."""
import sys, json, pickle, time, numpy as np, vesken_oracle as V
ck, out, rest = sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
run = V.Runner('refs/vesken.npz', 'tools/ref')
run.restore(pickle.load(open(ck, 'rb')))
t = time.time()
run.tail(dict(g=0.02, gr=0.01, rest_s=rest))
fc = run.s.final_check()
run.s.save_trajectory(path=out)
e, st = fc['end'], fc['settled']
print(json.dumps(dict(success=fc['success'], rows=len(run.s.rows), end={k: e[k] for k in ('goal', 'released', 'at_rest', 'breakdown')},
      settled={k: st[k] for k in ('goal', 'released', 'at_rest', 'breakdown')}, passed=e['report']['operations_passed'],
      orient=e['report']['orientation_deg'], floor=e['report']['floor_contact_N'], term=e['terminal'], sha=fc['state_sha'],
      settled_sha=fc['settled_sha'], rr=run.rr_max, wall=time.time() - t), default=str))
