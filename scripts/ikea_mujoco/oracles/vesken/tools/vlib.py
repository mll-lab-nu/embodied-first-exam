"""vesken oracle helpers: session, checkpoints, geometry probes."""
import os, pickle, numpy as np, mujoco, rcb_ikea as R
OPS = None
def session(free=False):
    s = R.Session('vesken')
    if free:
        s.applied = lambda a: np.clip(a, s._clo, s._chi)
    global OPS; OPS = {o['key']: o for o in s.S.task['operations']}
    return s
def save_ck(s, path):
    st = s.get_state(); n = len(st['rows']); st['rows'] = None; st['nrows'] = n
    pickle.dump(st, open(path, 'wb'))
def load_ck(s, path, rows_src=None):
    st = pickle.load(open(path, 'rb')); n = st['nrows']
    st['rows'] = list(rows_src[:n]) if rows_src is not None else [None] * n
    s.set_state(st); return n
def geom(s, key):
    o = OPS[key]; g, l, a = s.S.mech.geometry(o); return g, l, a
def pose(s, name):
    b = s.model.body(name).id; return s.data.xpos[b].copy(), s.data.xquat[b].copy()
