"""Shared fail-closed credential scanning. Never execute inspected files."""
from __future__ import annotations
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import zipfile

DEFAULT_VARS = ('OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'ANTHROPIC_API_KEY', 'HF_TOKEN')
PATTERNS = (('API_TOKEN', re.compile(rb'(?:sk-[A-Za-z0-9_-]{16,}|hf_[A-Za-z0-9]{20,})')),
            ('JWT', re.compile(rb'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}')))
BINARY = {'.npz', '.npy', '.mp4', '.png', '.jpg', '.jpeg', '.stl', '.glb', '.blend', '.gz', '.zip'}
CHUNK = 1024 * 1024

class ScanError(ValueError): pass

def load_env(path):
    values = {}
    for line in Path(path).expanduser().read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'): continue
        match = re.fullmatch(r'(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)', line)
        if not match: raise ScanError('invalid credential dotenv file')
        name, value = match.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'": value = value[1:-1]
        else: value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
        if name in values: raise ScanError('duplicate credential dotenv variable')
        values[name] = value
    return values

def load_secrets(*, env_files=(), variables=(), auth_files=(), process_env=False, pii=False):
    env = dict(os.environ) if process_env else {}
    for path in env_files: env.update(load_env(path))
    names = variables or DEFAULT_VARS
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', n) for n in names):
        raise ScanError('invalid credential variable name')
    secrets = {name: env[name].encode() for name in names if env.get(name)}
    for index, path in enumerate(auth_files):
        data = json.loads(Path(path).expanduser().read_text())
        for key, value in (data.get('tokens') or {}).items():
            if isinstance(value, str) and value and (key != 'account_id' or pii):
                secrets[f'AUTH_{index}_{key.upper()}'] = value.encode()
        if data.get('OPENAI_API_KEY'): secrets[f'AUTH_{index}_API_KEY'] = data['OPENAI_API_KEY'].encode()
    if not secrets: raise ScanError('no credentials loaded; supply --process-env, --env-file or --codex-auth')
    return secrets

def files_under(root):
    root = Path(root)
    if not root.exists() or root.is_symlink(): raise ScanError('scan target missing or symlinked')
    def walk(path):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode): raise ScanError('symlink in scan target')
        if stat.S_ISREG(mode): yield path
        elif stat.S_ISDIR(mode):
            for child in sorted(path.iterdir()): yield from walk(child)
        else: raise ScanError('non-regular file in scan target')
    yield from walk(root)

def matches(data, secrets, patterns=True, pii=False):
    found = []
    for name, value in secrets.items():
        start = 0
        while (start := data.find(value, start)) >= 0:
            found.append((start, start + len(value), name)); start += len(value)
    if patterns:
        for name, pattern in PATTERNS:
            found.extend((m.start(), m.end(), name) for m in pattern.finditer(data))
    if pii:
        found.extend((m.start(), m.end(), 'EMAIL') for m in re.finditer(
            rb'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', data))
    return sorted(found, key=lambda v: (v[0], -v[1]))

def scan_stream(stream, secrets, *, output=None, patterns=True, pii=False, limit=None, guard=lambda: None):
    overlap = max([65536, *map(len, secrets.values())])
    pending, counts, size = b'', {}, 0
    while True:
        guard(); block = stream.read(CHUNK); size += len(block)
        if limit is not None and size > limit: raise ScanError('expanded scan exceeds size limit')
        pending += block
        cutoff = max(0, len(pending) - overlap) if block else len(pending)
        cursor = 0
        for start, end, name in matches(pending, secrets, patterns, pii):
            if start >= cutoff or start < cursor: continue
            counts[name] = counts.get(name, 0) + 1
            if output:
                output.write(pending[cursor:start]); output.write(b'[REDACTED-' + name.encode('ascii', 'replace') + b']')
            cursor = end
        consumed = max(cursor, cutoff)
        if output: output.write(pending[cursor:consumed])
        pending = pending[consumed:]
        if not block: break
    return counts, size

def fingerprint(path):
    info = Path(path).stat()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)

def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()

def scan_tree(root, secrets, *, redact=False, patterns=True, pii=False, guard=lambda: None):
    if not secrets: raise ScanError('no credentials loaded')
    root = Path(root)
    report = dict(schema_version=1, scanned_files=0, scanned_bytes=0, findings=[], redactions=[],
                  rules=list(secrets) + ([p[0] for p in PATTERNS] if patterns else []),
                  coverage='regular-file bytes; zip/npz members and gzip payloads; no pickle or code execution',
                  limitation='unknown secrets and nested compressed payloads are not certified')
    for path in files_under(root):
        guard(); relative = path.relative_to(root).as_posix() if root.is_dir() else path.name
        if matches(relative.encode(), secrets, patterns, pii): raise ScanError('credential-like filename')
        before = fingerprint(path); mode = path.stat().st_mode
        if not mode & 0o444: raise ScanError('scan contains unreadable files')
        with path.open('rb') as stream:
            hits, size = scan_stream(stream, secrets, patterns=patterns, pii=pii, guard=guard)
        compressed = {}
        if path.suffix.lower() in {'.zip', '.npz'}:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if len(infos) > 100000 or sum(i.file_size for i in infos) > 8 * 1024**3:
                    raise ScanError('compressed scan exceeds member/size limits')
                for info in infos:
                    if info.is_dir(): continue
                    if info.filename.lower().endswith(('.zip', '.npz', '.gz', '.tar', '.7z')):
                        raise ScanError('nested compressed artifact cannot be certified')
                    if matches(info.filename.encode(), secrets, patterns, pii): raise ScanError('credential-like member name')
                    with archive.open(info) as stream:
                        found, _ = scan_stream(stream, secrets, patterns=patterns, pii=pii, limit=info.file_size, guard=guard)
                    for name, count in found.items(): compressed[name] = compressed.get(name, 0) + count
        elif path.suffix.lower() == '.gz':
            with gzip.open(path, 'rb') as stream:
                compressed, _ = scan_stream(stream, secrets, patterns=patterns, pii=pii, limit=8*1024**3, guard=guard)
        if fingerprint(path) != before: raise ScanError('file changed while scanning')
        report['scanned_files'] += 1; report['scanned_bytes'] += size
        if hits or compressed:
            finding = dict(path=relative, matches=hits, compressed_matches=compressed)
            report['findings'].append(finding)
            if redact:
                if path.suffix.lower() in BINARY or compressed:
                    raise ScanError('secret in binary/compressed artifact; refusing to corrupt evidence')
                original = sha(path); fd, temp = tempfile.mkstemp(prefix='.redact-', dir=path.parent)
                try:
                    with path.open('rb') as inp, os.fdopen(fd, 'wb') as out:
                        scan_stream(inp, secrets, output=out, patterns=patterns, pii=pii, guard=guard)
                        out.flush(); os.fsync(out.fileno())
                    if fingerprint(path) != before: raise ScanError('file changed while redacting')
                    os.chmod(temp, stat.S_IMODE(mode)); os.replace(temp, path)
                finally:
                    if os.path.exists(temp): os.unlink(temp)
                report['redactions'].append(dict(finding, original_sha256=original, exported_sha256=sha(path)))
    if not report['scanned_files']: raise ScanError('scan target contains no regular files')
    report['clean'] = not report['findings']
    return report
