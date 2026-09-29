"""Stop one trial's agent UID and policy; preserve the manager for verification."""
import asyncio
import base64
import json
import os
import signal
import subprocess
import time


async def root_python(environment, source, *, timeout=10):
    import shlex
    result = await asyncio.wait_for(environment.exec(command="python -c " + shlex.quote(source),
        user="root", timeout_sec=timeout), timeout=timeout + 1)
    if result.return_code:
        raise RuntimeError("Trusted trial management command failed")
    return result


async def publish_usage(environment, snapshot, *, stop_worker=False):
    payload = base64.b64encode(json.dumps(snapshot).encode()).decode()
    source = f"""import base64,json
from topogym.agents.rollout.protocol import atomic_json
from topogym.agents.rollout.client import call
s=json.loads(base64.b64decode({payload!r}))
atomic_json('/trial/rollout/usage_final.json',s,0o600)
atomic_json('/rollout/budget.json',s,0o644)
"""
    if stop_worker:
        source += "call({'operation':'budget_stop','snapshot':s}, '/run/topogym/admin.sock')\n"
    await root_python(environment, source)


async def stop_trial(environment, snapshot, *, grace_ms=1000):
    timings = {"cancel_sent_at": time.time(), "cancel_sent_monotonic_ns": time.monotonic_ns()}
    kill = """import os,pwd,signal,time
uid=pwd.getpwnam('agent').pw_uid
end=time.monotonic()+%r
while True:
 active=[]
 for item in os.listdir('/proc'):
  if item.isdigit():
   try:
    fields=dict(line.split(':',1) for line in open('/proc/'+item+'/status'))
    if uid in map(int,fields['Uid'].split()) and fields['State'].strip()[0]!='Z':
     active.append(int(item));os.kill(int(item),signal.SIGKILL)
   except (FileNotFoundError,ProcessLookupError): pass
 if not active: break
 if time.monotonic()>=end: raise TimeoutError('Agent processes did not stop')
 time.sleep(.01)
"""
    kill = kill % (grace_ms / 1000)
    results = await asyncio.gather(root_python(environment, kill),
        publish_usage(environment, snapshot, stop_worker=True), return_exceptions=True)
    if any(isinstance(r, BaseException) for r in results):
        await asyncio.wait_for(environment.stop(delete=False), timeout=20)
        timings.update(forced_environment_stop=True, evidence_complete=False)
        return timings
    timings.update(agent_stopped_at=time.time(), agent_stopped_monotonic_ns=time.monotonic_ns())
    probe = """import time
from topogym.agents.rollout.client import call
end=time.monotonic()+%r
while time.monotonic()<end:
 s=call({'operation':'budget_status'}, '/run/topogym/admin.sock')
 if s['execution_stopped']:
  print('stopped');break
 time.sleep(.02)
else: raise TimeoutError('Policy did not stop within grace')
""" % (grace_ms / 1000)
    try:
        await root_python(environment, probe, timeout=max(2, grace_ms // 1000 + 1))
        timings.update(worker_stopped_at=time.time(), worker_stopped_monotonic_ns=time.monotonic_ns())
    except Exception:
        await asyncio.wait_for(environment.stop(delete=False), timeout=20)
        timings.update(forced_environment_stop=True, evidence_complete=False)
    return timings


def stop_process_group(process, *, grace=.1):
    """Local harness equivalent, used to verify real descendant-process stopping."""
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2)
