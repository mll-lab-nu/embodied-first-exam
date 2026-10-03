#!/usr/bin/env python3
"""Fill the image's shared cache (XDG_CACHE_HOME, CUDA_CACHE_PATH; see the Dockerfile) with one TopoGym instance: build
its Session (kernels, assets), run one hold step, render one RGB frame and one depth frame (Nyx shaders, the CPU
backend's visual-state kernels). Run once per instance, each in its own process (Genesis initialises one backend and
precision per process), inside the container that images/topogym/warm_cache.sh commits.

    python warm_cache.py <family> <instance.json> <tooling dir>   # prints one JSON line with the timings
"""
import json
import sys
import time

family, instance, tooling = sys.argv[1:4]
sys.path.insert(0, tooling)
t0 = time.time()
from rcb_topogym import Session  # noqa: E402

s = Session(family, instance=instance, strict=False)
t1 = time.time()
s.step(s.hold_action())
t2 = time.time()
s.render_frame()
s.render_depth()
t3 = time.time()
print(json.dumps(dict(family=family, instance=instance, build_s=round(t1 - t0, 1), step_s=round(t2 - t1, 2),
                      render_s=round(t3 - t2, 2), instance_matches=bool(s.instance_matches))), flush=True)
