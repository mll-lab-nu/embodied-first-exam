#!/usr/bin/env python3
"""Record already prepared server assets/runtimes; never download or use secrets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for data in iter(lambda: handle.read(1024*1024), b''):
            h.update(data)
    return h.hexdigest()


def git(root):
    try:
        return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except subprocess.SubprocessError:
        return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--native-root', type=Path, required=True)
    a = p.parse_args()
    versions = set()
    for path in (a.root/'data/LIBERO-Pro/.cache/huggingface/download').rglob('*.metadata'):
        versions.add(path.read_text().splitlines()[0])
    native = a.native_root
    binaries = ['codex/package/vendor/x86_64-unknown-linux-musl/bin/codex',
                'node-v26.0.0-linux-x64/bin/node', 'bin/native_isolated.py']
    files = {str(f.relative_to(native)): sha(f) for f in (native/'pi/packages').rglob('*')
             if f.is_file() and 'node_modules' not in f.parts and f.suffix in {'.ts', '.json'}
             and '.git' not in f.parts}
    models = json.loads((a.root/'data/models_manifest.json').read_text())
    robot = Path(os.environ.get('ROBOT_DESCRIPTIONS_CACHE',
        str(Path.home()/'.cache/robot_descriptions')))/'example-robot-data'
    panda = robot/'robots/panda_description'
    result = {'libero_code_commit': git(a.root/'LIBERO-PRO'),
              'libero_dataset': {'repo': 'zhouxueyang/LIBERO-Pro', 'downloaded_revisions': sorted(versions)},
              'perception_models': models,
              'native': {'pi_source_commit': git(native/'pi'),
                  'runtime_file_sha256': {str(f): sha(native/f) for f in binaries},
                  'pi_source_files': files},
              'optional_services': {'sam3': 'disabled', 'graspgen': 'disabled',
                  'grasp_mode': 'upstream analytic fallback; framework validation only',
                  'pyroki_git_commit': '388e43e1fc0d0ee382968d3dd72970fd62a0450c',
                  'panda_robot': {'repository_commit': git(robot),
                      'file_sha256': {str(f.relative_to(robot)): sha(f)
                          for f in sorted(panda.rglob('*')) if f.is_file()}}}}
    for name in ('venv', 'pyroki-managed'):
        result[name+'_packages'] = subprocess.check_output(
            ['uv', 'pip', 'freeze', '--python', str(a.root/name/'bin/python')], text=True).splitlines()
    path = a.root/'data/assets_manifest.json'
    path.write_text(json.dumps(result, indent=2))
    print(path)


if __name__ == '__main__':
    main()
