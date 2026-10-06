"""OpenRouter native runner contracts. Synthetic secrets; no paid API calls."""
import asyncio
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT)]
os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
import agent_batch_provider as provider
import agent_batch_contract as c
import agent_batch_runtime as runtime
import agent_batch_delivery as delivery
import configure_agent_batch as setup
import check_agent_batch_auth as auth_check
import patch_agent_batch_providers as installer
import secret_scan

spec = importlib.util.spec_from_file_location('native_fixture', ROOT / 'ci_checks/test-native-agent-batch.py')
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
KEY = 'synthetic-openrouter-key-for-ci-only'
MODEL = 'openrouter/meta/muse-spark-1.3-contributor'


class OpenRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.jobs, self.original = fixture.fixture(self.root)
        self.original['helper_selects_model'] = True
        self.original.pop('plan_sha256'); self.original['plan_sha256'] = c.digest(self.original)
        self.plan = c.select_agent(self.original, model=MODEL, effort='default')

    def tearDown(self):
        self.temp.cleanup()

    def test_key_alias_configure_and_scan_without_subscription_fallback(self):
        envfile = self.root / 'private/router.env'; hf = self.root / 'private/hf.token'
        with patch.dict(os.environ, OPENROUTER_API_KEY_FOR_SMOKE=KEY), \
                patch.object(setup, 'hidden_input', return_value='hf_syntheticUploadCredentialForCI'):
            setup.configure(envfile, hf, provider='openrouter', api_key_env='OPENROUTER_API_KEY_FOR_SMOKE')
        env, auth = runtime.credentials({'ENV_FILE': str(envfile), 'CODEX_FORCE_AUTH_JSON': '0'})
        self.assertIsNone(auth)
        self.assertEqual(env['OPENAI_API_KEY'], KEY)
        self.assertEqual(env['OPENAI_BASE_URL'], provider.OPENROUTER_URL)
        self.assertEqual(envfile.stat().st_mode & 0o777, 0o600)
        with patch.object(setup, 'hidden_input') as prompt:
            setup.configure(envfile, hf, provider='openrouter', check_only=True)
            prompt.assert_not_called()
        log = self.root / 'log'; log.write_text(KEY)
        secrets = secret_scan.load_secrets(env_files=[envfile])
        secret_scan.scan_tree(log, secrets, redact=True)
        self.assertNotIn(KEY, log.read_text())
        with patch.dict(os.environ, OPENROUTER_API_KEY_FOR_SMOKE=KEY):
            self.assertIn('OPENROUTER_API_KEY_FOR_SMOKE', secret_scan.load_secrets(process_env=True))

    def test_bare_slug_and_explicit_prefix_agree(self):
        for alias in provider.OPENROUTER_KEYS:
            env, auth = runtime.credentials({alias: KEY, 'MODEL': 'meta/muse-spark-1.3-contributor'})
            self.assertEqual(provider.canonical_model(env['MODEL'], env['PROVIDER']), MODEL)
            self.assertIsNone(auth)
        self.assertEqual(provider.canonical_model(MODEL, 'openrouter'), MODEL)
        self.assertEqual(provider.model_id(MODEL), 'meta/muse-spark-1.3-contributor')
        self.assertEqual(provider.model_id('openrouter/openai/gpt-6-sol'), 'openai/gpt-6-sol')
        self.assertEqual(provider.model_id('openai/gpt-6-sol'), 'gpt-6-sol')

    def test_conflicting_credentials_endpoint_or_subscription_are_rejected(self):
        for extra in ({'OPENAI_API_KEY': 'another-synthetic-key'},
                      {'OPENAI_BASE_URL': 'https://api.openai.com/v1'},
                      {'CODEX_FORCE_AUTH_JSON': '1'},
                      {'CODEX_AUTH_JSON_PATH': '/do-not-read/auth.json'},
                      {'PROVIDER': 'openai'},
                      {'OPENROUTER_API_KEY': 'another-synthetic-key'}):
            with self.subTest(extra=list(extra)), self.assertRaises(ValueError) as error:
                runtime.credentials(dict(OPENROUTER_API_KEY_FOR_SMOKE=KEY, **extra))
            self.assertNotIn(KEY, str(error.exception))

    def test_incomplete_model_id_rejected(self):
        for model in ('openrouter/muse', 'openrouter/meta/', 'openrouter//muse', 'openrouter/../muse'):
            with self.subTest(model=model), self.assertRaises(ValueError):
                c.select_agent(self.original, model=model)

    def test_unchanged_task_budget_and_authorized_choice(self):
        for field in ('tasks', 'repetitions', 'trial_count', 'jobs', 'upload'):
            self.assertEqual(self.plan[field], self.original[field])
        self.assertNotIn('reasoning_effort', self.plan['agent']['kwargs'])
        self.assertEqual(c.match_assignment(self.original, self.plan), self.plan)
        changed = copy.deepcopy(self.plan); changed['agent']['kwargs']['web_search'] = 'enabled'
        changed.pop('plan_sha256'); changed['plan_sha256'] = c.digest(changed)
        with self.assertRaises(ValueError): c.match_assignment(self.original, changed)
        fixed = copy.deepcopy(self.original); fixed.pop('helper_selects_model'); fixed.pop('plan_sha256'); fixed['plan_sha256'] = c.digest(fixed)
        with self.assertRaisesRegex(ValueError, 'fixed'): c.select_agent(fixed, model=MODEL)

    def test_effort_is_optional_and_not_silently_downgraded(self):
        high = c.select_agent(self.original, model=MODEL, effort='xhigh')
        self.assertEqual(high['agent']['kwargs']['reasoning_effort'], 'xhigh')
        with self.assertRaisesRegex(ValueError, 'reasoning effort'):
            c.select_agent(self.original, model=MODEL, effort='unrecognized')

    def test_canary_uses_real_native_provider_config_and_full_slug(self):
        seen = []
        def command(argv, **kwargs):
            if '--version' in argv:
                return SimpleNamespace(returncode=0, stdout='codex-cli 0.157.0')
            if 'login' in argv:
                self.assertEqual(kwargs['input'], KEY.encode())
            if 'exec' in argv:
                import tomllib
                config = tomllib.loads((Path(kwargs['env']['CODEX_HOME']) / 'config.toml').read_text())
                self.assertEqual(config, provider.codex_config(MODEL))
                self.assertEqual(argv[argv.index('--model') + 1], 'meta/muse-spark-1.3-contributor')
                self.assertNotIn(KEY, str(argv)); self.assertNotIn('model_reasoning_effort', str(argv))
                kwargs['stdout'].write(b'{"type":"turn.completed"}\n')
                seen.append(config)
            return SimpleNamespace(returncode=0)
        with patch.object(auth_check.shutil, 'which', return_value='/test/codex'), \
                patch.object(auth_check.subprocess, 'run', side_effect=command):
            result = auth_check.canary(self.plan, {'OPENROUTER_API_KEY_FOR_SMOKE': KEY})
        self.assertTrue(result['passed']); self.assertEqual(len(seen), 1)

    def test_delivery_accepts_provider_config_and_rejects_tampered_routing(self):
        c.save(self.jobs / 'fixture-plan.json', self.plan)
        metadata = c.read(self.jobs / 'fixture-metadata.json'); metadata['plan_sha256'] = self.plan['plan_sha256']
        c.save(self.jobs / 'fixture-metadata.json', metadata)
        for path in self.jobs.glob('*/*/config.json'):
            config = c.read(path)
            config['agent'].update(model_name=MODEL, kwargs=dict(self.plan['agent']['kwargs'], config=provider.codex_config(MODEL)))
            c.save(path, config)
        self.assertTrue(c.check_batch(self.jobs, self.plan)['delivery_complete'])
        delivery.seal(self.jobs, self.plan, {'test': fixture.SECRET.encode()})
        archive = fixture.pack(self.root, self.jobs, self.plan)
        accepted = delivery.receive(archive, self.original, self.root / 'accepted', require_complete=True)
        self.assertEqual(accepted['report']['actual_agent']['model'], MODEL)
        path = next(self.jobs.glob('*/*/config.json')); config = c.read(path)
        config['agent']['kwargs']['config']['model_providers']['openrouter']['base_url'] = 'https://wrong.test/v1'
        c.save(path, config)
        self.assertEqual(c.check_batch(self.jobs, self.plan)['status_counts']['identity_mismatch'], 1)

    def test_actual_harbor_constructs_nested_model_command_with_patched_source(self):
        # Execute the real installed class with only environment I/O mocked. A
        # temporary in-memory module avoids changing a running host's tools.
        import harbor.agents.installed.codex as native
        namespace = dict(native.__dict__)
        source = installer.patch_source(Path(native.__file__).read_text())
        exec(compile(source, native.__file__, 'exec'), namespace)
        Codex = namespace['Codex']
        agent = Codex(logs_dir=self.root / 'agent', model_name=MODEL, config=provider.codex_config(MODEL), version='0.157.0')
        observed = []
        class Captured(Exception): pass
        async def execute(environment, *, command, env=None, **kwargs):
            if 'codex exec ' in command:
                observed.append((command, env)); raise Captured()
            return SimpleNamespace(return_code=0, stdout='', stderr='')
        from harbor.models.agent.context import AgentContext
        with patch.dict(os.environ, OPENAI_API_KEY=KEY, OPENAI_BASE_URL=provider.OPENROUTER_URL, CODEX_FORCE_AUTH_JSON='0', CODEX_AUTH_JSON_PATH=''), \
                patch.object(agent, 'exec_as_agent', side_effect=execute), \
                patch.object(agent, '_upload_effective_config', new_callable=AsyncMock) as upload:
            with self.assertRaises(Captured):
                asyncio.run(agent.run('fixture instruction', SimpleNamespace(default_user=None), AgentContext()))
            actual = upload.call_args.args[1]
        self.assertEqual(actual['model_providers'], provider.codex_config(MODEL)['model_providers'])
        self.assertIn('--model meta/muse-spark-1.3-contributor ', observed[0][0])
        self.assertEqual(observed[0][1]['OPENAI_API_KEY'], KEY)
        self.assertNotIn(KEY, observed[0][0])

    def test_host_patch_upgrade_is_verified_idempotent_and_rejects_modified_tools(self):
        import harbor.agents.installed.codex as native
        prefix = self.root / 'venv'; prefix.mkdir()
        codex = prefix / 'codex.py'; docker = prefix / 'docker.py'
        codex.write_text(Path(native.__file__).read_text().replace(installer.NEW, installer.OLD))
        docker.write_text('synthetic original Docker module\n')
        paths = {'harbor.agents.installed.codex': codex, 'harbor.environments.docker.docker': docker}
        names = ['images/difficulty-eval/patch_harbor.py', 'requirements/difficulty-eval-controller.lock']
        for name in names + [installer.PATCH]:
            dest = self.root / name; dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT / name).read_bytes())
        receipt = prefix / 'topogym-runner.json'
        c.save(receipt, dict(files={n:c.sha(self.root/n) for n in names}, modules={n:c.sha(p) for n,p in paths.items()}))
        with patch.object(sys, 'prefix', str(prefix)), \
                patch.object(installer.importlib.util, 'find_spec', side_effect=lambda name:SimpleNamespace(origin=str(paths[name]))):
            installer.apply(self.root)
            first = receipt.read_bytes(); content = codex.read_bytes()
            installer.apply(self.root)
            self.assertEqual(first, receipt.read_bytes()); self.assertEqual(content, codex.read_bytes())
            self.assertEqual(c.read(receipt)['files'][installer.PATCH], c.sha(self.root/installer.PATCH))
            codex.write_text(codex.read_text() + '\n# unapproved change\n')
            with self.assertRaisesRegex(ValueError, 'source changed'): installer.apply(self.root)

    def test_old_default_endpoint_is_written_to_canary_profile(self):
        self.assertEqual(provider.codex_config('openai/gpt-6-sol', {'OPENAI_BASE_URL':'https://example.test/v1'}),
                         {'openai_base_url':'https://example.test/v1'})

    def test_helper_release_rejects_unknown_batch_before_bootstrap(self):
        import subprocess
        script = self.root / 'scripts/run_agent_batch.sh'; script.parent.mkdir()
        script.write_bytes((ROOT / 'scripts/run_agent_batch.sh').read_bytes())
        (self.root / 'helper-release.json').write_text('{}')
        result = subprocess.run(['bash', str(script), 'old-batch', 'task'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('no assignment', result.stderr)
        self.assertNotIn('Installing', result.stdout)


if __name__ == '__main__': unittest.main()
