"""Credential setup contracts. Synthetic secrets only; no provider/model calls."""
import contextlib
import io
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import configure_agent_batch as setup
import agent_batch_runtime as runtime

API = 'synthetic-model-key-for-tests'
HF = 'hf_syntheticUploadTokenForTestsOnly'


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = self.root / 'private/rcb.env'
        self.hf = self.root / 'private/hf.token'

    def tearDown(self):
        self.temp.cleanup()

    def create(self):
        with patch.object(setup, 'hidden_input', side_effect=[API, HF]):
            setup.configure(self.env, self.hf)

    def test_first_setup_is_private_and_consumed_by_actual_runner(self):
        self.create()
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.hf.stat().st_mode), 0o600)
        env, auth = runtime.credentials({'ENV_FILE': str(self.env), 'CODEX_FORCE_AUTH_JSON': '0', 'CODEX_AUTH_JSON_PATH': ''})
        self.assertEqual(env['OPENAI_API_KEY'], API)
        self.assertEqual(env['OPENAI_BASE_URL'], setup.DEFAULT_BASE_URL)
        self.assertIsNone(auth)
        self.assertNotIn('HF_TOKEN', env)
        self.assertNotIn(HF, self.env.read_text())

    def test_reuse_needs_no_prompt_and_preserves_bytes(self):
        self.create()
        before = (self.env.read_bytes(), self.hf.read_bytes())
        self.env.chmod(0o644)
        with patch.object(setup, 'hidden_input') as prompt:
            setup.configure(self.env, self.hf)
            prompt.assert_not_called()
        self.assertEqual(before, (self.env.read_bytes(), self.hf.read_bytes()))
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)

    def test_missing_file_noninteractive_fails_without_creating_empty_env(self):
        with patch.object(sys.stdin, 'isatty', return_value=False):
            with self.assertRaisesRegex(setup.SetupError, 'foreground'):
                setup.configure(self.env, self.hf)
        self.assertFalse(self.env.exists())
        self.assertFalse(self.hf.exists())

    def test_cancelled_second_prompt_does_not_publish_first_credential(self):
        with patch.object(setup, 'hidden_input', side_effect=[API, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                setup.configure(self.env, self.hf)
        self.assertFalse(self.env.exists())

    def test_rejects_repository_path_symlink_and_same_file(self):
        with patch.object(setup, 'ROOT', self.root):
            with self.assertRaisesRegex(setup.SetupError, 'outside'):
                setup.configure(self.env, self.hf)
        target = self.root / 'target'; target.write_text('preserve')
        self.env.parent.mkdir(); self.env.symlink_to(target)
        with self.assertRaisesRegex(setup.SetupError, 'symlinks'):
            setup.configure(self.env, self.hf)
        self.assertEqual(target.read_text(), 'preserve')
        with self.assertRaisesRegex(setup.SetupError, 'separate'):
            setup.configure(self.hf, self.hf)

    def test_create_never_overwrites_existing_credentials(self):
        self.create()
        with self.assertRaisesRegex(setup.SetupError, 'preserved'):
            setup.create_private_file(self.env, 'replacement')
        self.assertIn(API, self.env.read_text())
        self.assertFalse(list(self.env.parent.glob('.helper-auth-*')))

    def test_endpoint_conflict_and_subscription_file_preserved(self):
        self.create()
        before = self.env.read_bytes()
        with self.assertRaisesRegex(setup.SetupError, 'endpoint differs'):
            setup.configure(self.env, self.hf, api_base_url='https://example.test/v1')
        self.assertEqual(self.env.read_bytes(), before)
        self.env.write_text('CODEX_FORCE_AUTH_JSON=1\n')
        with self.assertRaisesRegex(setup.SetupError, 'keep HF/subscription'):
            setup.configure(self.env, self.hf)
        self.assertEqual(self.env.read_text(), 'CODEX_FORCE_AUTH_JSON=1\n')

    def test_no_credentials_in_success_or_failure_output(self):
        args = ['--env-file', str(self.env), '--hf-token-file', str(self.hf)]
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output), \
                patch.object(setup, 'hidden_input', side_effect=[API, HF]):
            self.assertEqual(setup.main(args), 0)
        self.env.write_text('OPENAI_API_KEY=' + API + '\nOPENAI_BASE_URL=https://user:' + API + '@example.test/v1\n')
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(setup.main(args + ['--check']), 2)
        self.assertNotIn(API, output.getvalue())
        self.assertNotIn(HF, output.getvalue())

    def test_model_key_validation_rejects_hf_and_dotenv_injection(self):
        for value in (HF, API + '\nHF_TOKEN=injected', API + '"', ''):
            with self.subTest(value=value), self.assertRaises(setup.SetupError):
                setup.api_key(value)


if __name__ == '__main__':
    unittest.main()
