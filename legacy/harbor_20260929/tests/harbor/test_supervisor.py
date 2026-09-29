import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

from harbor_runners.supervisor import stop_process_group, stop_trial


def test_real_process_group_and_detached_leader_descendant_are_stopped(tmp_path):
    child_pid = tmp_path/'child.pid'
    source = """import os,signal,subprocess,sys,time
signal.signal(signal.SIGTERM,signal.SIG_IGN)
child=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(100)'])
open(sys.argv[1],'w').write(str(child.pid))
time.sleep(100)
"""
    process = subprocess.Popen([sys.executable,'-c',source,str(child_pid)],start_new_session=True)
    try:
        end=time.monotonic()+3
        while not child_pid.exists() and time.monotonic()<end: time.sleep(.01)
        assert child_pid.exists()
        start=time.monotonic()
        stop_process_group(process,grace=.05)
        assert time.monotonic()-start < 1
        pid=int(child_pid.read_text())
        stat=Path(f'/proc/{pid}/stat')
        def stopped():
            try:
                return stat.read_text().split()[2] == 'Z'
            except (FileNotFoundError, ProcessLookupError):
                # Reaping can remove /proc after exists() or even during read().
                return True
        end=time.monotonic()+1
        while not stopped() and time.monotonic()<end: time.sleep(.01)
        assert stopped()
    finally:
        if process.poll() is None: stop_process_group(process)


def test_supervisor_only_targets_its_trial_and_emits_stop_timings():
    class Environment:
        def __init__(self): self.commands=[]
        async def exec(self,**kwargs):
            self.commands.append(kwargs)
            return SimpleNamespace(return_code=0,stdout='stopped')
        async def stop(self,**kwargs): raise AssertionError('unnecessary container stop')
    one,two=Environment(),Environment()
    result=asyncio.run(stop_trial(one,{'stop':{'reason':'budget_exceeded'}}))
    assert result['agent_stopped_at'] and result['worker_stopped_at']
    assert two.commands == [] and all(cmd['user']=='root' for cmd in one.commands)


def test_unresponsive_trial_escalates_to_only_its_environment():
    class Environment:
        stopped=False
        async def exec(self,**kwargs): return SimpleNamespace(return_code=1)
        async def stop(self,**kwargs): self.stopped=True
    environment=Environment()
    result=asyncio.run(stop_trial(environment,{}))
    assert environment.stopped and result['forced_environment_stop']
    assert result['evidence_complete'] is False
