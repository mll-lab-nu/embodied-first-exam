"""In-process Genesis checkpoints, including state omitted by ``SimState``.

These checkpoints belong to one built world. They are deliberately not a disk
format and cannot be applied to another scene or another Genesis version.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import random
import zlib
from typing import Any
from collections.abc import Mapping

import numpy as np


def require_finite_state(value, path="world"):
    """Fail at the physical tick that produced invalid observed numbers."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            require_finite_state(child, f"{path}/{key}")
    elif isinstance(value, (list, tuple)):
        for i, child in enumerate(value):
            require_finite_state(child, f"{path}/{i}")
    elif isinstance(value, np.ndarray):
        if value.dtype.kind in "fc" and not np.isfinite(value).all():
            raise FloatingPointError(f"Non-finite physical state at {path}")
    elif isinstance(value, (float, np.floating)) and not np.isfinite(value):
        raise FloatingPointError(f"Non-finite physical state at {path}")


@dataclass(frozen=True)
class BufferState:
    target: Any = field(repr=False, compare=False)
    value: Any = field(repr=False, compare=False)
    kind: str
    path: str = ""


@dataclass(frozen=True)
class PackedArray:
    """Lossless numeric storage; preserve dtype, layout values and NaN bits."""

    shape: tuple
    dtype: Any
    data: bytes = field(repr=False)
    tensor: bool = False

    @property
    def nbytes(self):
        return int(np.prod(self.shape, dtype=np.int64)) * self.dtype.itemsize

    @property
    def stored_nbytes(self):
        return len(self.data)


def pack_buffer(value):
    if isinstance(value, dict):
        return {key: pack_buffer(item) for key, item in value.items()}
    # Genesis exposes its full contact-capacity arrays as CPU tensors too.
    # Preserve their numeric kind when packing, so archive/layout validation
    # and restoration still see a Tensor rather than an ndarray.
    tensor = hasattr(value, "detach")
    if tensor:
        if value.numel()*value.element_size() < 65536:
            return value
        try:
            numeric = value.detach().cpu().numpy()
        except TypeError:
            # NumPy has no equivalent for some Torch dtypes (e.g. bfloat16).
            return value
    else:
        numeric = value
    if isinstance(numeric, np.ndarray) and numeric.nbytes >= 65536:
        if numeric.dtype.hasobject:
            raise ValueError("Physics checkpoints cannot contain object arrays")
        contiguous = np.ascontiguousarray(numeric)
        return PackedArray(
            numeric.shape,
            numeric.dtype,
            zlib.compress(memoryview(contiguous).cast("B"), level=1),
            tensor=tensor,
        )
    return value


def unpack_buffer(value):
    """Produce independent writable input storage for engine restoration."""
    if isinstance(value, PackedArray):
        raw = zlib.decompress(value.data)
        if len(raw) != value.nbytes:
            raise ValueError("Corrupt compressed physics buffer")
        result = np.frombuffer(raw, dtype=value.dtype).reshape(value.shape).copy()
        if value.tensor:
            import torch
            return torch.from_numpy(result)
        return result
    if isinstance(value, dict):
        return {key: unpack_buffer(item) for key, item in value.items()}
    return deepcopy(value)


@dataclass(frozen=True)
class WorldState:
    world_id: str
    physics_step: int
    native_state: Any = field(repr=False, compare=False)
    buffers: tuple[BufferState, ...] = field(repr=False, compare=False)
    engine_flags: tuple = field(repr=False, compare=False)
    entity_inputs: tuple = field(repr=False, compare=False)
    python_rng: Any = field(repr=False, compare=False)
    numpy_rng: Any = field(repr=False, compare=False)
    torch_rng: Any = field(repr=False, compare=False)
    cuda_rng: Any = field(repr=False, compare=False)
    world_rng: Any = field(repr=False, compare=False)
    scene_tick: int
    engine_substep: int
    ipc_state: Any = field(default=None, repr=False, compare=False)
    contact_events: Any = field(default=None, repr=False, compare=False)
    grasp_state: Any = field(default=None, repr=False, compare=False)


def copy_native_state(state, *, device=None):
    """Detach tensor storage without copying the scene referenced by SimState."""
    from copy import copy

    result = copy(state)
    result._solvers_state = []
    for solver_state in state.solvers_state:
        if solver_state is None:
            result._solvers_state.append(None)
            continue
        saved = copy(solver_state)
        for name, value in vars(solver_state).items():
            if hasattr(value, "detach"):
                tensor = value.detach()
                if device is not None:
                    tensor = tensor.to(device=device)
                setattr(saved, name, tensor.clone())
            elif isinstance(value, np.ndarray):
                setattr(saved, name, value.copy())
        result._solvers_state.append(saved)
    return result


def copy_engine_field(value):
    """Copy canonical CPU Quadrants storage without a per-field copy kernel.

    ``copy=None`` uses the engine's layout-aware host view when available and
    falls back for unsupported layouts/devices. The explicit NumPy copy is
    essential: a checkpoint must never retain that live engine view.
    """
    import quadrants as qd
    if isinstance(value, qd.Tensor) and qd.lang.impl.current_cfg().arch == qd.cpu:
        return value.to_numpy(copy=None).copy()
    return value.to_numpy()


def capture_engine_buffers(scene, previous=(), comparison_cache=None):
    """Copy engine buffers including control, contact and constraint caches.

    Genesis 1.2.1's public rigid state excludes control targets/modes, contact
    warm starts and hibernation. PBD state omits its constraint and coupling
    buffers. Snapshot all array storage in the supported solver/coupler object
    graph instead of guessing that position and velocity suffice.

    Scene references and per-link geometry graphs are not traversed. Entity
    numeric buffers (including IK scratch data) are included. Geometry arrays reached
    through a solver are copied too: this conservative first implementation
    spends memory to avoid silently omitting mutable numeric state.
    """
    import torch
    from genesis.utils.geom import SpatialHasher

    saved, seen = [], set()
    previous = {id(item.target): item for item in previous}
    cache_keys = set()
    allowed = (
        "genesis.engine.solvers",
        "genesis.engine.couplers",
        "genesis.engine.entities",
        "genesis.utils.array_class",
        "genesis.utils.mesh",
        "topogym.world.physics.ipc",
        "topogym.world.physics.fem",
    )

    def same_bytes(first, second):
        if isinstance(first, PackedArray) and isinstance(second, PackedArray):
            return (
                first.shape == second.shape
                and first.dtype == second.dtype
                and first.tensor == second.tensor
                and first.data == second.data
            )
        if isinstance(first, np.ndarray) and isinstance(second, np.ndarray):
            return (
                first.shape == second.shape
                and first.dtype == second.dtype
                and np.array_equal(
                    first.reshape(-1).view(np.uint8), second.reshape(-1).view(np.uint8)
                )
            )
        if isinstance(first, torch.Tensor) and isinstance(second, torch.Tensor):
            return (
                first.shape == second.shape
                and first.dtype == second.dtype
                and torch.equal(
                    first.reshape(-1).view(torch.uint8),
                    second.reshape(-1).view(torch.uint8),
                )
            )
        if (
            isinstance(first, dict)
            and isinstance(second, dict)
            and first.keys() == second.keys()
        ):
            return all(same_bytes(first[key], second[key]) for key in first)
        return False

    def freeze(value):
        if isinstance(value, np.ndarray):
            value.flags.writeable = False
        elif isinstance(value, dict):
            for item in value.values():
                freeze(item)

    def save(target, payload, kind, path):
        old = previous.get(id(target))
        # Keep at most one independent raw comparison copy for each large
        # buffer in this world. All mutable engine storage is still read every
        # tick. Exact byte equality (including NaN payloads and signed zero)
        # avoids recompressing unchanged data; this is not hash-based equality.
        raw = payload
        cacheable = comparison_cache is not None and (
            isinstance(raw, np.ndarray) and raw.nbytes >= 65536
            or isinstance(raw, torch.Tensor) and raw.numel()*raw.element_size() >= 65536
            or isinstance(raw, dict) and sum(getattr(v, "nbytes", 0) for v in raw.values()) >= 65536
        )
        if cacheable:
            key = id(target)
            cache_keys.add(key)
            cached = comparison_cache.get(key)
            if (old is not None and old.kind == kind and cached is not None
                    and cached[0] is old.value and same_bytes(cached[1], raw)):
                saved.append(old if old.path == path else BufferState(target, old.value, kind, path))
                return
        payload = pack_buffer(payload)
        if old is not None and old.kind == kind and same_bytes(old.value, payload):
            payload = old.value
        else:
            freeze(payload)
        if cacheable:
            # Keep the comparison independent even for an engine adapter whose
            # to_numpy() exposes a view. Its next write must not change our
            # remembered bytes and falsely match a stale compressed snapshot.
            raw_copy = deepcopy(raw)
            freeze(raw_copy)
            comparison_cache[key] = (payload, raw_copy)
        # The record is immutable too. Sharing unchanged records avoids
        # retaining thousands of new Python objects and path strings per tick.
        saved.append(old if old is not None and old.kind == kind and old.path == path
                     and payload is old.value else BufferState(target, payload, kind, path))

    def visit(value, path):
        if value is None or id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, np.ndarray):
            if value.flags.writeable:
                save(value, value.copy(), "numpy", path)
        elif isinstance(value, torch.Tensor):
            # Genesis FEM tensors subclass Tensor without implementing its
            # deepcopy protocol. Checkpoints retain numeric storage, not the
            # subclass's scene/gradient metadata; normalize before caching.
            save(value, value.detach().as_subclass(torch.Tensor).to(device="cpu", copy=True), "torch", path)
        elif callable(getattr(value, "to_numpy", None)) and callable(
            getattr(value, "from_numpy", None)
        ):
            # Genesis 1.2.1 SupportField.activate writes this mesh-local lookup
            # once. Stepping/FK/contact queries only read it; World forbids mesh
            # edits after build. Keep the full first payload in every checkpoint
            # without re-transferring gigabytes of immutable data each tick.
            # A new/lazily allocated field has a new identity and is copied.
            old = previous.get(id(value))
            if (
                path.startswith(
                    "RigidSolver/collider/_support_field/_support_field_info/"
                )
                and old is not None
            ):
                saved.append(old if old.kind == "engine" and old.path == path
                             else BufferState(value, old.value, "engine", path))
                return
            save(value, copy_engine_field(value), "engine", path)
        elif isinstance(value, dict):
            for key, item in value.items():
                label = (
                    key
                    if isinstance(key, (str, int))
                    else getattr(key, "name", type(key).__name__)
                )
                visit(item, f"{path}/{label}")
        elif isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                visit(item, f"{path}/{i}")
        elif type(value) is SpatialHasher:
            # Genesis 1.2.1 defines this class in utils.geom. Its three fields
            # are mutable PBD neighbor-search state, outside the solver graph's
            # module whitelist. Traverse them explicitly, not all of geom.
            for name in ("slot_size", "slot_start", "cur_cnt"):
                # Inactive solvers construct a hasher without allocating fields.
                visit(getattr(value, name, None), f"{path}/{name}")
        elif type(value).__module__.startswith(allowed):
            for name, item in vars(value).items():
                # _qd_dc_unwrapped is a cached dictionary of the exact same
                # Tensor storage above, not additional physical state.
                if name not in {
                    "_scene",
                    "scene",
                    "_sim",
                    "sim",
                    "_entities",
                    "_queried_states",
                    "_ckpt",
                    "_links",
                    "_joints",
                    "_geoms",
                    "_tgt_buffer",
                    "checkpoint_store",
                    "_qd_dc_unwrapped",
                }:
                    visit(item, f"{path}/{name}")

    for solver in scene.sim._active_solvers:
        visit(solver, type(solver).__name__)
    visit(scene.sim.coupler, "coupler")
    for entity in scene.sim.entities:
        visit(entity, f"entity/{entity.name}")
    if comparison_cache is not None:
        for key in comparison_cache.keys()-cache_keys:
            del comparison_cache[key]
    return tuple(saved)


def restore_engine_buffers(buffers):
    import torch

    with torch.no_grad():
        for saved in buffers:
            if saved.kind == "engine":
                saved.target.from_numpy(unpack_buffer(saved.value))
            elif saved.kind == "torch":
                saved.target.copy_(unpack_buffer(saved.value) if isinstance(saved.value, PackedArray) else saved.value)
            else:
                np.copyto(saved.target, unpack_buffer(saved.value))


def capture_rng(rng):
    import torch

    return (
        deepcopy(random.getstate()),
        deepcopy(np.random.get_state()),
        torch.random.get_rng_state().clone(),
        tuple(s.clone() for s in torch.cuda.get_rng_state_all())
        if torch.cuda.is_initialized()
        else (),
        deepcopy(rng.bit_generator.state),
    )


def restore_rng(state, rng):
    import torch

    random.setstate(deepcopy(state.python_rng))
    np.random.set_state(deepcopy(state.numpy_rng))
    torch.random.set_rng_state(state.torch_rng.clone())
    if state.cuda_rng:
        torch.cuda.set_rng_state_all([s.clone() for s in state.cuda_rng])
    rng.bit_generator.state = deepcopy(state.world_rng)
