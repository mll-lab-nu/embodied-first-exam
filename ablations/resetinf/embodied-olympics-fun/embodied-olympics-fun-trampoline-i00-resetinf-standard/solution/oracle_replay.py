"""Standard-mode reference solution: the privileged twin's reference solution (the rows its controller stepped, by
action type) streamed through the client, one row per control step, as they are (interpolate="hold")."""
import numpy as np

from rcb_client import EpisodeOver, Robot

d = np.load("/solution/rows.npz", allow_pickle=False)
names, dims, typ, rows = [str(x) for x in d["names"]], d["dims"], d["type"], d["rows"]
r = Robot()
spec = r.spec()
cam = [sorted(spec["cameras"])[0]]
i, n, res = 0, len(typ), None
try:
    while i < n:
        j = i
        while j < n and typ[j] == typ[i] and j - i < 200:      # one chunk: a run of one type, at most 2 s
            j += 1
        res = r.submit(names[typ[i]], rows[i:j, :dims[typ[i]]], dt=spec["control_dt"], interpolate="hold", video="none",
                       cameras=cam)
        if res.done:
            break
        i = j
except EpisodeOver:
    pass
print(r.status(), None if res is None else {k: res.meta.get(k) for k in ("outcome", "stages_reached", "stages_total")})
