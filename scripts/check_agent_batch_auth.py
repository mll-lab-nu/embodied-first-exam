#!/usr/bin/env python3
"""Small model canary using the assigned harness, with private credentials/logs.

This runs a short model session, not an experimental rollout. Native harnesses
may make additional internal requests. Run before starting lanes; this does not
certify physics, task solvability or GPU capacity.
"""
from contextlib import nullcontext
import argparse
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from agent_batch_contract import read,save,validate,locked,component
from agent_batch_runtime import credentials,utc,auth_secrets
from agent_batch_provider import canonical_model,codex_config,model_id

def canary(plan,environment,*,diagnostics_dir=None):
    if plan['agent']['name']=='muse-openrouter':
        return muse_canary(plan,environment,diagnostics_dir=diagnostics_dir)
    if plan['agent']['name']!='codex':
        raise ValueError('this canary supports the published native Codex runner')
    env,auth=credentials(dict(environment,MODEL=plan['agent']['model']))
    if canonical_model(plan['agent']['model'],env.get('PROVIDER'))!=plan['agent']['model']:
        raise ValueError('model provider differs from the selected batch plan')
    guard=locked(auth.with_name('.agent-batch-auth.lock')) if auth else nullcontext()
    with guard,tempfile.TemporaryDirectory(prefix='topogym-auth-canary-') as td:
        root=Path(td); profile=root/'profile'; profile.mkdir(mode=0o700); work=root/'work'; work.mkdir()
        original=read(auth) if auth else None
        if auth: shutil.copyfile(auth,profile/'auth.json'); (profile/'auth.json').chmod(0o600)
        env=dict(env,CODEX_HOME=str(profile))
        import toml
        (profile/'config.toml').write_text(toml.dumps(codex_config(plan['agent']['model'],env)))
        codex=shutil.which('codex',path=env.get('PATH'))
        if not codex: raise ValueError('Codex CLI missing; run setup_agent_batch.sh and export PATH')
        result=subprocess.run([codex,'--version'],env=env,capture_output=True,text=True,timeout=15)
        if result.returncode or '0.157.0' not in result.stdout: raise ValueError('Codex 0.157.0 is required')
        with (root/'private.log').open('wb') as log:
            if not auth:
                result=subprocess.run([codex,'-c','cli_auth_credentials_store="file"','login','--with-api-key'],
                    input=env['OPENAI_API_KEY'].encode(),env=env,cwd=work,stdout=log,stderr=subprocess.STDOUT,timeout=30)
                if result.returncode: raise ValueError('canary API login failed (credentials not printed)')
            model=model_id(plan['agent']['model'])
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
            if result.returncode: raise ValueError('model canary failed; check provider API credit, model access and EFFORT (try default if unsupported); no trial was claimed')
        # Exit zero alone is insufficient: require a completed turn in the JSON stream.
        import json
        events=[]
        for line in (root/'private.log').read_text(errors='replace').splitlines():
            try: events.append(json.loads(line))
            except ValueError: pass
        if not any(e.get('type')=='turn.completed' for e in events if isinstance(e,dict)):
            raise ValueError('canary produced no completed model turn')
    return dict(passed=True,at=utc(),plan_sha256=plan['plan_sha256'],auth='subscription' if auth else 'api-key',scope='small model request only')

def retain_muse_diagnostics(work,destination,plan,env,returncode,failure):
    """Keep only redacted, selected diagnostic files outside trial/evidence trees."""
    from secret_scan import scan_stream
    from harbor_agents.muse_transport.bridge import safe_error
    secrets=auth_secrets(env,None)
    def clean(value,limit=2000):
        output=io.BytesIO()
        scan_stream(io.BytesIO(str(value).encode()),secrets,output=output)
        return safe_error(output.getvalue().decode(errors='replace'),limit=limit)
    destination=Path(destination).expanduser().resolve(); destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    folder=Path(tempfile.mkdtemp(prefix='attempt-',dir=destination))
    notes=[]
    for name,source in {'docker.log':work/'docker.log',
                        **{n:work/'logs'/n for n in ('muse-code.stderr.log','muse-code.jsonl','openrouter-usage.json')}}.items():
        if not source.exists(): continue
        if source.is_symlink() or not source.resolve().is_relative_to(work.resolve()) or not source.is_file():
            notes.append('unsafe diagnostic file skipped: '+name); continue
        try:
            with source.open('rb') as src,(folder/name).open('xb') as dst:
                os.chmod(folder/name,0o600); scan_stream(src,secrets,output=dst)
        except OSError as exc: notes.append(clean(type(exc).__name__+': '+str(exc)))
    report={}
    if (folder/'openrouter-usage.json').is_file():
        try:
            report=read(folder/'openrouter-usage.json')
            if not isinstance(report,dict): raise ValueError('usage report is not an object')
        except (ValueError,OSError) as exc:
            report={}; notes.append(clean('invalid usage report: '+str(exc)))
    errors=report.get('errors',[])
    errors=[clean(e,200) for e in errors] if isinstance(errors,list) else ['invalid_provider_errors']
    passed=returncode==0 and report.get('complete') is True and not failure and not notes
    if passed: stage='passed'
    elif failure: stage='container_check'
    elif returncode==125: stage='docker_startup'
    elif returncode in (126,127): stage='container_command'
    elif errors: stage='provider_or_transport'
    elif not report: stage='launcher_before_usage_report'
    elif not report.get('requests'): stage='muse_startup'
    else: stage='model_session'
    hints=[]
    details=report.get('error_details',[])
    if isinstance(details,list):
        hints.extend(clean(str(row.get('code',''))+': '+str(row.get('message',''))) for row in details[-3:] if isinstance(row,dict))
    for name in ('docker.log','muse-code.stderr.log'):
        if (folder/name).is_file():
            with (folder/name).open('rb') as stream:
                stream.seek(0,2);stream.seek(max(0,stream.tell()-4096));tail=stream.read().decode(errors='replace')
            if tail.strip(): hints.append(name+': '+clean(tail,1500))
    summary=dict(schema_version=1,at=utc(),passed=passed,stage=stage,returncode=returncode,
                 model=plan['agent']['model'],failure=clean(failure) if failure else None,
                 provider_errors=errors,details=hints,notes=notes,
                 usage_complete=report.get('complete') is True,
                 requests=report.get('requests'),diagnostics=str(folder),redacted=True)
    save(folder/'summary.json',summary);(folder/'summary.json').chmod(0o600)
    return summary


def muse_canary(plan,environment,*,diagnostics_dir=None):
    from harbor_agents.muse_transport.launch import ensure_binary,VERSION
    env,auth=credentials(dict(environment,MODEL=plan['agent']['model']))
    if auth: raise ValueError('Muse/OpenRouter requires OpenRouter API credentials')
    root=Path(__file__).resolve().parents[1]
    if diagnostics_dir is None:
        jobs=Path(environment.get('JOBS',root/'jobs/agents')).expanduser().resolve()
        diagnostics_dir=jobs.parent/'.agent-batch-private'/component(plan['batch'])/'model-check'
    binary=root/'.tools/agent-batch/muse'/('muse-'+VERSION)
    with locked(binary.parent/'install.lock'):
        ensure_binary(binary)
    with tempfile.TemporaryDirectory(prefix='muse-canary-') as td:
        work=Path(td); prompt=work/'prompt.txt'
        prompt.write_text('Reply with OK only. Do not call tools.')
        # Never run the unrestricted coding harness on the helper's host. Use a
        # disposable container with only adapter code, the fixed binary and this
        # empty private canary directory mounted. No host home/auth files enter it.
        import uuid
        name='topogym-muse-canary-'+uuid.uuid4().hex
        image=plan['tasks'][0]['runtime_binding']['image']['reference']
        argv=['docker','run','--rm','--name',name,'--label','topogym.role=auth-canary',
              '--user',str(os.getuid())+':'+str(os.getgid()),'--read-only','--cap-drop=ALL',
              '--security-opt=no-new-privileges','--memory','2g','--tmpfs','/tmp:rw,exec',
              '-v',str(root/'harbor_agents')+':/adapter/harbor_agents:ro',
              '-v',str(binary)+':/adapter/muse:ro','-v',str(work)+':/canary:rw',
              '-e','OPENROUTER_API_KEY','-e','PYTHONPATH=/adapter','-w','/canary',image,
              'python3','-m','harbor_agents.muse_transport.launch',
              '--binary','/adapter/muse','--model',plan['agent']['model'].removeprefix('openrouter/'),
              '--effort',plan['agent']['kwargs'].get('reasoning_effort','default'),
              '--prompt-file','/canary/prompt.txt','--logs','/canary/logs']
        import signal
        child=None; failure=None
        with (work/'docker.log').open('wb') as log:
            try:
                child=subprocess.Popen(argv,cwd=work,env=env,stdin=subprocess.DEVNULL,stdout=log,
                                       stderr=subprocess.STDOUT,start_new_session=True)
                child.wait(timeout=120)
            except subprocess.TimeoutExpired:
                failure='model canary timed out after 120 seconds'
            except OSError as exc:
                failure=type(exc).__name__+': '+str(exc)
            finally:
                if child is not None:
                    if child.poll() is None:
                        try: os.killpg(child.pid,signal.SIGTERM)
                        except ProcessLookupError: pass
                        try: child.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            try: os.killpg(child.pid,signal.SIGKILL)
                            except ProcessLookupError: pass
                            child.wait()
                    try:
                        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
                    except (OSError,subprocess.TimeoutExpired) as exc:
                        failure=(failure+'; ' if failure else '')+'container cleanup: '+type(exc).__name__+': '+str(exc)
        result=retain_muse_diagnostics(work,diagnostics_dir,plan,env,child.returncode if child else None,failure)
        print('Model check diagnostics (redacted): '+result['diagnostics'],flush=True)
        if not result['passed']:
            reason='; '.join(filter(None,[result['failure'],*result['provider_errors'],*result['details'],*result['notes']]))
            if not reason: reason='no completed model session; see retained Muse output and usage report'
            raise ValueError('Muse/OpenRouter model canary failed [stage='+result['stage']+
                             ', exit='+str(result['returncode'])+']: '+reason[:3500]+
                             '\nDiagnostics (redacted): '+result['diagnostics']+'/summary.json; no trial was claimed') from None
    return dict(passed=True,at=utc(),plan_sha256=plan['plan_sha256'],auth='api-key',
                agent='muse-openrouter',muse_version=VERSION,diagnostics=result['diagnostics'],scope='short model session only; adapted protocol')

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--assignment',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--diagnostics-dir',type=Path,help='Directory for redacted Muse check diagnostics (one subdirectory per attempt)')
    a=p.parse_args()
    try:
        result=canary(validate(read(a.assignment)),os.environ,
                      diagnostics_dir=a.diagnostics_dir or a.receipt.parent/(a.receipt.name+'.diagnostics'))
        save(a.receipt,result); print('Model authentication canary passed.'); return 0
    except (OSError,ValueError,KeyError,subprocess.TimeoutExpired) as e: p.exit(2,'Authentication blocked: '+str(e)+'\n')

if __name__=='__main__': raise SystemExit(main())
