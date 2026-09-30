#!/usr/bin/env python3
"""Docker delivery boundary: image recipes, environment checks and owned resources.

The evaluation state machine stays in difficulty_eval. This module also serves as
its container entry point; credentials are read from a private launcher mount.
"""
from __future__ import annotations

from contextlib import contextmanager, suppress
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from difficulty_release import digest, load_build_info, runtime_files, source_files

ROOT = Path(__file__).resolve().parents[1]


class DeliveryError(ValueError):
    pass


def safe_work_dir(value, cwd=None):
    path = Path(value or Path(cwd or Path.cwd()) / 'topogym-work').expanduser().resolve()
    if any(c in str(path) for c in ':,\n\r'):
        raise DeliveryError('work-dir cannot contain colon, comma or newline')
    return path


def resource_labels(workspace, run_id, release_id, role='work', owner=None):
    return {'topogym.workspace': workspace, 'topogym.difficulty-run': run_id,
            'topogym.release': release_id, 'topogym.role': role,
            'topogym.owner': owner or os.environ.get('TOPOGYM_CONTROLLER', '')}


def label_args(labels):
    return [x for key, value in labels.items() for x in ('--label', f'{key}={value}')]


def decorate_compose(document, labels, gpu_uuid, *, uid=None, gid=None):
    """Freeze stable labels/GPU in generated packages; owner changes on resume."""
    labels = dict(labels, **{'topogym.owner': '${TOPOGYM_CONTROLLER}'})
    for name, service in document['services'].items():
        service.setdefault('labels', {}).update(labels)
        devices = service.get('deploy', {}).get('resources', {}).get('reservations', {}).get('devices', [])
        for device in devices:
            if device.get('driver') == 'nvidia':
                device.pop('count', None)
                device['device_ids'] = [gpu_uuid]
                service.setdefault('environment', {})['NVIDIA_VISIBLE_DEVICES'] = gpu_uuid
        # The trusted sidecar writes bind-mounted evidence as the caller.
        if name == 'sim' and uid is not None:
            service['user'] = f'{uid}:{gid}'
            service.setdefault('environment', {})['HOME'] = '/tmp'
    document.setdefault('networks', {}).setdefault('default', {}).setdefault('labels', {}).update(labels)
    return document


class Delivery:
    def __init__(self, work, commands, *, gpu_device='0', run_id='check', release_lock=None, cuda_flavor='cu128'):
        from cuda_profiles import PROFILES
        if cuda_flavor not in PROFILES:
            raise DeliveryError('invalid CUDA profile')
        self.cuda_flavor = cuda_flavor
        self.work, self.commands, self.run_id = Path(work), commands, run_id
        self.info = load_build_info(ROOT)
        if self.info is None:
            raise DeliveryError('container release build-info is missing')
        self.release_id = self.info['release_id']
        self.workspace = hashlib.sha256(str(self.work).encode()).hexdigest()
        self.owner = os.environ.get('TOPOGYM_CONTROLLER', '')
        if not self.owner:
            raise DeliveryError('controller identity missing; use the Docker launcher')
        self.gpu_device, self.gpu_uuid = gpu_device, None
        self.images = {}
        self.lock_id = None
        self.release_lock = None
        if release_lock:
            self.release_lock = json.loads(Path(release_lock).read_text())
            import jsonschema
            schema = json.loads((ROOT / 'images/difficulty-eval/release.schema.json').read_text())
            try:
                jsonschema.validate(self.release_lock, {'$ref': '#/$defs/published', '$defs': schema['$defs']})
            except jsonschema.ValidationError:
                raise DeliveryError('invalid published release.lock schema') from None
            if self.release_lock.get('release_id') != self.release_id:
                raise DeliveryError('release.lock does not match controller source')
            if self.release_lock.get('cuda_flavor', 'cu128') != self.cuda_flavor:
                raise DeliveryError('release.lock CUDA profile differs from --cuda-flavor')
            declared = self.inspect(self.release_lock['images']['controller'], 'image')
            if declared is None or declared['Id'] != self.inspect(self.owner)['Image']:
                raise DeliveryError('release.lock controller digest does not match this container')
            for role in ('runtime', 'agent', 'client'):
                value = self.release_lock['images'][role]
                if not re.fullmatch(r'[A-Za-z0-9./:_-]+@sha256:[a-f0-9]{64}', value):
                    raise DeliveryError('published release images must use registry digests')
        for name in ('logs', 'cache', 'cache/build-locks', 'cache/tmp'):
            (self.work / name).mkdir(parents=True, exist_ok=True)
        self.commands.env['TMPDIR'] = str(self.work / 'cache/tmp')
        self.commands.env['TOPOGYM_WORKSPACE'] = self.workspace

    def command(self, args, **kwargs):
        return self.commands.run_command(args, **kwargs)

    def inspect(self, reference, kind='container'):
        # Query existence separately: a broken daemon must not look like a dead owner.
        if kind == 'container':
            _, rows = self.command(['docker', 'ps', '-aq', '--no-trunc', '--filter', f'name=^/{reference}$'],
                                   capture=True, check=True, timeout=30)
            if not rows.strip():
                return None
        code, text = self.command(['docker', kind, 'inspect', reference], capture=True, timeout=30)
        if code:
            if kind == 'image' and ('No such image' in text or 'No such object' in text):
                return None
            raise DeliveryError(f'cannot inspect {kind} identity')
        return json.loads(text)[0]

    def labels(self, role='work'):
        return resource_labels(self.workspace, self.run_id, self.release_id, role, self.owner)

    def resolve_gpu(self):
        # Docker has already selected one host device. NVML indices inside this
        # container can differ from host indices; resolve the sole visible UUID.
        _, text = self.command(['nvidia-smi', '--query-gpu=uuid',
                               '--format=csv,noheader'], capture=True, check=True, timeout=30)
        uuid = text.strip()
        if not re.fullmatch(r'GPU-[A-Za-z0-9-]+', uuid):
            raise DeliveryError('GPU selection must resolve to exactly one physical GPU UUID')
        if self.gpu_device.startswith('GPU-') and uuid != self.gpu_device:
            raise DeliveryError('visible GPU does not match requested UUID')
        self.gpu_uuid = uuid
        self.commands.env.update(TOPOGYM_GPU_UUID=uuid,
                                 TOPOGYM_RESOURCE_LABELS=json.dumps(self.labels()),
                                 TOPOGYM_HOST_UID=str(os.getuid()), TOPOGYM_HOST_GID=str(os.getgid()))
        return uuid

    def cleanup(self, owner=None):
        """Only resources bearing our role and owner labels; never the controller."""
        owner = owner or self.owner
        filters = ['--filter', 'label=topogym.role=work', '--filter', f'label=topogym.owner={owner}']
        _, rows = self.command(['docker', 'ps', '-aq', *filters], capture=True, check=True, timeout=30)
        ids = rows.split()
        if ids:
            self.command(['docker', 'rm', '-f', *ids], check=True, timeout=30)
        _, rows = self.command(['docker', 'network', 'ls', '-q', *filters], capture=True, check=True, timeout=30)
        if rows.split():
            self.command(['docker', 'network', 'rm', *rows.split()], check=True, timeout=30)

    @contextmanager
    def gpu_lock(self):
        """Daemon-wide atomic ownership, independent of work-dir file locks."""
        if not self.gpu_uuid:
            self.resolve_gpu()
        name = 'topogym-gpu-lock-' + self.gpu_uuid.lower()
        image = self.inspect(self.owner)['Image']
        for attempt in range(3):
            code, output = self.command(['docker', 'create', '--name', name, *label_args(self.labels('gpu-lock')),
                                         '--entrypoint', '/bin/true', image], capture=True, timeout=30)
            if code == 0:
                self.lock_id = output.strip()
                break
            existing = self.inspect(name)
            if not existing:
                raise DeliveryError('could not create the Docker GPU lock')
            labels = existing['Config'].get('Labels') or {}
            if labels.get('topogym.role') != 'gpu-lock' or not labels.get('topogym.owner'):
                raise DeliveryError('GPU lock name belongs to an unrecognized resource')
            previous_owner = labels['topogym.owner']
            controller = self.inspect(previous_owner)
            if controller and controller['State']['Running']:
                raise DeliveryError('another active controller owns this GPU')
            self.cleanup(previous_owner)
            self.command(['docker', 'rm', existing['Id']], check=True, timeout=30)
        if not self.lock_id:
            raise DeliveryError('GPU lock changed concurrently; retry after the active run finishes')
        try:
            yield
        finally:
            try:
                self.cleanup()
            finally:
                self.command(['docker', 'rm', '-f', self.lock_id], check=True, timeout=30)
                self.lock_id = None

    def ensure_image(self, role, source, *, inputs, dockerfile, build_args=None):
        from difficulty_eval import lock, progress
        fingerprint = digest(inputs)
        reference = (self.release_lock['images'][role] if self.release_lock else
                     f'topogym-local/difficulty-{role}:{fingerprint}')
        with lock(self.work / 'cache/build-locks' / f'{role}-{fingerprint}.lock', 'image build already in progress'):
            actual = self.inspect(reference, 'image')
            if actual is None:
                log = self.work / 'logs' / f'{role}-build-{fingerprint}.log'
                progress(f'Preparing {role} image: {reference} | log: {log}')
                if self.release_lock:
                    cmd = ['docker', 'pull', reference]
                else:
                    cmd = ['docker', 'build', '--label', f'topogym.inputs={fingerprint}', '-t', reference,
                           '-f', source / dockerfile]
                    for key, value in (build_args or {}).items():
                        cmd += ['--build-arg', f'{key}={value}']
                    cmd += [source]
                self.command(cmd, log=log, monitor=True, check=True)
                actual = self.inspect(reference, 'image')
            if actual['Architecture'] != 'amd64':
                raise DeliveryError('runtime image architecture is not amd64')
            if (actual['Config'].get('Labels') or {}).get('topogym.inputs') != fingerprint:
                raise DeliveryError(f'{role} cache image identity changed')
            self.images[role] = dict(image=reference, id=actual['Id'], inputs_sha256=fingerprint)
        return reference

    def ensure_images(self, source=ROOT):
        from cuda_profiles import build_args, check_driver
        files = source_files(source)
        runtime_inputs = runtime_files(files)
        if digest(runtime_inputs) != self.info['runtime_inputs_sha256']:
            raise DeliveryError('runtime build inputs differ from this controller release')
        if self.cuda_flavor == 'cu130':
            _, versions = self.command(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'],
                                       capture=True, check=True, timeout=30)
            for version in versions.splitlines():
                check_driver(self.cuda_flavor, version.strip())
        arguments = build_args(source, self.cuda_flavor)
        runtime_inputs = dict(runtime_inputs, cuda_flavor=self.cuda_flavor, build_args=arguments)
        runtime = self.ensure_image('runtime', source, inputs=runtime_inputs, dockerfile='images/topogym/Dockerfile',
                                    build_args=arguments)
        client_inputs = {p: h for p, h in files.items() if p in (
            'images/difficulty-eval/client.Dockerfile', 'images/difficulty-eval/client.Dockerfile.dockerignore',
            'requirements/difficulty-eval-client.lock')}
        self.ensure_image('client', source, inputs=client_inputs, dockerfile='images/difficulty-eval/client.Dockerfile')
        agent_inputs = {p: h for p, h in files.items() if p.startswith('images/difficulty-eval/runtime-agent.')}
        agent_inputs['runtime_image_id'] = self.images['runtime']['id']
        self.ensure_image('agent', source, inputs=agent_inputs, dockerfile='images/difficulty-eval/runtime-agent.Dockerfile',
                          build_args={'RUNTIME_IMAGE': runtime})
        self.commands.env['TOPOGYM_CLIENT_IMAGE'] = self.images['client']['image']
        self.commands.env['TOPOGYM_AGENT_IMAGE'] = self.images['agent']['image']
        return runtime

    def verify_images(self):
        for role, expected in self.images.items():
            actual = self.inspect(expected['image'], 'image')
            if actual is None or actual['Id'] != expected['id']:
                raise DeliveryError(f'frozen {role} image changed')

    def environment_check(self, source=ROOT):
        from difficulty_eval import progress
        from sample_difficulty_instances import atomic_json
        progress('=== environment check: Docker / paths / resources / GPU / assets (no model) ===')
        marker = self.work / 'check.json'
        if marker.exists():
            marker.rename(self.work / f'check.previous.{time.time_ns()}.json')
        atomic_json(marker, dict(passed=False, status='started', release_id=self.release_id, started_at=time.time()))
        self.command(['docker', 'compose', 'version'], check=True, timeout=30)
        self.commands.check_resources()
        if shutil.disk_usage(self.work).free < 20 * 1024**3:
            raise DeliveryError('less than 20 GiB free in work-dir; free space before building/running')
        if not self.gpu_uuid:
            self.resolve_gpu()
        # Serialize probes too: a check must not compete with another evaluation.
        runtime = self.ensure_images(source)
        marker = self.work / 'cache' / f'path-probe-{self.owner}.txt'
        marker.write_text(self.workspace)
        try:
            code = ('from pathlib import Path; import os; p=Path(' + repr(str(marker)) + '); '
                    'assert p.read_text()==' + repr(self.workspace) + '; p.write_text("checked")')
            self.command(['docker', 'run', '--rm', *label_args(self.labels()), '--user', f'{os.getuid()}:{os.getgid()}',
                          '--mount', f'type=bind,src={self.work},dst={self.work}', self.images['client']['image'],
                          'python', '-c', code], check=True, timeout=60)
            if marker.read_text() != 'checked' or marker.stat().st_uid != os.getuid():
                raise DeliveryError('sibling container path/permission probe failed')
        finally:
            marker.unlink(missing_ok=True)
        log = self.work / 'logs' / f'environment-check-{time.time_ns()}.log'
        self.command(['docker', 'run', '--rm', '--gpus', f'device={self.gpu_uuid}', '--runtime', 'nvidia',
                      '-e', 'NVIDIA_DRIVER_CAPABILITIES=all', '-e', f'NVIDIA_VISIBLE_DEVICES={self.gpu_uuid}',
                      *label_args(self.labels()), runtime,
                      'python', '-c', GPU_CHECK], log=log, monitor=True, check=True, timeout=180)
        record = dict(passed=True, scope='container_gpu_paths_assets', physical_scenes_qualified=False,
                      release_id=self.release_id, cuda_flavor=self.cuda_flavor, gpu_uuid=self.gpu_uuid, images=self.images,
                      work_dir=str(self.work), log=str(log), checked_at=time.time())
        atomic_json(self.work / 'check.json', record)
        progress(f'Environment check passed | {self.work / "check.json"}')
        return record


GPU_CHECK = r'''
import hashlib, importlib.metadata as m, json, os
from pathlib import Path
import runpy
runpy.run_path('/opt/check_gpu_stack.py', run_name='__main__')
for name in ('genesis-world', 'gs-nyx-plugin', 'gs-nyx', 'pyuipc'):
    print(name, m.version(name), flush=True)
assert Path('/opt/topogym/SOURCE.json').is_file()
robots = Path('/opt/topogym-assets/robots')
assert (robots/'aloha/aloha.xml').is_file() and (robots/'robotiq_2f85/2f85.xml').is_file(), 'robot source assets missing'
assert list(robots.rglob('*.stl')), 'robot meshes missing'
import genesis
root = Path(os.environ['TOPOGYM_VISUAL_ASSET_ROOT'])
expected = {'studio_small_09_2k.hdr': '36724313c0fc66dab126ff90f081b85a0b1ef47be65eda1417bd20b033f0573f',
'wood_table_001_diff_1k.png': 'aef45ab36d9f258b80edf278d417920b7326ad77c341d6618498d4598c59fd2c',
'wood_table_001_nor_gl_1k.png': '3d1dc2cc14cd9a3d2bc0035560aa715f4f8786902b4b72e78135f1d097428f98'}
for name, sha in expected.items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == sha, name
import ctypes
ctypes.CDLL('libvulkan.so.1'); ctypes.CDLL('libEGL.so.1')
import subprocess
probe = subprocess.run(['vulkaninfo', '--summary'], capture_output=True, text=True, timeout=30)
assert probe.returncode == 0 and 'NVIDIA' in probe.stdout, 'NVIDIA Vulkan device unavailable'
print(json.dumps({'cuda': True, 'assets': True, 'graphics_libraries': True}))
'''


class Tee:
    def __init__(self, stream, file):
        self.stream, self.file = stream, file
    def write(self, text):
        self.stream.write(text); self.file.write(text); self.file.flush()
    def flush(self):
        self.stream.flush(); self.file.flush()
    def isatty(self):
        return self.stream.isatty()
    def fileno(self):
        return self.stream.fileno()


def main(argv=None):
    os.umask(0o077)
    argv = list(sys.argv[1:] if argv is None else argv)
    Path.home().mkdir(parents=True, exist_ok=True)
    work = None
    if argv[:1] == ['--launch-input']:
        if len(argv) != 2:
            raise DeliveryError('invalid launcher input')
        launch = Path(argv[1])
        argv = launch.joinpath('args').read_bytes().decode().split('\0')[:-1]
        work = safe_work_dir(launch.joinpath('work-dir').read_text())
        # The selected fallback is the only host API variable sent across the boundary.
        key = launch.joinpath('api-key').read_text()
        if key:
            os.environ['TOPOGYM_LAUNCH_KEY'] = key
        release_lock = launch / 'release.lock.json'
        if release_lock.is_file() and '--release-lock' not in argv:
            argv += ['--release-lock', str(release_lock)]
    if argv[:1] == ['auth']:
        if argv[1:] not in (['login', '--device-auth'], ['login'], ['status']):
            raise DeliveryError('use auth login --device-auth or auth status')
        Path(os.environ.get('CODEX_HOME', str(Path.home()/'.codex'))).mkdir(parents=True, exist_ok=True)
        from difficulty_eval import lock
        with lock(Path(os.environ['CODEX_HOME']) / '.auth.lock', 'another operation is using this login'):
            return subprocess.call(['codex', '-c', 'cli_auth_credentials_store="file"',
                                    *(['login', 'status'] if argv[1:] == ['status'] else ['login', '--device-auth'])])
    if work:
        argv += ['--work-dir', str(work)]
    if argv[:1] == ['check']:
        import argparse
        from difficulty_eval import ArgumentParser, Commands, on_signal
        import signal
        parser = ArgumentParser(description='Check Docker/GPU/paths/assets without model calls.', allow_abbrev=False)
        parser.add_argument('--work-dir', type=Path)
        parser.add_argument('--gpu-device', default='0')
        parser.add_argument('--release-lock', type=Path)
        parser.add_argument('--cuda-flavor', choices=('cu128', 'cu130'), default='cu128')
        args = parser.parse_args(argv[1:])
        work = safe_work_dir(args.work_dir)
        work.mkdir(parents=True, exist_ok=True)
        configure_host_metrics()
        commands = Commands(dict(os.environ), work)
        delivery = Delivery(work, commands, gpu_device=args.gpu_device, release_lock=args.release_lock,
                            cuda_flavor=args.cuda_flavor)
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, on_signal)
        with delivery.gpu_lock():
            delivery.environment_check()
        return 0
    from difficulty_eval import main as evaluate
    if work:
        (work/'logs').mkdir(parents=True, exist_ok=True)
        log = work / 'logs' / f'controller-{time.time_ns()}.log'
        original = sys.stdout, sys.stderr
        with log.open('a') as stream:
            sys.stdout, sys.stderr = Tee(sys.stdout, stream), Tee(sys.stderr, stream)
            try:
                return evaluate(argv)
            finally:
                sys.stdout, sys.stderr = original
    return evaluate(argv)


def configure_host_metrics():
    import psutil
    root = Path('/host/proc')
    if not (root/'stat').is_file() or not (root/'meminfo').is_file():
        raise DeliveryError('host /proc metrics mount is unavailable')
    psutil.PROCFS_PATH = str(root)


if __name__ == '__main__':
    from difficulty_eval import EvaluationError, Interrupted
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, Interrupted):
        print('Interrupted; evidence retained', file=sys.stderr)
        raise SystemExit(130)
    except (ValueError, OSError, EvaluationError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        raise SystemExit(2)
