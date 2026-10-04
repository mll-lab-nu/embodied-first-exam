"""Manager-side runtime locks and fresh-process instance probes for every family."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
import uuid

from .contracts import BridgeError, digest, instance_binding, read_json
from .packaging import task_inputs
from topogym.simulator.frozen_binding import validate_lock, check_inputs

ROOT = Path(__file__).resolve().parents[3]
IDENTITY_MODULE = ROOT/'topogym/simulator/frozen_binding.py'


def selected_tasks(root=ROOT, *, selection='active', tiers=('easy','medium','hard')):
    sys.path.insert(0, str(Path(root)/'scripts'))
    from topogym_versions import release, task_root
    target, folder = release(root, selection), task_root(root, selection)
    rows = []
    for path in sorted(folder.glob('topogym-*/task.toml')):
        meta = tomllib.loads(path.read_text()).get('metadata', {})
        if meta.get('tooling_version') == target['tooling_version'] and meta.get('difficulty') in tiers:
            rows.append(path.parent)
    if not rows:
        raise BridgeError(f"No frozen tasks for {target['name']}")
    return rows


def image_references(task):
    """Use the repository's base-image selector, retaining container roles."""
    spec = importlib.util.spec_from_file_location('_binding_tooling_check', ROOT/'ci_checks/check-topogym-tooling.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    pairs = checker.image_references(Path(task), include_custom=True)
    references = dict(pairs)
    if len(references) != len(pairs):
        raise BridgeError(f'Ambiguous simulator image stages: {pairs}')
    return references


def image_reference(task):
    references = image_references(task)
    key = 'environment/docker-compose.yaml' if Path(task).name.endswith(('-standard','-limited')) else 'tests/Dockerfile'
    if key not in references:
        raise BridgeError(f'Task lacks a simulator/verifier image: {references}')
    return references[key]


def inspect_image(reference):
    result = subprocess.run(['docker','image','inspect',reference], capture_output=True, text=True)
    if result.returncode:
        raise BridgeError(f'Required local image is unavailable: {reference}: {result.stderr.strip()}')
    row = json.loads(result.stdout)[0]
    return dict(reference=reference, id=row['Id'], repo_digests=sorted(row.get('RepoDigests') or []))


def inspect_runtime(image):
    # Import this small stdlib-only checker by path: older immutable images do
    # not contain it. No checkout/public simulator is added to PYTHONPATH.
    code = ("import importlib.util,json; "
            "s=importlib.util.spec_from_file_location('identity','/binding_identity.py'); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            "print(json.dumps(m.installed_runtime('/opt/topogym')))" )
    result = subprocess.run(['docker','run','--rm','--network','none',
        '-v',f'{IDENTITY_MODULE}:/binding_identity.py:ro','-w','/tmp',image['id'],'python','-c',code],
        capture_output=True,text=True)
    if result.returncode:
        raise BridgeError('Image source inspection failed: '+result.stderr[-2000:])
    return json.loads(result.stdout.strip().splitlines()[-1])


def lock_for_task(task, image, runtime, *, agent_image=None):
    task, mode, instance, tooling = task_inputs(task)
    if image_reference(task) != image['reference']:
        raise BridgeError('Selected runtime image differs from the task package')
    binding = instance_binding(instance)
    lock = dict(schema_version=1, instance_sha256=binding['instance_sha256'],
                asset_files=binding['asset_files'], tooling_sha256=digest(tooling),
                creation_source=binding['instance']['topogym_source'], runtime=runtime, image=image)
    agent_ref = image_references(task).get('environment/Dockerfile', image['reference'])
    if agent_ref != image['reference']:
        if agent_image is None or agent_image['reference'] != agent_ref:
            raise BridgeError('A derived privileged agent image needs its own inspected identity')
        lock['agent_image'] = agent_image
    validate_lock(lock)
    return lock


def inspect_task(task, cache=None):
    cache = {} if cache is None else cache

    def inspect(reference):
        if reference not in cache:
            image = inspect_image(reference)
            cache[reference] = (image, inspect_runtime(image))
        return cache[reference]

    base = image_reference(task)
    image, runtime = inspect(base)
    agent_ref = image_references(task).get('environment/Dockerfile', base)
    agent_image = None
    if agent_ref != base:
        agent_image, agent_runtime = inspect(agent_ref)
        if agent_runtime != runtime:
            raise BridgeError('Privileged agent and verifier have different simulator source/dependencies')
    return lock_for_task(task, image, runtime, agent_image=agent_image)


def bind_tasks(tasks, output):
    """Prepare identities only. Every actual Session must still restore exactly."""
    output = Path(output).resolve()
    if output.exists():
        raise BridgeError('Binding output must be new')
    images, prepared = {}, []
    for task in tasks:
        task = Path(task).resolve()
        lock = inspect_task(task, images)
        prepared.append((task, lock))
    # No incomplete catalog if even one task/image cannot be inspected.
    output.mkdir(parents=True)
    rows = []
    for task, lock in prepared:
        path = output/(task.name+'.json')
        path.write_text(json.dumps(lock,indent=2)+'\n')
        rows.append(dict(task=str(task),lock=path.name,lock_sha256=digest(path),
                         exact_restore='not_run',physical_success='not_run',harbor='not_run'))
    catalog = dict(schema_version=1,status='runtime_bound_pending_exact_restore',tasks=rows)
    (output/'runtime_catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
    return catalog


def check_lock_for_task(task, lock, *, inspect_docker=False):
    task, _, instance, tooling = task_inputs(task)
    validate_lock(lock)
    check_inputs(instance, tooling, lock)
    if image_reference(task) != lock['image']['reference']:
        raise BridgeError('Task image changed after runtime binding')
    expected_images = [lock['image']]
    if not task.name.endswith(('-standard','-limited')):
        agent_ref = image_references(task).get('environment/Dockerfile')
        agent_image = lock.get('agent_image', lock['image'])
        if agent_ref != agent_image['reference']:
            raise BridgeError('Privileged agent image changed after runtime binding')
        if agent_image != lock['image']:
            expected_images.append(agent_image)
    if inspect_docker:
        for expected in expected_images:
            actual = inspect_image(expected['reference'])
            if actual['id'] != expected['id']:
                raise BridgeError('Docker image tag moved after runtime binding; bind a new experiment')
    return lock


def preflight(task, lock_path, output, *, gpu='0', execute=False):
    """Plan or perform exact restore in a clean process; never claim solvability."""
    task, _, instance, tooling = task_inputs(task)
    lock_path, output = Path(lock_path).resolve(), Path(output).resolve()
    lock = read_json(lock_path)
    check_lock_for_task(task,lock,inspect_docker=execute)
    if output.exists():
        raise BridgeError('Preflight output must be new')
    output.mkdir(parents=True)
    # The probe is manager-owned and can inspect full state; no oracle runs.
    worker = output/'probe.py'
    worker.write_text('''import importlib.util,json,sys,time,traceback
from pathlib import Path
sys.path.insert(0,'/binding')
import frozen_binding as B
started=time.time()
report=dict(stage='startup',status='failed',solvability=False,harbor_qualified=False)
s=None
try:
 lock=json.loads(Path('/binding/runtime.json').read_text())
 inst=B.check_inputs('/input/instance.json','/input/rcb_topogym.py',lock)
 report['runtime']=B.check_runtime(lock)
 spec=importlib.util.spec_from_file_location('rcb_topogym','/input/rcb_topogym.py')
 tool=importlib.util.module_from_spec(spec);sys.modules['rcb_topogym']=tool;spec.loader.exec_module(tool)
 s=tool.Session(inst['task'],instance='/input/instance.json',strict=True)
 if not s.instance_exact or not s.instance_matches or s.instance_sha != inst['state_sha']:
  raise B.BindingMismatch('Fresh process did not restore the exact frozen state')
 if s.asset_identity != inst['asset_identity'] or list(s.action_layout) != inst['action_layout']:
  raise B.BindingMismatch('Runtime assets or action layout differ')
 report.update(status='passed',instance_exact=True,state_sha=s.instance_sha,binding_id=B.binding_id(lock))
except BaseException as error:
 report.update(error=f'{type(error).__name__}: {error}',traceback=traceback.format_exc())
finally:
 if s is not None:s.close()
 report['wall_s']=time.time()-started
 Path('/output/startup.json').write_text(json.dumps(report,indent=2)+'\\n')
print(json.dumps(report),flush=True)
raise SystemExit(0 if report['status']=='passed' else 1)
''')
    container_name = 'topogym-binding-' + uuid.uuid4().hex
    command = ['docker','run','--rm','--name',container_name,'--network','none','--runtime','nvidia','--gpus','device='+gpu,
        '-e','NVIDIA_DRIVER_CAPABILITIES=all','-e','PYTHONDONTWRITEBYTECODE=1',
        '-v',f'{instance.parent}:/input:ro','-v',f'{output}:/output',
        '-v',f'{IDENTITY_MODULE}:/binding/frozen_binding.py:ro',
        '-v',f'{lock_path}:/binding/runtime.json:ro','-w','/output',lock['image']['id'],
        'python','/output/probe.py']
    plan = dict(stage='startup',status='planned',command=command,task=str(task),binding_sha256=digest(lock_path),
                scope='fresh-process exact restore only; no actions, success or video qualification')
    (output/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    if execute:
        from topogym.utils.process_limits import run_guarded
        (output/'supervision').mkdir()
        try:
            code = run_guarded(command, output/'supervision',cwd=output,env=dict(os.environ))
        finally:
            # Killing a Docker client does not necessarily stop its container.
            # Remove only this uniquely named probe, never another experiment.
            subprocess.run(['docker','rm','-f',container_name],capture_output=True,text=True)
        if code:
            raise BridgeError(f'Exact-load probe failed ({code}); see {output}')
        report = read_json(output/'startup.json')
        if report.get('status') != 'passed' or report.get('instance_exact') is not True:
            raise BridgeError('Probe produced no exact-load evidence')
        return report
    return plan
