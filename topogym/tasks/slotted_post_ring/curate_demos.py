"""Move superseded task videos to bootstrap storage and repair live references."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def curate(keep):
    video_root = ROOT / 'demos/slotted_post_ring'
    history = ROOT / 'runs/environment_bootstrap/slotted_post_ring/historical_demos'
    mapping = {}
    records = []
    for source in sorted(video_root.rglob('*.mp4')):
        if source.name.startswith(keep + '_'):
            continue
        relative = source.relative_to(video_root)
        target = history / relative
        if source.is_symlink():
            raise ValueError(f'Expected independent file: {source}')
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        digest = sha(source)
        if sha(target) != digest:
            raise ValueError(f'Conflicting destination: {target}')
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(target),
                        '-f', 'null', '-'], check=True, capture_output=True)
        old, new = str(source.relative_to(ROOT)), str(target.relative_to(ROOT))
        mapping[old] = new
        records.append(dict(source=old, destination=new, sha256=digest, full_decode=True))
    # Update live documentation and archive indexes, never frozen source snapshots.
    candidates = [ROOT/'README.md', ROOT/'demos/README.md']
    for folder in ('docs', 'configs', 'reports', 'runs/demo_metadata/slotted_post_ring'):
        candidates.extend(p for p in (ROOT/folder).rglob('*')
                          if p.suffix in ('.md', '.json', '.yaml') and p.is_file()
                          and 'snapshots' not in p.parts)
    changed = []
    for path in candidates:
        original = path.read_text()
        updated = original
        for old, new in mapping.items():
            old_relative = os.path.relpath(ROOT/old, path.parent)
            new_relative = os.path.relpath(ROOT/new, path.parent)
            updated = updated.replace(old_relative, new_relative)
            updated = updated.replace(old, new)
        if updated != original:
            path.write_text(updated)
            changed.append(str(path.relative_to(ROOT)))
    # Preserve hashes of relocated videos; refresh hashes for rewritten README links.
    for path in (ROOT/'runs/demo_metadata/slotted_post_ring').glob('*/archive_manifest.json'):
        manifest = json.loads(path.read_text())
        for item in manifest.get('evidence', []):
            evidence = path.parent / item['path']
            if str(evidence.relative_to(ROOT)) in changed:
                item['sha256'] = sha(evidence)
        path.write_text(json.dumps(manifest, indent=2) + '\n')
    log = history / f'migration_keep_{keep}.json'
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps(dict(keep_version=keep, videos=records,
                                   rewritten_references=changed), indent=2) + '\n')
    for item in records:
        source, target = ROOT/item['source'], ROOT/item['destination']
        if sha(source) != item['sha256'] or sha(target) != item['sha256']:
            raise RuntimeError('File changed during migration')
        source.unlink()
    for folder in sorted(video_root.rglob('*'), reverse=True):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    print(json.dumps(dict(moved=len(records), kept=len(list(video_root.rglob('*.mp4'))),
                          log=str(log)), indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--keep', required=True, help='Exact version prefix to retain')
    curate(p.parse_args().keep)
