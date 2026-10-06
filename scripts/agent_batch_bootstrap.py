#!/usr/bin/env python3
"""Private, serialized runner installation, invoked by run_agent_batch.sh itself.

Uses the documented host Python/pip and Docker prerequisites. No global Python,
Node, Harbor, shell profile or credential files are modified.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
NODE='22.14.0'
CODEX='0.157.0'
UV='0.11.30'


def guard():
    data={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    if data['MemAvailable']<=data['MemTotal']*.10: raise ValueError('host memory reached 90%; stopped owned setup')


def run(argv, *, env=None, capture=False):
    guard()
    # Capture to disk so setup output cannot fill a pipe or memory while monitored.
    with tempfile.TemporaryFile() as output:
        child=subprocess.Popen(list(map(str,argv)),env=env,start_new_session=True,
                               stdout=output if capture else None,stderr=output if capture else None)
        try:
            while child.poll() is None: guard(); time.sleep(.25)
        except BaseException:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try: child.wait(timeout=10)
                except subprocess.TimeoutExpired: os.killpg(child.pid,signal.SIGKILL); child.wait()
            raise
        if child.returncode: raise ValueError('runner setup command failed: '+Path(str(argv[0])).name)
        output.seek(0)
        return output.read().decode().strip() if capture else ''


def python312(root):
    explicit=os.environ.get('AGENT_BATCH_BOOTSTRAP_PYTHON')
    for candidate in [explicit] if explicit else [shutil.which('python3.12'),sys.executable]:
        if not candidate: continue
        try:
            run([candidate,'-c','import sys; assert sys.version_info[:2]==(3,12)'],capture=True)
            return candidate
        except (OSError,ValueError):
            if explicit: raise ValueError('AGENT_BATCH_BOOTSTRAP_PYTHON must be Python 3.12') from None
    uv=shutil.which('uv')
    if not uv:
        target=root/'.tools/agent-batch/bootstrap'
        run([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-deps',
             '--target',target,'uv=='+UV])
        uv=str(target/'bin/uv')
    env=dict(os.environ,UV_PYTHON_INSTALL_DIR=str(root/'.tools/agent-batch/python'))
    run([uv,'python','install','3.12'],env=env)
    return run([uv,'python','find','3.12'],env=env,capture=True)


def download(url,path):
    with urllib.request.urlopen(url,timeout=60) as response,path.open('wb') as output:
        while True:
            guard(); block=response.read(1024*1024)
            if not block: break
            output.write(block)


def node_tools(root,python):
    # npm is not an additional host prerequisite: obtain the official pinned
    # Node distribution (which includes npm) when the documented host lacks it.
    npm=shutil.which('npm')
    if not npm:
        arch={'x86_64':'x64','aarch64':'arm64'}.get(platform.machine())
        if platform.system()!='Linux' or not arch: raise ValueError('runner needs Linux x86-64/arm64')
        name='node-v'+NODE+'-linux-'+arch
        home=root/'.tools/agent-batch'/name
        if not (home/'bin/npm').is_file():
            with tempfile.TemporaryDirectory(dir=home.parent,prefix='.node-') as td:
                temp=Path(td); archive=temp/(name+'.tar.xz'); sums=temp/'SHASUMS256.txt'
                base='https://nodejs.org/dist/v'+NODE+'/'
                download(base+archive.name,archive); download(base+sums.name,sums)
                expected=dict((line.split()[1],line.split()[0]) for line in sums.read_text().splitlines())
                if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected[archive.name]:
                    raise ValueError('Node archive checksum mismatch')
                # Python 3.12's data filter also checks link targets before extraction.
                run([python,'-c','import sys,tarfile; t=tarfile.open(sys.argv[1]); t.extractall(sys.argv[2],filter="data")',archive,temp])
                (temp/name).rename(home)
        npm=str(home/'bin/npm')
        os.environ['PATH']=str(home/'bin')+os.pathsep+os.environ.get('PATH','')
    run([npm,'install','--prefix',root/'.tools/agent-batch','node@'+NODE,'@openai/codex@'+CODEX])


def verify(root):
    python=root/'.venv-agent-batch/bin/python'
    run([python,'-c','import sys; sys.path.insert(0,sys.argv[1]); from agent_batch_runtime import tooling; tooling()',root/'scripts'],capture=True)
    env=dict(os.environ,PATH=str(root/'.tools/agent-batch/node_modules/.bin')+os.pathsep+os.environ.get('PATH',''))
    if run(['node','-p','process.versions.node'],env=env,capture=True)!=NODE: raise ValueError('private Node version differs')
    if CODEX not in run(['codex','--version'],env=env,capture=True): raise ValueError('private Codex version differs')


def bootstrap(root=ROOT):
    from agent_batch_host import require_docker
    require_docker()
    root=Path(root).resolve(); tools=root/'.tools/agent-batch'; tools.mkdir(parents=True,exist_ok=True)
    with (tools/'setup.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        venv=root/'.venv-agent-batch'; receipt=venv/'topogym-runner.json'
        if receipt.exists() and (tools/'node_modules/.bin/codex').exists():
            run([venv/'bin/python',root/'scripts/patch_agent_batch_providers.py',root])
            verify(root); return
        owner=tools/'setup-in-progress.json'
        if venv.exists() and not owner.exists() and not receipt.exists():
            raise ValueError('unrecognized existing runner venv; preserved for maintainer repair')
        owner.write_text(json.dumps({'repository':str(root)})+'\n')
        print('Installing pinned runner tools automatically; no additional helper command is needed.',flush=True)
        python=python312(root)
        if not venv.exists(): run([python,'-m','venv',venv])
        if not receipt.exists():
            run([venv/'bin/python','-m','pip','install','--require-hashes','-r',root/'requirements/difficulty-eval-controller.lock'])
            run([venv/'bin/python',root/'images/difficulty-eval/patch_harbor.py'],env=dict(os.environ,PYTHONPATH=str(root)))
            code='''import hashlib,importlib.util,json,pathlib,sys
root=pathlib.Path(sys.argv[1])
files={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
('images/difficulty-eval/patch_harbor.py','requirements/difficulty-eval-controller.lock')}
modules={name:hashlib.sha256(pathlib.Path(importlib.util.find_spec(name).origin).read_bytes()).hexdigest() for name in
('harbor.agents.installed.codex','harbor.environments.docker.docker')}
(pathlib.Path(sys.prefix)/'topogym-runner.json').write_text(json.dumps(dict(files=files,modules=modules),indent=2)+'\\n')
'''
            run([venv/'bin/python','-c',code,root])
        run([venv/'bin/python',root/'scripts/patch_agent_batch_providers.py',root])
        node_tools(root,python)
        verify(root); owner.unlink()
        print('Pinned runner tools ready.',flush=True)


if __name__=='__main__':
    try: bootstrap()
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        print('Runner setup blocked: '+str(error),file=sys.stderr); raise SystemExit(2)
