"""Compatibility checks for numeric birth archives; provenance is not compatibility.

WORLD_RESTORE_SEMANTICS must change when world construction/restore semantics
change in a way not represented by scene identity, static geometry or layout.
Never migrate a v1 archive by editing its hashes: reprepare it instead.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from topogym.utils.io import canonical_hash, sha256_file
from topogym.world.state import PackedArray, unpack_buffer

CODEC = "rigid_pbd_numeric_v2"
WORLD_RESTORE_SEMANTICS = 1
ARCHIVE_REVISION = "gathered_archive_v2"


def resource_profile(backend=None):
    """Select an immutable archive family; full compatibility is still checked on load."""
    from importlib.metadata import version
    import torch
    if backend is None:
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(torch.cuda.current_device())
            device = dict(type="cuda", compute_capability=[props.major, props.minor],
                          multiprocessor_count=props.multi_processor_count)
        else:
            device = dict(type="cpu")
        dependencies = {p: version(p) for p in ("quadrants", "torch", "numpy")}
        genesis = version("genesis-world")
    else:
        device, dependencies, genesis = backend["device"], backend["dependencies"], backend["genesis"]
    hardware = (f"cuda_sm{device['compute_capability'][0]}{device['compute_capability'][1]}"
                f"_mp{device['multiprocessor_count']}" if device["type"] == "cuda" else device["type"])
    stack = canonical_hash(dict(genesis=genesis, dependencies=dependencies, codec=CODEC,
                                world_restore_semantics=WORLD_RESTORE_SEMANTICS))[:12]
    return f"{hardware}_{stack}"


def device_identity():
    import genesis as gs
    import torch
    device = torch.device(gs.device)
    if device.type != "cuda":
        return dict(type=device.type)
    props = torch.cuda.get_device_properties(device)
    return dict(type="cuda", compute_capability=[props.major, props.minor],
                multiprocessor_count=props.multi_processor_count,
                warp_size=props.warp_size if hasattr(props, "warp_size") else 32)


def layout(value):
    """No dynamic numeric values: equivalent packed/live buffers compare equal."""
    if isinstance(value, PackedArray):
        return dict(kind="tensor" if value.tensor else "array", shape=list(value.shape),
                    dtype=np.dtype(value.dtype).str)
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
        return dict(kind="tensor", shape=list(value.shape), dtype=value.dtype.str)
    if isinstance(value, np.ndarray):
        return dict(kind="array", shape=list(value.shape), dtype=value.dtype.str)
    if isinstance(value, dict):
        return {k: layout(v) for k, v in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return dict(kind=type(value).__name__, items=[layout(v) for v in value])
    return dict(kind=type(value).__name__)


def built_geometry(state):
    # Local rigid mesh data and cloth rest lengths are immutable under ordinary
    # simulation. Do not hash posed vertices, warm starts or contact scratch.
    prefixes = tuple(f"RigidSolver/data_manager/{name}/" for name in
                     ("verts_info", "faces_info", "edges_info", "geoms_info"))
    hashes = {}
    for buffer in state.buffers:
        if not (buffer.path.startswith(prefixes) or buffer.path.endswith(
                ("/_edges_len_rest", "/_inner_edges_len_rest", "/_vfaces"))):
            continue
        value = unpack_buffer(buffer.value)
        if hasattr(value, "detach"):
            value = value.detach().cpu().numpy()
        array = np.ascontiguousarray(value)
        hashes[buffer.path] = dict(layout=layout(buffer.value),
                                  sha256=hashlib.sha256(array.tobytes()).hexdigest())
    if not hashes:
        raise ValueError("No immutable geometry buffers found for v2 compatibility")
    return dict(sha256=canonical_hash(hashes), buffers=hashes)


def provenance(world):
    import genesis as gs
    import torch
    import os
    return dict(world_source_sha256=sha256_file(Path(__file__).parents[1]/"genesis_world.py"),
                codec_source_sha256=sha256_file(Path(__file__).with_name("pbd_initial_state.py")),
                compatibility_source_sha256=sha256_file(__file__),
                gpu_name=torch.cuda.get_device_name(gs.device) if torch.device(gs.device).type == "cuda" else None,
                torch_cuda=torch.version.cuda,
                preparation_image=os.environ.get("TOPOGYM_PREPARATION_IMAGE"))


def require_compatible(source, target, path="backend"):
    """Name the first incompatible field before touching destination state."""
    if isinstance(source, dict) and isinstance(target, dict) and source.keys() == target.keys():
        for key in sorted(source):
            require_compatible(source[key], target[key], f"{path}/{key}")
    elif source != target:
        raise ValueError(f"Frozen initial-state incompatibility at {path}: "
                         f"archive={str(source)[:320]}, runtime={str(target)[:320]}. "
                         "Use the archive's compatible software/GPU profile or prepare a new state; "
                         "do not rewrite hashes or resize physics buffers.")
