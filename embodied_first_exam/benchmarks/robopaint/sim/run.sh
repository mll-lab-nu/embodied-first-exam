#!/bin/sh
# The scoring service of the privileged mode (rcb_scorer.py): the graders' copy of the frozen instance, metrics only over HTTP.
export RCB_RENDER=0 RCB_SESSION_LOG= OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 RCB_TORCH_THREADS=2
exec python -u /srv/rcb_scorer.py
