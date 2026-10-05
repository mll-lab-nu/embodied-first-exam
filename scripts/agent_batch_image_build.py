"""Freeze/build helper image materials without rewriting prepared task bindings.

Maintainers freeze a tested runtime's software and audited native wheel. Helpers
download the pinned base and Python/OS dependencies, using the bundled wheel.
Only a byte-checked equivalent runtime may substitute for the authoring image ID.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid

from agent_batch_bootstrap import run, guard
from agent_batch_contract import digest, inventory, read, relative, save, sha

ROOT = Path(__file__).resolve().parents[1]
BASE = 'python:3.11.15-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3'


def inspect_contents(image_id, probe_root):
    """No GPU/model, no network, immutable image ID and read-only probe scripts."""
    probe_root = Path(probe_root).resolve()
    name = 'tg-build-probe-' + uuid.uuid4().hex
    try:
        output = run(['docker', 'run', '--rm', '--name', name, '--network', 'none', '--read-only',
                      '--tmpfs', '/tmp', '-e', 'PYTHONDONTWRITEBYTECODE=1',
                      '--mount', f'type=bind,src={probe_root},dst=/probe,readonly',
                      '--entrypoint', 'python', image_id, '/probe/probe.py', '/probe/identity.py'], capture=True)
        return json.loads(output)
    finally:
        # A killed docker client may leave its container alive. Only our named probe.
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def validate_spec(spec):
    if not isinstance(spec, dict) or set(spec) != {'manifest', 'sha256', 'expected'}:
        raise ValueError('build source needs manifest, sha256 and expected contents')
    relative(spec['manifest'])
    if not re.fullmatch('[a-f0-9]{64}', spec['sha256']):
        raise ValueError('invalid build manifest hash')
    expected = spec['expected']
    if (not isinstance(expected, dict) or set(expected) != {'schema_version', 'runtime', 'packages', 'dpkg', 'robots', 'visuals'}
            or expected['schema_version'] != 1 or not expected['packages'] or not expected['dpkg']):
        raise ValueError('incomplete frozen image contents')
    return spec


def materials(root, spec):
    validate_spec(spec)
    root = Path(root).resolve()
    path = root / relative(spec['manifest'])
    if path.is_symlink() or not path.resolve().is_relative_to(root) or sha(path) != spec['sha256']:
        raise ValueError('image build manifest changed')
    manifest = read(path)
    if (manifest.get('schema_version') != 1 or manifest.get('platform') != 'linux/amd64'
            or manifest.get('expected') != spec['expected'] or not manifest.get('files')):
        raise ValueError('image build manifest differs from assignment')
    context = path.parent / 'context'
    if inventory(context) != manifest['files']:
        raise ValueError('frozen image build materials changed')
    return manifest, context


def assert_contents(observed, expected):
    if observed != expected:
        changed = sorted(k for k in set(observed) | set(expected) if observed.get(k) != expected.get(k))
        raise ValueError('rebuilt image contents differ from frozen reference: ' + ', '.join(changed))


def build(root, spec, reference):
    manifest, context = materials(root, spec)
    # Build under an isolated temporary tag. Never replace a tag before verification.
    temporary = 'topogym-local/helper-rebuild:' + spec['sha256'][:20]
    print('Building frozen helper runtime; this is outside the trial budget.', flush=True)
    run(['docker', 'build', '--platform', manifest['platform'], '--label',
         'topogym.helper-build=' + spec['sha256'], '-t', temporary, str(context)])
    actual = json.loads(run(['docker', 'image', 'inspect', temporary], capture=True))[0]
    observed = inspect_contents(actual['Id'], context / 'probe')
    assert_contents(observed, spec['expected'])
    run(['docker', 'tag', actual['Id'], reference])
    return actual, observed


def _copy(source, target):
    if source.is_symlink() or not source.is_file():
        raise ValueError('build input must be a regular file: ' + str(source))
    guard(); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)


def freeze(source, image, wheel_image, output, *, snapshot):
    source = Path(source).resolve(); output = Path(output).resolve()
    if output.exists():
        raise ValueError('preserve existing frozen materials; choose a new output')
    if not re.fullmatch(r'\d{8}T\d{6}Z', snapshot):
        raise ValueError('use a fixed Debian snapshot timestamp YYYYMMDDTHHMMSSZ')
    actual = json.loads(run(['docker', 'image', 'inspect', image], capture=True))[0]
    if actual['Architecture'] != 'amd64' or actual['Os'] != 'linux':
        raise ValueError('helper build currently supports the tested linux/amd64 runtime')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.freeze-', dir=output.parent) as td:
        stage = Path(td) / 'materials'; context = stage / 'context'; context.mkdir(parents=True)
        _copy(ROOT / 'scripts/agent_batch_image_probe.py', context / 'probe/probe.py')
        _copy(source / 'topogym/simulator/frozen_binding.py', context / 'probe/identity.py')
        expected = inspect_contents(actual['Id'], context / 'probe')
        # Reuse the exact, already audited native dependency. Recompiling it would
        # invalidate the native binary/build-record hashes in existing task locks.
        name = 'tg-wheel-export-' + uuid.uuid4().hex
        try:
            run(['docker', 'create', '--name', name, wheel_image], capture=True)
            run(['docker', 'cp', name + ':/out/wheels', context / 'ipc'])
        finally:
            subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        record = read(context / 'ipc/uipc-build.json')
        if (sha(context / 'ipc/uipc-build.json') != expected['runtime']['uipc_build_sha256']
                or sha(context / 'ipc' / relative(record['wheel'])) != record['wheel_sha256']):
            raise ValueError('native wheel/build record differs from the prepared runtime')
        omitted = {'agents', 'planning', 'data', 'deferred', 'legacy', 'redundants', 'rollout_simulation', '__pycache__'}
        for folder in ('topogym', 'assets/robots'):
            for path in sorted((source / folder).rglob('*')):
                rel = path.relative_to(source)
                if (folder == 'topogym' and (set(rel.parts) & omitted or path.suffix in ('.md', '.pyc'))):
                    continue
                if path.is_file():
                    _copy(path, context / rel)
        profile = record['version'].rsplit('cuda', 1)[-1]
        flavor = {'128': 'cu128', '130': 'cu130'}.get(profile)
        if not flavor:
            raise ValueError('unsupported wheel CUDA profile')
        lock = 'difficulty-eval-runtime' + ('-cu130' if flavor == 'cu130' else '') + '.lock'
        for src, dest in [('requirements/' + lock, 'runtime.lock'),
                          ('images/topogym/verify_uipc_wheel.py', 'verify_uipc_wheel.py'),
                          ('images/topogym/check_gpu_stack.py', 'check_gpu_stack.py'),
                          ('images/topogym/prune.py', 'prune.py'),
                          ('scripts/prepare_nyx_studio.py', 'prepare_nyx_studio.py')]:
            _copy(source / src, context / dest)
        save(context / 'os-packages.json', expected['dpkg'])
        _copy(ROOT / 'scripts/agent_batch_image_os.py', context / 'install_os.py')
        save(context / 'os-source.json', dict(snapshot=snapshot))
        # Pin the installer artifact too, rather than accepting a replacement wheel
        # with an unchanged version number. It is small and kept with the recipe.
        uv_version = expected['packages']['uv']['version']
        run(['docker', 'run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}', '-e', 'HOME=/tmp',
             '--mount', f'type=bind,src={context},dst=/materials', '--entrypoint', 'python', actual['Id'],
             '-m', 'pip', 'download', '--disable-pip-version-check', '--no-cache-dir', '--no-deps', '--only-binary=:all:',
             '--dest', '/materials/installers', 'uv==' + uv_version])
        wheels = list((context / 'installers').glob('*.whl'))
        if len(wheels) != 1:
            raise ValueError('expected one pinned uv installer')
        (context / 'installer.lock').write_text('uv @ file:///opt/installers/' + wheels[0].name + ' --hash=sha256:' + sha(wheels[0]) + '\n')
        recipe = (ROOT / 'images/helper-build/Dockerfile.template').read_text()
        (context / 'Dockerfile').write_text(recipe.replace('@BASE@', BASE).replace('@CUDA@', flavor))
        (context / '.dockerignore').write_text('**/__pycache__\n**/*.pyc\n.git\n')
        manifest = dict(schema_version=1, platform='linux/amd64', reference_image=dict(reference=image, id=actual['Id']),
                        expected=expected, files=inventory(context), snapshot=snapshot,
                        native_dependency='exact audited wheel; bundled build input, not a Docker image')
        save(stage / 'manifest.json', manifest)
        stage.rename(output)
    return dict(manifest=str(output / 'manifest.json'), sha256=sha(output / 'manifest.json'), expected=expected)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path); p.add_argument('--image')
    p.add_argument('--wheel-image'); p.add_argument('--output', type=Path)
    p.add_argument('--apt-snapshot')
    p.add_argument('--verify-build', type=Path, help='maintainer rehearsal using a frozen material manifest')
    p.add_argument('--repository', type=Path, default=ROOT); p.add_argument('--tag')
    p.add_argument('--receipt', type=Path)
    p.add_argument('--image-sources-output', type=Path, help='write the publisher image-sources JSON after freezing')
    a = p.parse_args()
    if a.verify_build:
        if not a.tag or not a.receipt: p.error('--verify-build needs --tag and --receipt')
        manifest=read(a.verify_build)
        spec=dict(manifest=str(a.verify_build.resolve().relative_to(a.repository.resolve())),
                  sha256=sha(a.verify_build),expected=manifest['expected'])
        actual,observed=build(a.repository,spec,a.tag)
        result=dict(verified=True,image=a.tag,id=actual['Id'],reference_id=manifest['reference_image']['id'],
                    manifest_sha256=spec['sha256'],observed=observed)
        save(a.receipt,result)
        print(json.dumps({k:v for k,v in result.items() if k!='observed'},indent=2))
        return
    if not all((a.source,a.image,a.wheel_image,a.output,a.apt_snapshot)):
        p.error('freeze requires --source, --image, --wheel-image, --output and --apt-snapshot')
    result = freeze(a.source, a.image, a.wheel_image, a.output, snapshot=a.apt_snapshot)
    if a.image_sources_output:
        spec=dict(result,manifest=str(Path(result['manifest']).relative_to(a.repository.resolve())))
        save(a.image_sources_output,{a.image:{'build':spec}})
    print(json.dumps({k: v for k, v in result.items() if k != 'expected'}, indent=2))


if __name__ == '__main__':
    main()
