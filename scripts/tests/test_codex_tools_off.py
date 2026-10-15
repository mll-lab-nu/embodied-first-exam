"""Tests for scripts/codex_tools_off.py: the Codex config a run starts from has no provider-side tool on.

    python3 scripts/tests/test_codex_tools_off.py     # stdlib only (the parse-back needs Python 3.11+)
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import codex_tools_off as m  # noqa: E402

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

PROVIDER = 'model_provider = "azure"\n[model_providers.azure]\nbase_url = "https://x.openai.azure.com/openai/v1"\n'


def get(doc, key):
    for part in key.split("."):
        doc = doc[part]
    return doc


@unittest.skipIf(tomllib is None, "needs tomllib")
class ToolsOff(unittest.TestCase):
    def off(self, text):
        doc = tomllib.loads(m.tools_off(text))
        for key in m.OFF:
            self.assertIs(get(doc, key), False, key)
        return doc

    def test_no_config(self):
        self.assertEqual(set(self.off("")), {"features", "apps"})

    def test_provider_config_is_kept(self):
        doc = self.off(PROVIDER)
        self.assertEqual(doc["model_providers"]["azure"]["base_url"], "https://x.openai.azure.com/openai/v1")
        self.assertNotIn("features", doc["model_providers"]["azure"])  # the keys precede the first table

    def test_a_config_that_already_has_the_keys(self):
        # what a scheduler with its own block passes (dotted keys first, then the provider): same result, no duplicate
        head = "".join(f"{k} = false\n" for k in m.OFF)
        self.assertEqual(self.off(head + PROVIDER), self.off(PROVIDER))
        self.off("features.apps = false   # mine\n" + PROVIDER)

    def test_own_tables(self):
        doc = self.off('[features]\nfoo = true\napps = false\n[apps.github]\nenabled = true\n[apps._default]\nx = 1\n' + PROVIDER)
        self.assertIs(doc["features"]["foo"], True)
        self.assertIs(doc["apps"]["github"]["enabled"], True)
        self.assertEqual(doc["apps"]["_default"]["x"], 1)
        self.off("[apps]\nfoo = 1\n")
        self.off('features.foo = true\n["features".sub]\nx = 1\n')

    def test_a_key_turned_on_is_refused(self):
        for text in ("features.apps = true\n", "[features]\nplugins = true\n", "[features]\nimage_generation = 'false'\n",
                     "[apps._default]\nenabled = true\n", "[apps]\n_default.enabled = true\n", "features = { apps = false }\n",
                     "apps = { _default = { enabled = false } }\n", "[apps]\n_default = { enabled = false }\n"):
            with self.assertRaises(ValueError, msg=text):
                m.tools_off(text)

    def test_same_name_elsewhere_is_not_ours(self):
        doc = self.off("[model_providers.azure]\napps = true\n[[profiles]]\nfeatures.apps = true\n")
        self.assertIs(doc["model_providers"]["azure"]["apps"], True)

    def test_command_line(self):
        script = str(HERE / "codex_tools_off.py")
        with tempfile.TemporaryDirectory() as d:
            good, bad = pathlib.Path(d) / "good.toml", pathlib.Path(d) / "bad.toml"
            good.write_text(PROVIDER)
            bad.write_text("[features]\napps = true\n")
            r = subprocess.run([sys.executable, script, str(good)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.off(r.stdout)
            r = subprocess.run([sys.executable, script], capture_output=True, text=True)
            self.off(r.stdout)
            r = subprocess.run([sys.executable, script, str(bad)], capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout), (2, ""))
            self.assertIn("features.apps", r.stderr)
            r = subprocess.run([sys.executable, script, str(pathlib.Path(d) / "missing.toml")], capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout), (2, ""))


if __name__ == "__main__":
    unittest.main()
