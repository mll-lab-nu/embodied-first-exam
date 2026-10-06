"""Host-only fix for Harbor 0.23.0 nested model IDs; leaves task images unchanged."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

OLD = '        model = self.model_name.split("/")[-1]\n'
NEW = '        model = self.model_name.split("/", 1)[-1]\n'
# The exact wheel after the existing private-auth patch, verified by the caller's
# receipt on upgrades and by patch_harbor.py on a fresh installation.
EXPECTED = '5f91c4a480a1c10296134a0a281d1e26c026e3d4a9f8bfc3c340fe7d2bda2405'
PATCH = 'scripts/patch_agent_batch_providers.py'


def patch_source(source):
    if source.count(NEW) == 1 and OLD not in source:
        return source
    if source.count(OLD) != 1 or NEW in source:
        raise ValueError('Harbor Codex model selection changed; review the provider patch')
    return source.replace(OLD, NEW)


def apply(root):
    root = Path(root)
    receipt_path = Path(sys.prefix) / 'topogym-runner.json'
    receipt = json.loads(receipt_path.read_text())
    expected_files = {'images/difficulty-eval/patch_harbor.py', 'requirements/difficulty-eval-controller.lock'}
    if set(receipt['files']) not in (expected_files, expected_files | {PATCH}):
        raise ValueError('unexpected runner receipt; preserve the installation')
    for name, wanted in receipt['files'].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != wanted:
            raise ValueError('runner receipt differs from checkout; preserve the installation')
    if set(receipt['modules']) != {'harbor.agents.installed.codex', 'harbor.environments.docker.docker'}:
        raise ValueError('unexpected runner module receipt')
    path = Path(importlib.util.find_spec('harbor.agents.installed.codex').origin)
    source = path.read_text()
    original = source.replace(NEW, OLD)
    if hashlib.sha256(original.encode()).hexdigest() != EXPECTED:
        raise ValueError('Harbor Codex source changed; review the provider patch')
    for name, wanted in receipt['modules'].items():
        actual = hashlib.sha256(Path(importlib.util.find_spec(name).origin).read_bytes()).hexdigest()
        if actual != wanted and not (name == 'harbor.agents.installed.codex' and wanted == EXPECTED and PATCH not in receipt['files']):
            raise ValueError('installed Harbor source changed; preserve the installation')
    updated = patch_source(source)
    if updated != source:
        temporary = path.with_suffix('.provider-tmp')
        temporary.write_text(updated); temporary.replace(path)
    receipt['modules']['harbor.agents.installed.codex'] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt['files'][PATCH] = hashlib.sha256((root / PATCH).read_bytes()).hexdigest()
    temporary = receipt_path.with_suffix('.provider-tmp')
    temporary.write_text(json.dumps(receipt, indent=2) + '\n'); temporary.replace(receipt_path)
    if updated != source:
        print('Native Harbor Codex preserves complete provider model IDs.')


if __name__ == '__main__':
    apply(sys.argv[1])
