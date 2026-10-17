"""Rebuild the reference from the demo with the kept per-operation parameters (params.json), op by op, then the tail;
save it and print the final check. usage: rebuild.py demo.npz ref_dir params.json out.npz"""
import sys, json, time, numpy as np, vesken_oracle as V
demo, ref_dir, pp, out = sys.argv[1:5]
P = json.load(open(pp)); run = V.Runner(demo, ref_dir); t = time.time()
for k in range(len(run.ops)):
    run.restore(run.checkpoint())        # as search.py: every op starts from a restored checkpoint (set_state + mj_forward)
    r = run.run_op(k, P['ops'][k])
    print(k, r['key'], r['ok'], r['waited'], r['rows'], round(time.time() - t), flush=True)
    if not r['ok']: sys.exit(f'op {k} failed')
run.restore(run.checkpoint())
run.tail(P['tail'])
fc = run.s.final_check(); run.s.save_trajectory(path=out)
import rcb_ikea as R
print(json.dumps(dict(success=fc['success'], rows=len(run.s.rows), sha=fc['state_sha'], settled_sha=fc['settled_sha'],
                      file_rows_sha=__import__('hashlib').sha256(np.array(run.s.rows).tobytes()).hexdigest(), rr=run.rr_max, wall=round(time.time() - t))))
