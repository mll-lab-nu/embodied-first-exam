#!/usr/bin/env python3
"""Qualify automatic rigid/FEM/PBD grasp using an isolated source snapshot.

Mechanical fixtures explicitly disable RGB. Robot cases use the shared
segmented policy runner, standard home and Nyx (unless --no-rgb is explicit).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import resource
import math
from importlib.metadata import distribution, version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--no-rgb', action='store_true', help='Explicit physics-only soft robot probe')
    parser.add_argument('--robot', choices=('panda_robotiq','aloha'), default='panda_robotiq',
                        help='Robot for the independent soft material policy cases')
    parser.add_argument('--fem-rope-profile', choices=('baseline', 'v13_material_mesh'), default=None,
                        help='FEM robot fixture material/mesh; v13 omits historical task-local damping')
    parser.add_argument('--lift-height-m', type=float, default=.055,
                        help='Soft robot policy lift; use .10 to leave clearance below a sagging rope')
    parser.add_argument('--case', choices=('mechanism', 'robot-cube', 'fem-mechanism', 'pbd-mechanism', 'fem-robot', 'pbd-robot'), default='mechanism')
    args = parser.parse_args()
    if args.fem_rope_profile is not None and args.case != 'fem-robot':
        parser.error('--fem-rope-profile is only supported by fem-robot')
    if args.fem_rope_profile is None and args.case == 'fem-robot':
        args.fem_rope_profile = 'v13_material_mesh'
    if not math.isfinite(args.lift_height_m) or args.lift_height_m <= .02:
        parser.error('--lift-height-m must be finite and greater than .02')
    if args.lift_height_m != .055 and args.case not in ('fem-robot', 'pbd-robot'):
        parser.error('--lift-height-m is only supported by soft robot cases')
    if args.case == 'robot-cube' and args.device != 'cuda':
        parser.error('robot-cube requires CUDA/Nyx')
    if args.case == 'robot-cube' and args.no_rgb:
        parser.error('robot-cube always qualifies Nyx; use mechanism for physics only')
    if (args.case.startswith('fem') or (args.case.endswith('-robot') and not args.no_rgb)) and args.device != 'cuda':
        parser.error('FEM IPC and Nyx robot cases require CUDA')
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output/'source'
    snapshot.mkdir()
    for folder in ('topogym', 'tests', 'configs'):
        shutil.copytree(root/folder, snapshot/folder, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(root/'pyproject.toml', snapshot/'pyproject.toml')
    # Immutable external fixtures remain outside source; their role is explicit.
    (snapshot/'assets').symlink_to(root/'assets', target_is_directory=True)
    hashes = {str(p.relative_to(snapshot)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in snapshot.rglob('*.py')}
    (output/'source_hashes.json').write_text(json.dumps(hashes, indent=2))
    test_file = {'robot-cube': 'test_grasp_robot_runtime.py', 'mechanism': 'test_grasp_assist.py',
                 'pbd-mechanism': 'test_soft_grasp_mechanism.py', 'pbd-robot': 'test_grasp_pbd.py',
                 'fem-mechanism': 'test_soft_grasp_mechanism.py', 'fem-robot': 'test_grasp_ipc.py'}[args.case]
    # Preserve native solver diagnostics even if libuipc aborts the process.
    command = [sys.executable, '-m', 'pytest', '-q', '-s', '-m', 'genesis',
               'tests/integration/'+test_file, '-x', '--junitxml='+str(output/'pytest.xml')]
    identity = dict(device=args.device, command=command, source=str(snapshot),
                    fem_rope_profile=args.fem_rope_profile,
                    lift_height_m=args.lift_height_m,
                    case=args.case, robot=args.robot, rgb=args.case == 'robot-cube' or (args.case.endswith('-robot') and not args.no_rgb),
                    scope='grasp qualification; no puzzle solve claim')
    identity['driver_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    shutil.copy2(__file__, output/'test_driver.py')
    engine = Path(distribution('genesis-world').locate_file('genesis'))
    files = ('engine/solvers/rigid/constraint/solver.py', 'utils/array_class.py',
             'engine/solvers/rigid/collider/collider.py', 'engine/entities/pbd_entity.py',
             'engine/solvers/pbd_solver.py', 'engine/couplers/legacy_coupler.py',
             'engine/solvers/rigid/rigid_solver.py', 'engine/solvers/rigid/abd/forward_kinematics.py',
             'engine/couplers/ipc_coupler/coupler.py')
    identity['engine'] = dict(version=version('genesis-world'), source_sha256={
        name: hashlib.sha256((engine/name).read_bytes()).hexdigest() for name in files})
    identity['engine']['pyuipc_version'] = version('pyuipc')
    if args.case.startswith('fem'):
        identity['engine']['tetgen_version'] = version('tetgen')
    (output/'invocation.json').write_text(json.dumps(identity, indent=2))
    env = dict(os.environ, PYTHONPATH=str(snapshot)+os.pathsep+str(snapshot/'tests'), TOPOGYM_TEST_DEVICE=args.device,
               TOPOGYM_TEST_RGB='1' if args.case.endswith('-robot') and not args.no_rgb else '0',
               TOPOGYM_TEST_MATERIAL='fem' if args.case.startswith('fem') else 'pbd',
               TOPOGYM_TEST_ROBOT=args.robot,
               TOPOGYM_TEST_FEM_ROPE_PROFILE=args.fem_rope_profile or '',
               TOPOGYM_TEST_LIFT_HEIGHT_M=str(args.lift_height_m),
               TOPOGYM_VISUAL_ASSET_ROOT=str(root/'.external/nyx-assets'),
               OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
               TOPOGYM_TEST_OUTPUT=str(output/'evidence'))
    with (output/'pytest.log').open('w') as log:
        started = time.monotonic()
        result = subprocess.run(command, cwd=snapshot, env=env, stdout=log, stderr=subprocess.STDOUT)
    identity['exit_code'] = result.returncode
    identity['elapsed_s'] = time.monotonic()-started
    identity['peak_child_rss_kib'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    identity['generated_assets_sha256'] = {
        str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((output/'evidence').rglob('*'))
        if p.is_file() and 'assets' in p.parts and p.suffix in {'.npz', '.obj', '.urdf', '.png', '.json'}
    }
    (output/'invocation.json').write_text(json.dumps(identity, indent=2))
    print(f'Grasp qualification exit={result.returncode}; evidence: {output}')
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
