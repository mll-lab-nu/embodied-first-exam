"""Harbor Codex with pinned offline installation and ChatGPT-only authentication."""
import json
import os
from pathlib import Path
from harbor.agents.installed.codex import Codex


class SubscriptionCodex(Codex):
    async def _with_owned_upload(self, operation, environment, **kwargs):
        # Compose cp preserves host UID on this Docker version. With ALL
        # capabilities dropped, container root cannot chmod/read another UID's
        # private files. Harbor's tar uploader normalizes ownership to UID 0;
        # use it instead of granting DAC_OVERRIDE/CHOWN capabilities.
        original = environment.upload_file
        environment.upload_file = environment._platform._upload_file_with_tar
        try:
            return await operation(environment=environment, **kwargs)
        finally:
            environment.upload_file = original

    async def setup(self, environment):
        return await self._with_owned_upload(super().setup, environment)

    async def run(self, instruction, environment, context):
        return await self._with_owned_upload(super().run, environment, instruction=instruction, context=context)

    async def install(self, environment):
        binary = Path(os.environ['VLABENCH_CODEX_BINARY']).resolve()
        await environment.upload_file(binary, '/usr/local/bin/codex')
        # Standalone Codex 0.158 splits tool execution into a companion binary.
        # Copy the pinned companions, not only the model/CLI executable.
        for source, name in ((binary.with_name('codex-code-mode-host'), 'codex-code-mode-host'),
                             (binary.parent.parent/'codex-path/rg', 'rg')):
            await environment.upload_file(source, '/usr/local/bin/'+name)
        result = await self.exec_as_root(environment, command='chmod 755 /usr/local/bin/codex && codex --version')
        if result.return_code or self.version() not in result.stdout:
            raise RuntimeError('Pinned Codex binary failed version validation')

    def _resolve_auth_json_path(self):
        path = super()._resolve_auth_json_path()
        if path is None:
            raise RuntimeError('ChatGPT login required; API-key fallback is disabled')
        data = json.loads(path.read_text())
        if data.get('auth_mode') != 'chatgpt' or not (data.get('tokens') or {}).get('access_token') or data.get('OPENAI_API_KEY'):
            raise RuntimeError('Expected ChatGPT subscription auth, not API-key auth')
        return path

    # Harbor BaseInstalledAgent._exec already enables pipefail and raises on CLI
    # errors, so an auth/quota error is not treated as normal agent completion.
