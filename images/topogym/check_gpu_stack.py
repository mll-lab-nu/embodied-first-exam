#!/usr/bin/env python3
"""Small real CUDA operations and IPC build identity; no task qualification."""
import ctypes
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import subprocess


def check_torch():
    flavor = os.environ.get('TOPOGYM_CUDA_FLAVOR', 'cu128')
    assert flavor in ('cu128', 'cu130'), flavor
    driver = subprocess.check_output(['nvidia-smi', '--query-gpu=uuid,driver_version,name',
                                      '--format=csv,noheader'], text=True).strip()
    if flavor == 'cu130':
        assert all(int(row.split(',')[1].strip().split('.')[0]) >= 580 for row in driver.splitlines()), \
            'cu130 requires host NVIDIA driver R580 or newer'
    import torch
    import torchvision
    assert torch.__version__ == '2.11.0+' + flavor, torch.__version__
    assert torchvision.__version__ == '0.26.0+' + flavor, torchvision.__version__
    assert torch.version.cuda == {'cu128': '12.8', 'cu130': '13.0'}[flavor], torch.version.cuda
    assert torch.cuda.is_available(), 'CUDA unavailable'
    device = torch.cuda.get_device_properties(0)
    capability = torch.cuda.get_device_capability(0)
    # Exercise CUDA libraries as well as simple tensor allocation.
    x = torch.arange(64, dtype=torch.float32, device='cuda').reshape(8, 8)
    assert torch.equal((x + 1).cpu(), torch.arange(64).reshape(8, 8) + 1)
    assert torch.allclose((x @ x.T).cpu(), x.cpu() @ x.cpu().T)
    a = torch.eye(8, device='cuda') * 2
    assert torch.allclose(torch.linalg.solve(a, x), x / 2)
    boxes = torch.tensor([[0., 0., 2., 2.], [0., 0., 2., 2.], [5., 5., 6., 6.]], device='cuda')
    scores = torch.tensor([0.9, 0.8, 0.7], device='cuda')
    assert torchvision.ops.nms(boxes, scores, 0.5).tolist() == [0, 2]
    torch.cuda.synchronize()
    return dict(passed=True, scope='cuda_operators', task_physics_executed=False,
                  cuda_flavor=flavor,
                  torch=torch.__version__, torchvision=torchvision.__version__, cuda=torch.version.cuda,
                  gpu=device.name, capability=capability, torch_architectures=torch.cuda.get_arch_list(),
                  driver=driver, operators=['elementwise', 'matmul', 'solve', 'torchvision_nms'])


def check_ipc():
    flavor = os.environ.get('TOPOGYM_CUDA_FLAVOR', 'cu128')
    assert flavor in ('cu128', 'cu130'), flavor
    record = json.loads(Path('/opt/uipc-build.json').read_text())
    assert record['materials_unchanged'] is True
    assert {'sm_89', 'sm_120'} <= set(record['sass'])
    package = metadata.distribution('pyuipc')
    assert package.version == '0.0.25+topogym.det1.cuda' + flavor[2:] == record['version']
    backend = Path(package.locate_file(record['backend_path']))
    with backend.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == record['backend_sha256']
    import uipc
    ctypes.CDLL(str(backend))
    return dict(pyuipc=package.version,
                  ipc_source_commit=record['source_commit'],
                  ipc_backend_sha256=record['backend_sha256'], ipc_sass=record['sass'],
                  ipc_materials_unchanged=True)


def check():
    # Load the backend before torch: tensor operations must not hide missing
    # CUDA runtime-library search paths by preloading libraries as a side effect.
    ipc = check_ipc()
    result = check_torch()
    capability = result['capability']
    assert f'sm_{capability[0]}{capability[1]}' in ipc['ipc_sass'], 'GPU lacks audited native IPC kernels'
    result.update(ipc, scope='cuda_operators_and_ipc_binary_load')
    print(json.dumps(result), flush=True)
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--link-only', action='store_true', help='no GPU operations; usable during image build')
    if parser.parse_args().link_only:
        print(json.dumps(dict(check_ipc(), scope='ipc_binary_load_only', task_physics_executed=False)), flush=True)
    else:
        check()
