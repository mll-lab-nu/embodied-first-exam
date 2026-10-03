"""Trusted launcher: credentials and meters remain in the simulator service."""
import os
from pathlib import Path
import subprocess
import sys
import time
from workers import affinity

if len(sys.argv)>1:
    side=sys.argv[1]
    affinity(f'DUEL_PROXY_{side}_CPUS')
    os.environ['THINK_CLIENT_HOST']='seat_'+side.lower()
    os.environ['THINK_USAGE_FILE']=f'/data/think_usage_{side}.json'
    # per-seat route for OpenAI-style calls (THINK_OPENAI_ROUTE_A / _B), e.g. one Codex seat on Azure, one on OpenRouter
    if os.environ.get(f'THINK_OPENAI_ROUTE_{side}'):
        os.environ['THINK_OPENAI_ROUTE']=os.environ[f'THINK_OPENAI_ROUTE_{side}']
    os.execv(sys.executable,[sys.executable,'/srv/think_proxy.py','18090' if side=='A' else '18091'])

Path('/data').mkdir(exist_ok=True)
procs=[]
try:
    for side in ('A','B'):
        procs.append(subprocess.Popen([sys.executable,__file__,side]))
    procs.append(subprocess.Popen([sys.executable,'/srv/server_duel.py']))
    while all(p.poll() is None for p in procs): time.sleep(.5)
    raise RuntimeError('a required service exited')
finally:
    for p in procs:
        if p.poll() is None: p.terminate()
    for p in procs:
        try: p.wait(timeout=3)
        except subprocess.TimeoutExpired: p.kill()
