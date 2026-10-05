"""Persist Codex token refresh to the private controller auth store, never jobs.

Called by the version-checked Harbor delivery patch immediately before Codex
deletes its temporary secrets. The controller holds the user's auth lock.
"""
import json
from pathlib import Path
import tempfile
import os


async def persist_auth(environment, remote, local):
    local = Path(local)
    original = json.loads(local.read_text())
    account = (original.get('tokens') or {}).get('account_id')
    with tempfile.TemporaryDirectory(prefix='.refresh-', dir=local.parent) as directory:
        candidate = Path(directory) / 'auth.json'
        await environment.download_file(remote, candidate)
        data = json.loads(candidate.read_text())
        tokens = data.get('tokens') or {}
        if not tokens.get('access_token') or tokens.get('account_id') != account:
            raise ValueError('refreshed login identity does not match imported account')
        history = os.environ.get('TOPOGYM_AUTH_HISTORY')
        if history:
            # Caller holds the shared account lock. Keep every rotated value private
            # until all historical mirror versions have been scanned.
            path = Path(history)
            saved = json.loads(path.read_text()) if path.exists() else {'tokens': {}}
            for value in (original.get('tokens') or {}) | tokens:
                for record in (original.get('tokens') or {}, tokens):
                    token = record.get(value)
                    if token and value != 'account_id' and token not in saved['tokens'].values():
                        saved['tokens'][str(len(saved['tokens']))] = token
            fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.auth-history-')
            with os.fdopen(fd, 'w') as stream: json.dump(saved, stream)
            os.replace(temporary, path)
        candidate.chmod(0o600)
        candidate.replace(local)
