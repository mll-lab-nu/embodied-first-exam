"""Explicitly authorized Muse Code compatibility agent; distinct from native D11 runs."""
import json
from pathlib import Path
import shlex

from harbor.agents.installed.muse_code import MuseCode
from harbor.agents.installed.base import with_prompt_template
from harbor_agents.muse_transport.launch import VERSION, BINARY_SHA256, ensure_binary


class MuseOpenRouter(MuseCode):
    @staticmethod
    def name(): return 'muse-openrouter'

    def __init__(self, *args, reasoning_effort=None, **kwargs):
        self.effort = reasoning_effort or 'default'
        if self.effort not in ('default','none','minimal','low','medium','high','xhigh','max','ultra'):
            raise ValueError('invalid Muse reasoning effort')
        super().__init__(*args, **kwargs)
        if self._version and self._version != VERSION: raise ValueError('Muse version differs from fixed adapter')
        if not self.model_name or not self.model_name.startswith('openrouter/meta/muse'):
            raise ValueError('muse-openrouter requires openrouter/meta/muse...')

    async def install(self, environment):
        root = Path(__file__).resolve().parent
        import fcntl
        cache=root.parent/'.tools/agent-batch/muse'; cache.mkdir(parents=True,exist_ok=True)
        with (cache/'install.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            binary=ensure_binary(cache/('muse-'+VERSION))
        await self.exec_as_agent(environment, command='mkdir -p /tmp/topogym-muse-adapter/harbor_agents/muse_transport')
        await self._upload_agent_owned_file(environment,binary,'/tmp/topogym-muse-adapter/muse')
        await self.exec_as_agent(environment, command='chmod 755 /tmp/topogym-muse-adapter/muse')
        for source in [root/'__init__.py', *(p for p in (root/'muse_transport').iterdir() if p.is_file() and p.suffix!='.pyc')]:
            relative = source.relative_to(root)
            await self._upload_agent_owned_file(environment, source, '/tmp/topogym-muse-adapter/harbor_agents/'+relative.as_posix())

    def get_version_command(self): return '/tmp/topogym-muse-adapter/muse --version'

    @with_prompt_template
    async def run(self, instruction, environment, context):
        key = self._get_env('OPENROUTER_API_KEY') or self._get_env('OPENROUTER_API_KEY_FOR_SMOKE')
        if not key: raise ValueError('OpenRouter credentials missing for Muse Code')
        await self.exec_as_agent(environment, command="printf '%s' "+shlex.quote(instruction)+' > /tmp/muse-code-prompt.txt')
        command = ('PYTHONPATH=/tmp/topogym-muse-adapter python3 -m harbor_agents.muse_transport.launch '
                   '--binary /tmp/topogym-muse-adapter/muse --logs /logs/agent --prompt-file /tmp/muse-code-prompt.txt '
                   '--model '+shlex.quote(self.model_name.removeprefix('openrouter/'))+' --effort '+shlex.quote(self.effort))
        result = await self.exec_as_agent(environment, command=command, env={'OPENROUTER_API_KEY':key})
        if result.return_code != 0: raise RuntimeError('Muse/OpenRouter execution failed; see sanitized agent usage and native logs')

    def populate_context_post_run(self, context):
        context.metadata = dict(agent=self.name(), provider='openrouter', muse_version=VERSION,
                                muse_binary_sha256=BINARY_SHA256, protocol='muse-openrouter-adapted-v1', native_d11=False)
        path = self.logs_dir/'openrouter-usage.json'
        if not path.exists(): return
        report = json.loads(path.read_text())
        if not report.get('complete') or report.get('model') != self.model_name.removeprefix('openrouter/'): return
        totals = report['totals']
        context.n_input_tokens = totals['input_tokens']; context.n_output_tokens = totals['output_tokens']
        context.n_cache_tokens = totals['cached_tokens']
