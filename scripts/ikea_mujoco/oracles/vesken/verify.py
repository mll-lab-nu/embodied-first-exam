"""Fresh-process replay of a reference: rows over the speed limit (vs the previous row, from the keyframe ctrl) and final_check()."""
import sys, json, time, numpy as np, rcb_ikea as R
p = sys.argv[1]; s = R.Session('vesken'); c = R.load_trajectory(p, s.nu, s.timestep)
prev = np.vstack([s.data.ctrl.copy(), c[:-1]]); over = int((np.abs(c - prev) > s.step_limit + 1e-9).any(1).sum())
clip = int((np.clip(c, s._clo, s._chi) != c).any(1).sum())
t = time.time(); s.run(c); fc = s.final_check(); w = time.time() - t
e, st = fc['end'], fc['settled']
print(json.dumps(dict(file_sha=R.file_sha(p), rows=len(c), over=over, clipped=clip, slewed=s.slewed_ticks, success=fc['success'],
      end={k: e[k] for k in ('goal', 'released', 'at_rest', 'breakdown')}, settled={k: st[k] for k in ('goal', 'released', 'at_rest', 'breakdown')},
      passed=e['report']['operations_passed'], depth=st['terminal']['max_part_depth_mm'], sha=fc['state_sha'], settled_sha=fc['settled_sha'], wall_s=round(w, 1))))
