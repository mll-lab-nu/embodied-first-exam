"""Persist Codex token refresh to the private controller auth store, never jobs.

Called by the version-checked Harbor delivery patch immediately before Codex
deletes its temporary secrets. The controller holds the user's auth lock.
"""
import json
from pathlib import Path
import tempfile


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
        candidate.chmod(0o600)
        candidate.replace(local)
