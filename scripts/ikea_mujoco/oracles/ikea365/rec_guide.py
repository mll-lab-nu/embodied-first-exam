"""The phase guide: the original demo replayed open-loop (with `noclamp`: WITHOUT the arm clamp, as it was made), logging
per row the part poses (member_a, member_b, same_screw, bowl), both TCP poses, the screw and member_b relative to
member_a, the executed ctrl and the mechanism's progress. build_ref.py's guide tracks read `pose` and `tcp`.
The reference's guide is this run on the PRE-prism scene, where the demo passes all seven operations and final_check():
  IKEA_SCENES=<scene root with f782d078a1^1's ikea365 files> rec_guide.py runs/scan_old_noclamp.npz noclamp
On the current (prism) scene the unclamped demo never seats the screw, so its later part poses are no guide.
  rec_guide.py OUT.npz [noclamp]"""
import sys, os, json, numpy as np, mujoco
import rcb_ikea as R
s = R.Session('ikea365'); m, d = s.model, s.data
if len(sys.argv) > 2 and sys.argv[2] == 'noclamp':
    s.applied = lambda a: np.clip(a, s._clo, s._chi)
c = np.load(os.environ['I365_DEMO'])['ctrl']
mech = s.S.mech
parts = ['member_a', 'member_b', 'same_screw', 'bowl']
bid = [m.body(p).id for p in parts]
sites = [m.site('left_tcp').id, m.site('right_tcp').id]
N = len(c)
pose = np.zeros((N, 4, 7)); tcp = np.zeros((N, 2, 12)); srel = np.zeros((N, 7)); brel = np.zeros((N, 7)); ctrl = np.zeros((N, 16))
turns = np.zeros(N); nxt = np.zeros(N, int)
ev = []
for i, row in enumerate(c):
    s.step(row)
    for k, b in enumerate(bid):
        pose[i, k, :3] = d.xpos[b]; pose[i, k, 3:] = d.xquat[b]
    for k, si in enumerate(sites):
        tcp[i, k, :3] = d.site_xpos[si]; tcp[i, k, 3:] = d.site_xmat[si]
    p, q, sp = mech.rel('same_screw'); srel[i, :3] = p; srel[i, 3:] = q
    p, q, sp = mech.rel('member_b'); brel[i, :3] = p; brel[i, 3:] = q
    ctrl[i] = d.ctrl
    turns[i] = mech.op.get('turns', 0.); nxt[i] = mech.next
    if len(mech.events) > len(ev):
        ev.append(mech.events[-1]); print('ACCEPT', i, mech.events[-1][0], json.dumps(mech.events[-1][2]), flush=True)
    if i % 5000 == 0:
        print('row', i, 'next', mech.ops[mech.next] if not mech.complete else 'done', 'op', {k: v for k, v in mech.op.items() if isinstance(v, float)}, flush=True)
fc = s.final_check()
print('FINAL', fc['success'], json.dumps(fc['end']['report'].get('failures')), fc['state_sha'][:16], fc['settled_sha'][:16])
np.savez_compressed(sys.argv[1], pose=pose, tcp=tcp, srel=srel, brel=brel, ctrl=ctrl, turns=turns, nxt=nxt,
                    acc=np.array([[0]]), ev=np.array(json.dumps(ev, default=str)))
