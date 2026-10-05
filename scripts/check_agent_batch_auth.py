#!/usr/bin/env python3
"""Small real Codex model canary, with private credentials/logs and serialized refresh.

This consumes one small model request, not an experimental rollout. Run before
starting lanes. It does not certify Docker, physics, task solvability or GPU capacity.
"""
from contextlib import nullcontext
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from agent_batch_contract import read,save,validate,locked
from agent_batch_runtime import credentials,utc

def canary(plan,environment):
    if plan['agent']['name']!='codex' or not plan['agent']['model'].startswith('openai/'):
        raise ValueError('this canary supports the published native Codex/OpenAI runner')
    env,auth=credentials(environment)
    guard=locked(auth.with_name('.agent-batch-auth.lock')) if auth else nullcontext()
    with guard,tempfile.TemporaryDirectory(prefix='topogym-auth-canary-') as td:
        root=Path(td); profile=root/'profile'; profile.mkdir(mode=0o700); work=root/'work'; work.mkdir()
        original=read(auth) if auth else None
        if auth: shutil.copyfile(auth,profile/'auth.json'); (profile/'auth.json').chmod(0o600)
        env=dict(env,CODEX_HOME=str(profile))
        codex=shutil.which('codex',path=env.get('PATH'))
        if not codex: raise ValueError('Codex CLI missing; run setup_agent_batch.sh and export PATH')
        result=subprocess.run([codex,'--version'],env=env,capture_output=True,text=True,timeout=15)
        if result.returncode or '0.157.0' not in result.stdout: raise ValueError('Codex 0.157.0 is required')
        with (root/'private.log').open('wb') as log:
            if not auth:
                result=subprocess.run([codex,'-c','cli_auth_credentials_store="file"','login','--with-api-key'],
                    input=env['OPENAI_API_KEY'].encode(),env=env,cwd=work,stdout=log,stderr=subprocess.STDOUT,timeout=30)
                if result.returncode: raise ValueError('canary API login failed (credentials not printed)')
            model=plan['agent']['model'].split('/',1)[1]
            argv=[codex,'exec','--skip-git-repo-check','--ephemeral','--sandbox','read-only','--model',model,
                  '-c','cli_auth_credentials_store="file"','-c','web_search="disabled"','--json']
            effort=plan['agent']['kwargs'].get('reasoning_effort')
            if effort: argv+=['-c','model_reasoning_effort="'+effort+'"']
            argv+=['Reply with OK only. Do not call any tools.']
            try:
                result=subprocess.run(argv,env=env,cwd=work,stdout=log,stderr=subprocess.STDOUT,timeout=90)
            finally:
                if auth:
                    refreshed=read(profile/'auth.json')
                    if (refreshed.get('tokens') or {}).get('account_id')!=(original.get('tokens') or {}).get('account_id'):
                        raise ValueError('canary changed subscription account')
                    save(auth,refreshed); auth.chmod(0o600)
            if result.returncode: raise ValueError('model canary failed; check account/model access before running the batch')
        # Exit zero alone is insufficient: require a completed turn in the JSON stream.
        import json
        events=[]
        for line in (root/'private.log').read_text(errors='replace').splitlines():
            try: events.append(json.loads(line))
            except ValueError: pass
        if not any(e.get('type')=='turn.completed' for e in events if isinstance(e,dict)):
            raise ValueError('canary produced no completed model turn')
    return dict(passed=True,at=utc(),plan_sha256=plan['plan_sha256'],auth='subscription' if auth else 'api-key',scope='small model request only')

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--assignment',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True); a=p.parse_args()
    try: save(a.receipt,canary(validate(read(a.assignment)),os.environ)); print('Model authentication canary passed.'); return 0
    except (OSError,ValueError,KeyError,subprocess.TimeoutExpired) as e: p.exit(2,'Authentication blocked: '+str(e)+'\n')

if __name__=='__main__': raise SystemExit(main())
