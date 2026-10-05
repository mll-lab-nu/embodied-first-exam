"""Small audited patch against the exact Harbor 0.23.0 wheel, inside image only."""
import hashlib
import importlib.util
from pathlib import Path

path = Path(importlib.util.find_spec('harbor.agents.installed.codex').origin)
expected = 'ee0ca8ec43617f3909d2195afe8f9e7cbd7313a8b3b558b01fde388f65b7c39c'
assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'Harbor Codex source changed; review the delivery patch'
source = path.read_text()
anchor = '            # cleanup - best effort\n'
assert source.count(anchor) == 1
patch = '''            # TopoGym delivery: retain token rotation in the private auth store.
            if auth_json_path and self._get_env("TOPOGYM_PERSIST_AUTH") == "1":
                try:
                    from harbor_agents.persistent_auth import persist_auth
                    await persist_auth(environment, remote_auth_path, auth_json_path)
                except Exception as refresh_error:
                    status_path = self._get_env("TOPOGYM_AUTH_STATUS")
                    if status_path:
                        from pathlib import Path as StatusPath
                        import json as status_json
                        StatusPath(status_path).write_text(status_json.dumps({"status": "failed", "error_type": type(refresh_error).__name__}))
                    self.logger.warning("Could not persist refreshed login; run auth login if the next trial cannot authenticate")
'''
path.write_text(source.replace(anchor, patch + anchor))
print('Applied TopoGym private-auth persistence patch to pinned Harbor Codex')

# Harbor creates an egress helper in addition to task-declared services. Mark it
# with the same owner so SIGKILL recovery can remove its network namespace too.
path = Path(importlib.util.find_spec('harbor.environments.docker.docker').origin)
expected = '8757d3fbc19e58c7ccd14c9b613a0d00dccd1b514375fa0e546ff41ca963a15e'
assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'Harbor Docker source changed; review ownership patch'
source = path.read_text()
anchor = '        self._egress_control_services_compose_temp_dir = tempfile.TemporaryDirectory()\n'
assert source.count(anchor) == 1
patch = '''        # TopoGym delivery: tag the internal helper as owned work.
        ownership = json.loads(os.environ.get("TOPOGYM_RESOURCE_LABELS", "{}"))
        if ownership:
            services[self._EGRESS_CONTROL_SERVICE_NAME] = {"labels": ownership}

'''
path.write_text(source.replace(anchor, patch + anchor))
print('Applied TopoGym ownership labels to pinned Harbor egress helper')
