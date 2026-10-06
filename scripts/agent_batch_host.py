"""Host prerequisites and an isolated GPU check before claiming trials."""
import copy
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import uuid

from secret_scan import scan_stream


GPU_CHECK = '''import json, os, subprocess
expected = os.environ["TOPOGYM_EXPECTED_GPU_UUID"]
visible = subprocess.check_output(["nvidia-smi", "--query-gpu=uuid", "--format=csv,noheader"], text=True).split()
if visible != [expected]:
    raise RuntimeError("Container GPU UUID does not match the selected host GPU: " + repr(visible))
import torch
if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
    raise RuntimeError("The task image cannot use exactly one CUDA GPU")
value = torch.ones(1, device="cuda") + 1
torch.cuda.synchronize()
if value.item() != 2:
    raise RuntimeError("CUDA check returned an unexpected result")
print("TOPOGYM_GPU_CHECK " + json.dumps({"gpu_uuid": expected, "cuda": True}))
'''


def gpu_configurations(plan, root):
    """Group identical GPU service declarations; don't boot 48 task servers."""
    import yaml
    from agent_batch_contract import relative
    groups = {}
    for task in plan['tasks']:
        folder = Path(root)/'tasks'/relative(task['name'])/'environment'
        services = yaml.safe_load((folder/'docker-compose.yaml').read_text())['services']
        name = 'main' if task['mode'] == 'privileged' else 'sim'
        service = services[name]
        devices = service['deploy']['resources']['reservations']['devices']
        if not any(d.get('driver') == 'nvidia' and 'gpu' in d.get('capabilities', []) for d in devices):
            raise ValueError('Task service has no NVIDIA GPU reservation: '+task['name']+'/'+name)
        image = task['runtime_binding']['image']['reference']
        if service.get('image', image) != image:
            raise ValueError('GPU service image differs from the frozen runtime: '+task['name'])
        config = dict(image=image, deploy={'resources': {'reservations': {'devices': copy.deepcopy(devices)}}},
                      environment={'NVIDIA_DRIVER_CAPABILITIES': service.get('environment', {}).get('NVIDIA_DRIVER_CAPABILITIES', 'compute,utility')})
        for key in ('runtime', 'shm_size'):
            if key in service: config[key] = service[key]
        key = json.dumps(config, sort_keys=True)
        group = groups.setdefault(key, dict(service=config, tasks=[]))
        group['tasks'].append(task['name']+'/'+name)
    if not groups: raise ValueError('No assigned GPU task services to check')
    return list(groups.values())


def require_gpu_containers(plan, root, environment, destination, secrets):
    """Check the task GPU configuration, not physics/graphics or model quality.

    Runs before a lane/job claim or model canary. Only our uniquely named Compose
    project is removed. No model credential is put in the probe container.
    """
    from agent_batch_contract import save
    configs = gpu_configurations(plan, root)
    destination = Path(destination); destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder = Path(tempfile.mkdtemp(prefix='attempt-', dir=destination))
    def clean(value):
        output = io.BytesIO()
        scan_stream(io.BytesIO(str(value).encode()), secrets, output=output)
        return output.getvalue().decode(errors='replace')
    report = dict(passed=False, gpu_uuid=environment['TOPOGYM_GPU_UUID'], checks=[], diagnostics=str(folder),
                  scope='GPU container startup and minimal CUDA operation; no physics, rendering or model calls')
    print('Checking assigned GPU container access before model requests or trial claims...', flush=True)
    for index, group in enumerate(configs):
        service = copy.deepcopy(group['service'])
        service.update(entrypoint=[], command=['python3', '-c', GPU_CHECK], network_mode='none',
                       read_only=True, tmpfs=['/tmp'], labels={'topogym.role': 'gpu-check'})
        service['environment'].update(TOPOGYM_EXPECTED_GPU_UUID=environment['TOPOGYM_GPU_UUID'],
                                      PYTHONDONTWRITEBYTECODE='1', CUDA_CACHE_DISABLE='1')
        compose = folder/('probe-'+str(index)+'.json')
        save(compose, {'services': {'gpucheck': service}}); compose.chmod(0o600)
        project = 'topogym-gpu-check-'+uuid.uuid4().hex
        argv = ['docker', 'compose', '--project-name', project, '-f', str(compose)]
        output = ''; reason = None; rc = None
        try:
            result = subprocess.run([*argv, 'run', '--rm', '--no-deps', '-T', 'gpucheck'],
                                    env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90)
            rc = result.returncode; output = result.stdout+'\n'+result.stderr
            if rc: reason = 'GPU container exited with code '+str(rc)
            elif 'TOPOGYM_GPU_CHECK ' not in result.stdout: reason = 'GPU check produced no success marker'
        except subprocess.TimeoutExpired as exc:
            def decode(value): return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
            output = decode(exc.stdout)+'\n'+decode(exc.stderr)
            reason = 'GPU container check timed out after 90 seconds'
        except OSError as exc:
            reason = type(exc).__name__+': '+str(exc)
        finally:
            try:
                cleanup = subprocess.run([*argv, 'down', '--remove-orphans', '--timeout', '5'], env=environment,
                                         stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)
                if cleanup.returncode:
                    reason = (reason+'; ' if reason else '')+'GPU check cleanup failed'
                    output += '\n'+cleanup.stdout+'\n'+cleanup.stderr
            except (OSError, subprocess.TimeoutExpired) as exc:
                reason = (reason+'; ' if reason else '')+'GPU check cleanup: '+type(exc).__name__
        log = folder/('probe-'+str(index)+'.log')
        log.write_text(clean(output)); log.chmod(0o600)
        report['checks'].append(dict(tasks=group['tasks'], image=service['image'], returncode=rc,
                                     passed=reason is None, reason=clean(reason) if reason else None, log=str(log)))
        report['passed'] = reason is None and len(report['checks']) == len(configs)
        save(folder/'summary.json', report); (folder/'summary.json').chmod(0o600)
        if reason:
            raise ValueError('GPU container check failed: '+clean(reason)+'. '+clean(output)[-2000:]+
                             '\nDiagnostics (redacted): '+str(folder/'summary.json')+
                             '\nCheck NVIDIA Container Toolkit and the selected Docker service. '
                             'No model request or trial was started; fix the host and retry the same batch.')
    print('GPU container check passed: '+report['gpu_uuid']+'; '+str(len(configs))+' configuration(s).', flush=True)
    return report


def require_docker():
    """Check the engine and Compose; do not install software or start containers."""
    if platform.system() != 'Linux':
        raise ValueError('Run this batch in Bash on a Linux GPU host or GPU-enabled WSL 2, not Windows PowerShell.')
    wsl = 'microsoft' in platform.release().lower()
    hint = (' In Windows, start Docker Desktop in Linux-container mode and enable Settings > Resources > '
            'WSL Integration for this Ubuntu distribution, then reopen its terminal.' if wsl else
            ' Install and start Docker Engine with the Compose v2 plugin, and grant this user Docker access.')
    docker = shutil.which('docker')
    if not docker:
        raise ValueError('Docker CLI not found on PATH.' + hint +
                         ' The runner can build images automatically, but Docker is a host prerequisite. '
                         'No model request or trial was started.')

    def query(args, failure):
        try:
            result = subprocess.run([docker, *args], capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError(failure + hint + ' No model request or trial was started.') from None
        if result.returncode:
            raise ValueError(failure + hint + ' No model request or trial was started.')
        return result.stdout.strip()

    engine = query(['info', '--format', '{{.OSType}}'],
                   'Docker CLI exists, but the Docker daemon is unavailable to this user (service, context or permission).')
    if engine != 'linux':
        raise ValueError('Docker must use Linux containers for these task images. No model request or trial was started.')
    version = query(['compose', 'version', '--short'], 'Docker Compose v2 is missing or unavailable.')
    if not version.lstrip('v').startswith('2.'):
        raise ValueError('Docker Compose v2 is required. No model request or trial was started.')
