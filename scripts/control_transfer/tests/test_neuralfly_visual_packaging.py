"""Opt-in observation identity and public runtime boundary; no simulator dependency."""

import ast
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.control_transfer.specs import spec
from scripts.control_transfer.gen_tasks import render
from scripts.control_transfer.check_contract import check

NAME = "neural-fly-general-skydio-v1"


class VisualPackagingTests(unittest.TestCase):
    def setUp(self):
        self.previous_umask = os.umask(0o022)

    def tearDown(self):
        os.umask(self.previous_umask)

    def test_explicit_observation_revision_preserves_physical_banks(self):
        for index in range(2):
            before = spec("neural-fly-general-v1", index)
            after = spec(NAME, index)
            self.assertEqual(after["bank"], before["bank"])
            self.assertEqual(after["task_revision"], before["task_revision"])
            self.assertEqual(after["public"]["score"], before["public"]["score"])
            self.assertNotIn("visual_profile", before)
            self.assertEqual(after["observation_revision"], "neuralfly-skydio/1")
            self.assertEqual(after["public"]["visual_profile"], "skydio-x2/1")

    def test_generated_profiles_use_one_image_and_frozen_legacy_renderer(self):
        from scripts.control_transfer.gen_tasks import IMAGE
        with tempfile.TemporaryDirectory() as directory:
            for name in ["neural-fly", "neural-fly-general-v1", NAME]:
                task = Path(directory) / f"control-transfer-{name}-i00-standard"
                render(task, name, 0)
                self.assertEqual(check(task), [])
                main = (task / "environment/Dockerfile").read_text()
                sim = (task / "environment/docker-compose.yaml").read_text()
                public = task / "environment/public"
                helper = public / "neuralfly_visual.py"
                if name == NAME:
                    self.assertIn(IMAGE + "-nominal", main)   # one image for every family (0.2.0)
                    self.assertIn("NEURALFLY_VISUAL_STYLE=skydio-x2/1", main)
                    self.assertIn("NEURALFLY_VISUAL_STYLE: skydio-x2/1", sim)
                    self.assertEqual(tomllib.loads((task / "task.toml").read_text())["metadata"]["oracle"], "full")   # gen_tasks.EVIDENCE
                    self.assertTrue(helper.exists())
                    compose = task / "environment/docker-compose.yaml"
                    compose.write_text(
                        sim.replace("NEURALFLY_VISUAL_STYLE: skydio-x2/1", "NEURALFLY_VISUAL_STYLE: primitive")
                    )
                    self.assertTrue(check(task))
                else:
                    self.assertIn(IMAGE + "-nominal", main)
                    self.assertNotIn("NEURALFLY_VISUAL_STYLE", main + sim)
                    self.assertFalse(helper.exists())
                    self.assertEqual(
                        (public / "neuralfly_video.py").read_bytes(),
                        (ROOT / "scripts/control_transfer/neuralfly_video_primitive.py").read_bytes(),
                    )

    def test_public_export_has_no_operator_downloader_or_trusted_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory) / f"control-transfer-{NAME}-i01-standard"
            render(task, NAME, 1)
            public = task / "environment/public"
            module = public / "neuralfly_visual.py"
            text = module.read_text()
            self.assertNotIn("githubusercontent", text)
            self.assertNotIn("urlopen", text)
            self.assertNotIn("prepare", [n.name for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)])
            code = "import sys; sys.path.insert(0,sys.argv[1]); import neuralfly_visual as v; assert not hasattr(v,'prepare'); assert v.PROFILE=='skydio-x2/1'; assert not any('trusted' in k for k in sys.modules)"
            subprocess.run([sys.executable, "-I", "-B", "-S", "-c", code, str(public)], check=True, capture_output=True)
            self.assertFalse(any(p.name.endswith("spec.py") or "trusted" in p.parts for p in public.rglob("*")))

    def test_asset_staging_fails_before_writing_on_corrupt_source(self):
        module_spec = importlib.util.spec_from_file_location(
            "stage_skydio", ROOT / "images/control-transfer/stage_skydio.py"
        )
        stage = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(stage)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            (source / "assets").mkdir(parents=True)
            (source / "assets/X2_lowpoly.obj").write_text("corrupt mesh")
            output = Path(directory) / "output"
            with self.assertRaises(ValueError):
                stage.stage(source, output)
            self.assertFalse(output.exists())
        checksum_rows = (ROOT / "images/control-transfer/skydio-assets.sha256").read_text().splitlines()
        self.assertEqual({row.split(None, 1)[1]: row.split(None, 1)[0] for row in checksum_rows}, stage.FILES)


if __name__ == "__main__":
    unittest.main()
