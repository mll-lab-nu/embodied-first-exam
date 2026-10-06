"""Run the fixed Muse binary through a per-process OpenRouter bridge."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import urllib.request

from .bridge import Bridge

VERSION = '1.4.3-R5018.1'
BINARY_SHA256 = 'e671790882bc88d65edb4ae0f713becf378ebf91011034ab75abebe3592dde4f'
BINARY_URL = 'https://lookaside.facebook.com/lookaside/muse/download/?channel=muse&version='+VERSION+'&file=muse-x86-linux'
IMPORT_PATH = 'harbor_agents.muse_openrouter:MuseOpenRouter'


def checksum(path):
    with open(path,'rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def ensure_binary(path):
    path = Path(path)
    if path.exists():
        if path.is_symlink() or checksum(path) != BINARY_SHA256: raise ValueError('fixed Muse binary checksum mismatch')
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.muse-')
    try:
        with os.fdopen(fd,'wb') as out, urllib.request.urlopen(BINARY_URL, timeout=60) as src:
            shutil.copyfileobj(src,out)
        if checksum(temp) != BINARY_SHA256: raise ValueError('downloaded Muse binary checksum mismatch')
        os.chmod(temp,0o755); os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    return path


def launch(binary, model, effort, prompt, logs, key, *, max_steps=None, upstream=None, environment=None):
    if checksum(binary) != BINARY_SHA256: raise ValueError('fixed Muse binary checksum mismatch')
    logs = Path(logs); logs.mkdir(parents=True, exist_ok=True)
    private = Path(tempfile.mkdtemp(prefix='muse-private-'))
    bridge = Bridge(key, model, logs, **({'upstream':upstream} if upstream else {}))
    thread = threading.Thread(target=bridge.serve_forever, daemon=True); thread.start()
    env = dict(os.environ if environment is None else environment)
    # The real key belongs to this bridge, not the child CLI or its stored config.
    for name in ('OPENROUTER_API_KEY','OPENROUTER_API_KEY_FOR_SMOKE','OPENAI_API_KEY','HF_TOKEN',
                 'HUGGING_FACE_HUB_TOKEN','META_API_KEY','CODEX_AUTH_JSON_PATH','ENV_FILE'):
        env.pop(name,None)
    env.update(META_API_KEY='topogym-loopback-bridge', MUSE_NO_AUTO_UPDATE='1',
               XDG_CONFIG_HOME=str(private/'config'), XDG_CACHE_HOME=str(private/'cache'),
               XDG_DATA_HOME=str(logs/'native-data'), XDG_STATE_HOME=str(private/'state'))
    argv = [str(binary),'exec','--json','--yolo','--user-input-auto-resolve',
            '--no-foreign-personal-context','--disable-web-tools','--provider','meta',
            '--base-url',f'http://127.0.0.1:{bridge.server_port}','--model',model,'--prompt-file',str(prompt)]
    if effort != 'default': argv += ['--reasoning-effort',effort]
    if max_steps: argv += ['--max-model-steps',str(max_steps)]
    child = None
    def interrupted(signum, frame):
        if child and child.poll() is None: child.terminate()
        raise KeyboardInterrupt
    previous = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM,signal.SIGINT): previous[sig] = signal.signal(sig,interrupted)
    try:
        with (logs/'muse-code.jsonl').open('wb') as stdout, (logs/'muse-code.stderr.log').open('wb') as stderr:
            child = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
            rc = child.wait()
        report = json.loads((logs/'openrouter-usage.json').read_text())
        if rc or not report['complete']:
            print('Muse/OpenRouter failed; check agent/openrouter-usage.json and native Muse logs. '
                  'HTTP 401 means model credentials; 402 means account credit; 429 means account rate/usage limits.',file=sys.stderr)
            return rc or 2
        return 0
    finally:
        if child and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
        bridge.shutdown(); bridge.server_close(); thread.join(timeout=5)
        for sig, handler in previous.items(): signal.signal(sig,handler)
        shutil.rmtree(private)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--model',required=True); p.add_argument('--effort',default='default')
    p.add_argument('--prompt-file',type=Path,required=True); p.add_argument('--logs',type=Path,required=True)
    a = p.parse_args()
    key = os.environ.get('OPENROUTER_API_KEY')
    if not key: p.error('OPENROUTER_API_KEY is required')
    return launch(a.binary,a.model,a.effort,a.prompt_file,a.logs,key)


if __name__ == '__main__': raise SystemExit(main())
