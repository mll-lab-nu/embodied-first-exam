#!/usr/bin/env python3
"""Real Docker/Harbor integration with a synthetic sidecar and nop agent.

Run inside the controller with a host-identical work-dir and Docker socket.
No model, task physics or solve qualification is involved.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
from difficulty_delivery import Delivery, DeliveryError, decorate_compose, resource_labels, configure_host_metrics, label_args
from difficulty_eval import Commands
from sample_difficulty_instances import atomic_json
import yaml


def lifecycle(work, cmd, base, image):
    """Actual daemon ownership tests using a synthetic UUID; no GPU is allocated."""
    lease=Delivery(work,cmd,run_id=base.name)
    lease.gpu_uuid='GPU-integration-'+base.name
    other_name='tg-other-'+base.name
    stale_name='tg-stale-'+base.name
    lock_name='topogym-gpu-lock-'+lease.gpu_uuid.lower()
    created=[]
    def create(args):
        _,out=cmd.run_command(args,capture=True,check=True,timeout=30)
        cid=out.strip(); created.append(cid); return cid
    try:
        create(['docker','run','-d','--name',other_name,'--entrypoint','sleep',image,'300'])
        rival=Delivery(base/'other-workspace',cmd,run_id='same-name')
        rival.owner=other_name; rival.gpu_uuid=lease.gpu_uuid
        with lease.gpu_lock():
            try:
                with rival.gpu_lock(): raise AssertionError('active lease was stolen')
            except DeliveryError as error:
                assert 'active controller' in str(error)
        create(['docker','run','-d','--name',stale_name,'--entrypoint','sleep',image,'300'])
        stale_labels=dict(lease.labels(),**{'topogym.owner':stale_name})
        orphan=create(['docker','run','-d',*label_args(stale_labels),'--entrypoint','sleep',image,'300'])
        create(['docker','create','--name',lock_name,*label_args(dict(stale_labels,**{'topogym.role':'gpu-lock'})),
                '--entrypoint','/bin/true',image])
        cmd.run_command(['docker','kill',stale_name],check=True,timeout=30)
        with lease.gpu_lock():
            assert lease.inspect(other_name)['State']['Running'], 'unrelated live container was touched'
            code,_=cmd.run_command(['docker','inspect',orphan],capture=True,timeout=30)
            assert code!=0, 'stale owned work survived reconciliation'
        return dict(active_owner_protected=True,cross_workspace_lock=True,kill_reconciled=True,unrelated_preserved=True)
    finally:
        for cid in created:
            cmd.run_command(['docker','rm','-f',cid],timeout=30)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--client-image', help='Pinned local image ID or registry digest for CPU-only testing; no GPU precheck is claimed')
    args=parser.parse_args()
    work=args.work_dir.resolve()
    if args.client_image:
        import subprocess
        from difficulty_release import load_build_info
        assert args.client_image.startswith('sha256:') or '@sha256:' in args.client_image, 'use an immutable image reference'
        actual=json.loads(subprocess.run(['docker','image','inspect',args.client_image],
            check=True,capture_output=True,text=True).stdout)[0]
        release_id=load_build_info(ROOT)['release_id']
        # BuildKit FROM cannot use an image-config ID as a registry digest.
        # Resolve the already installed image's immutable manifest reference.
        image=args.client_image if '@sha256:' in args.client_image else actual['RepoDigests'][0]
    else:
        check=json.loads((work/'check.json').read_text())
        assert check['passed'], 'run check first or select --client-image for CPU-only testing'
        release_id=check['release_id']
        image=check['images']['client']['image']
    (work/'cache/tmp').mkdir(parents=True,exist_ok=True)
    base=work/f'harbor-boundary-{time.time_ns()}'
    task=base/'tasks/topogym-delivery-nop'
    for folder in ('environment/sim','tests','solution'): (task/folder).mkdir(parents=True)
    payload='host-path-to-sibling-sidecar'
    (task/'environment/sim/probe.txt').write_text(payload)
    (task/'environment/Dockerfile').write_text(f'FROM {image}\nRUN mkdir -p /app/output\nWORKDIR /app\n')
    (task/'instruction.md').write_text('Infrastructure probe: no action is required.\n')
    (task/'solution/solve.sh').write_text('#!/bin/bash\nexit 0\n')
    labels=resource_labels('integration-'+base.name,base.name,release_id)
    # /data is private to this synthetic service; the real runtime provides it too.
    compose={'services':{'main':{'depends_on':['sim']},'sim':{'image':image,'volumes':['./sim:/srv:ro'],
        'command':['python','-c',"from pathlib import Path; import json,time; "
                   "Path('/data').mkdir(exist_ok=True); "
                   "Path('/data/final.json').write_text(json.dumps({'payload':Path('/srv/probe.txt').read_text()})); time.sleep(600)"]}}}
    decorate_compose(compose,labels,'GPU-unused')
    (task/'environment/docker-compose.yaml').write_text(yaml.safe_dump(compose,sort_keys=False))
    verifier=decorate_compose({'services':{'main':{}}},labels,'GPU-unused')
    (task/'tests/docker-compose.yaml').write_text(yaml.safe_dump(verifier,sort_keys=False))
    (task/'tests/Dockerfile').write_text(f'FROM {image}\nCOPY test.sh /tests/test.sh\nRUN chmod +x /tests/test.sh\n')
    (task/'tests/test.sh').write_text("#!/bin/bash\nset -eu\nmkdir -p /logs/verifier\n"
        "find /logs/verifier -mindepth 1 -maxdepth 1 ! -name test-stdout.txt -exec rm -rf {} +\n"
        "python - <<'CHECK'\nimport json\nfrom pathlib import Path\n"
        f"assert json.loads(Path('/data/final.json').read_text())['payload']=={payload!r}\n"
        "Path('/logs/verifier/reward.json').write_text('{\"success\":1}')\n"
        "Path('/logs/verifier/reward.txt').write_text('1\\n')\nCHECK\n")
    (task/'task.toml').write_text('''schema_version = "1.3"
artifacts = [{source="/data/final.json", service="sim"}]
[task]
name = "topogym/topogym-delivery-nop"
[agent]
timeout_sec = 30
[environment]
build_timeout_sec = 300
[verifier]
timeout_sec = 60
environment_mode = "separate"
network_mode = "no-network"
[[verifier.collect]]
service = "sim"
command = "test -f /data/final.json"
timeout_sec = 30
''')
    configure_host_metrics()
    env=dict(os.environ,TMPDIR=str(work/'cache/tmp'),TOPOGYM_RESOURCE_LABELS=json.dumps(labels))
    cmd=Commands(env,base)
    code,_=cmd.run_command(['/usr/local/bin/harbor','run','-p',task,'-a','nop','-n','1','-k','1','--max-retries','0',
                           '-o',base/'jobs','--job-name','probe'],log=base/'harbor.log',monitor=True,timeout=600)
    records=list((base/'jobs/probe').glob('*/result.json'))
    data=json.loads(records[0].read_text()) if len(records)==1 else {}
    passed=(code==0 and data.get('finished_at') and not data.get('exception_info') and
            ((data.get('verifier_result') or {}).get('rewards') or {}).get('success')==1 and
            data.get('verifier_environment_mode')=='separate')
    unreadable=[str(p) for p in base.rglob('*') if p.is_file() and not os.access(p,os.R_OK)]
    report=dict(passed=bool(passed and not unreadable),scope='real_docker_harbor_synthetic_sidecar_nop_separate_verifier',
                model_calls=0,physics_executed=False,gpu_environment_qualified=False,
                test_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                client_image=image,release_id=release_id,unreadable=unreadable,harbor_exit_code=code,result=data)
    if report['passed']:
        report['lifecycle']=lifecycle(work,cmd,base,image)
    atomic_json(base/'report.json',report)
    print(base/'report.json',flush=True)
    assert report['passed'], f'see {base}/harbor.log and report.json'


if __name__=='__main__': main()
