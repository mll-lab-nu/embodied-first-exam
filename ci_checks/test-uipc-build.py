#!/usr/bin/env python3
"""CPU contracts for the original-material CUDA build; not GPU/physics evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('wheel_audit', ROOT/'images/topogym/verify_uipc_wheel.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
sys.path.insert(0, str(ROOT/'scripts'))
import difficulty_release as release
import cuda_profiles


class BuildContracts(unittest.TestCase):
    def test_material_guard_and_exact_build_only_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            cmake = source/'src/backends/cuda/CMakeLists.txt'
            cmake.parent.mkdir(parents=True)
            cmake.write_text('    CUDA_ARCHITECTURES ${UIPC_CUDA_ARCHITECTURES}\n')
            material = source/'material.cpp'
            material.write_text('original constitutive law\n')
            cfg = dict(material_sha256={'material.cpp': audit.sha(material)}, cmake_before_sha256=audit.sha(cmake))
            audit.prepare(source, cfg)
            self.assertIn('"${UIPC_CUDA_ARCHITECTURES}"', cmake.read_text())
            self.assertEqual(audit.sha(material), cfg['material_sha256']['material.cpp'])
            material.write_text('different constitutive law\n')
            with self.assertRaisesRegex(ValueError, 'material implementation changed'):
                audit.materials(source, cfg)

    def test_original_wheel_removed_but_dependency_hashes_preserved(self):
        before = 'a==1 \\\n    --hash=sha256:aaa\npyuipc==0.0.25 \\\n    --hash=sha256:bbb \\\n    --hash=sha256:ccc\nb==2 \\\n    --hash=sha256:ddd\n'
        after = audit.without_pyuipc(before)
        self.assertEqual(after, 'a==1 \\\n    --hash=sha256:aaa\nb==2 \\\n    --hash=sha256:ddd\n')
        for invalid in (before.replace('0.0.25', '0.0.28'), before+before, 'a==1\n'):
            with self.assertRaises(ValueError): audit.without_pyuipc(invalid)

    def test_wheel_requires_both_native_architectures_and_ptx(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with zipfile.ZipFile(folder/'test.whl', 'w') as wheel:
                wheel.writestr('pyuipc.dist-info/METADATA', 'Name: pyuipc\nVersion: 0.0.25+topogym.cuda128\n')
                wheel.writestr('uipc/_native/libuipc_backend_cuda.so', b'test backend')
            cfg = dict(material_sha256={}, source_commit='original', version='0.0.25+topogym.cuda128',
                       required_sass=['sm_89', 'sm_120'])
            def output(cmd, **kwargs):
                if 'rev-parse' in cmd: return 'original\n'
                if 'ls-files' in cmd: return 'src/backends/cuda/CMakeLists.txt\n'
                if 'diff' in cmd: return 'src/backends/cuda/CMakeLists.txt\n'
                if '--list-elf' in cmd: return 'sm_89\n'
                if '--list-ptx' in cmd: return 'sm_120\n'
                raise AssertionError(cmd)
            with patch.object(audit.subprocess, 'check_output', side_effect=output):
                with self.assertRaisesRegex(ValueError, 'lacks required native'):
                    audit.audit(folder, cfg, folder)
            self.assertFalse((folder/'uipc-build.json').exists())
            def missing_ptx(cmd, **kwargs):
                if '--list-elf' in cmd: return 'sm_89\nsm_120\n'
                if '--list-ptx' in cmd:
                    self.assertIn('--all-fatbin', cmd)
                    return ''
                return output(cmd, **kwargs)
            with patch.object(audit.subprocess, 'check_output', side_effect=missing_ptx):
                with self.assertRaisesRegex(ValueError, 'lacks compute-120 PTX'):
                    audit.audit(folder, cfg, folder)

    def test_corrupt_wheel_rejected_before_any_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder/'test.whl').write_bytes(b'tampered')
            (folder/'uipc-build.json').write_text(json.dumps(dict(wheel='test.whl', wheel_sha256='expected')))
            with patch.object(audit.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                    audit.install(folder, folder/'runtime.lock')
                run.assert_not_called()

    def test_build_inputs_invalidate_runtime_identity(self):
        paths = ['requirements/uipc-build.lock', 'images/topogym/uipc-build.json',
                 'images/topogym/build_uipc.sh', 'images/topogym/verify_uipc_wheel.py',
                 'images/topogym/check_gpu_stack.py']
        baseline = {p: 'a' for p in paths}
        identity = release.digest(release.runtime_files(baseline))
        for path in paths:
            self.assertNotEqual(identity, release.digest(release.runtime_files(dict(baseline, **{path: 'b'}))))

    def test_profiles_keep_materials_but_separate_builds(self):
        a = cuda_profiles.build_args(ROOT, 'cu128')
        b = cuda_profiles.build_args(ROOT, 'cu130')
        self.assertNotEqual(release.digest(a), release.digest(b))
        configs = [json.loads((ROOT/'images/topogym'/x['UIPC_CONFIG']).read_text()) for x in (a, b)]
        for key in ('source_commit', 'material_sha256', 'architectures', 'vcpkg_commit'):
            self.assertEqual(configs[0][key], configs[1][key])
        self.assertNotEqual(configs[0]['version'], configs[1]['version'])
        self.assertEqual(configs[0]['wheel_platform'], 'manylinux_2_34_x86_64')
        self.assertEqual(configs[1]['wheel_platform'], 'manylinux_2_35_x86_64')
        for x in (a, b):
            lock = (ROOT/'requirements'/x['RUNTIME_LOCK']).read_text()
            self.assertIn('torch==2.11.0+' + x['CUDA_FLAVOR'], lock)
            self.assertIn('torchvision==0.26.0+' + x['CUDA_FLAVOR'], lock)
        with self.assertRaises(ValueError): cuda_profiles.build_args(ROOT, 'auto')

    def test_cu130_driver_guard(self):
        cuda_profiles.check_driver('cu128', '570.153.02')
        cuda_profiles.check_driver('cu130', '580.65.06')
        cuda_profiles.check_driver('cu130', '590.48.01')
        with self.assertRaisesRegex(ValueError, 'R580'):
            cuda_profiles.check_driver('cu130', '570.153.02')

    def test_resume_cannot_switch_cuda_profile(self):
        import difficulty_eval as evaluation
        with tempfile.TemporaryDirectory() as tmp:
            args = evaluation.parse_args(['--run-id', 'profile-test', '--phase', 'plan', '--work-dir', tmp])
            fake = dict(instance_count=1, trial_count=2, settings=dict(agent_wall_clock_s=21600))
            with patch.object(evaluation.sampling, 'prepare_manifest', return_value=fake):
                self.assertEqual(evaluation.DifficultyEvaluation(args).execute(), 0)
                args.cuda_flavor = 'cu130'
                with self.assertRaisesRegex(evaluation.EvaluationError, 'CUDA profile changed'):
                    evaluation.DifficultyEvaluation(args).execute()


if __name__ == '__main__':
    unittest.main()
