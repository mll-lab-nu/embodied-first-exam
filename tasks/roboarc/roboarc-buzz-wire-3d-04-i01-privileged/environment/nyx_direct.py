"""nyx_direct.py -- Nyx frames of MuJoCo states without Genesis: gs-nyx fed directly from the scene declarations.

The render bridge (render_bridge.py) keeps a never-stepped Genesis scene as Nyx's host and lets gs-nyx-plugin 0.1.4
export and drive it. This module produces the same Nyx input without genesis-world:

  - the static scene (gs_nyx.nyx_py_sdk SceneAsset, written with nps.export_scene_file): one instance per Genesis
    visual geometry or entity, materials, the camera rig, lights and the HDRI, built from what the MuJoCo world
    already holds (env_cfg, robot_cfg, the task's EntitySpecs and their generated assets) by the rules the plugin's
    exporter applies to the Genesis scene those declarations build;
  - the robot's visual meshes, compiled from its MJCF with MuJoCo exactly as Genesis' MJCF loader reads them and
    written with trimesh as the exporter writes them;
  - every frame, the rigid visual-geometry poses (MuJoCo body pose x the geometry's local pose) and the camera poses
    (wrist cameras follow their links), float32, Genesis Z-up and wxyz, in the plugin's order; the native call
    sequence is the plugin's: update, update_scene_buffers, set_env_map, render_frame per camera;
  - FEM deformables (ropes) as Nyx dynamic meshes: Genesis' surface triangles of the tetrahedra, and every frame the
    vertices a MuJoCo body chain skins (bind_chain, render_bridge.ChainSkin), as the host streams them.

    import nyx_direct
    nyx = nyx_direct.NyxDirect.from_world(session.env._world, instance=path)   # no Genesis anywhere; ropes bound
    nyx.update(model, data)
    rgb = nyx.render()                                            # {camera: (H, W, 3) uint8}
    depth = nyx.depth()                                           # {camera: (H, W) float32 m}, MuJoCo raster

Imports: numpy, trimesh, mujoco, topogym's Genesis-free helpers and gs_nyx; never genesis. CUDA buffers go through
the driver API with ctypes (libcuda.so.1). torch, when importable, runs the camera arithmetic so that it matches
today's host bit for bit (its CPU float32 kernels decide the last bit); without it a numpy replica is used.
Depth needs an OpenGL context (EGL on headless GPUs). docs/rcb/RENDER_BRIDGE.md has the evidence.

Licence note: gs-nyx 0.1.3 / gs-nyx-plugin 0.1.4 ship without a licence file; their documentation repository
(Genesis-Embodied-AI/nyx-for-genesis) is Apache-2.0. No plugin code is copied here: this module calls gs_nyx's
public API (nyx_py_sdk / nyx_py_renderer) and reproduces the data the plugin hands it, checked against recordings.
The pose and camera conventions follow Genesis (Apache-2.0), genesis/utils/geom.py and genesis/utils/mjcf.py.
"""
from __future__ import annotations

import ctypes
import hashlib
import math
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import numpy as np

SCENE_FILE = "nyx_scene.json"
# Genesis' raster depth camera draws into a 4x multisampled depth buffer and resolves it by its first sample, which
# NVIDIA places at (+1/8, -3/8) px from the pixel centre (x right, y down): the MuJoCo raster samples there too.
GENESIS_DEPTH_SAMPLE = (0.125, -0.375)
EPS = 1e-15                     # genesis.EPS (camera frame degeneracy threshold)


# --------------------------------------------------------------------------------------------- CUDA (driver API)
class _Cuda:
    """The device's primary context (the one Nyx retains), device buffers and copies, through libcuda.so.1."""

    def __init__(self, device: int = 0):
        self.lib = ctypes.CDLL("libcuda.so.1")
        self._check(self.lib.cuInit(0), "cuInit")
        self.dev = ctypes.c_int()
        self._check(self.lib.cuDeviceGet(ctypes.byref(self.dev), int(device)), "cuDeviceGet")
        self.ctx = ctypes.c_void_p()
        self._check(self.lib.cuDevicePrimaryCtxRetain(ctypes.byref(self.ctx), self.dev), "cuDevicePrimaryCtxRetain")
        self._check(self.lib.cuCtxSetCurrent(self.ctx), "cuCtxSetCurrent")
        self.lib.cuMemAlloc_v2.argtypes = [ctypes.POINTER(ctypes.c_uint64), ctypes.c_size_t]
        self.lib.cuMemFree_v2.argtypes = [ctypes.c_uint64]
        self.lib.cuMemcpyHtoD_v2.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
        self.lib.cuMemcpyDtoH_v2.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_size_t]
        self.lib.cuMemsetD8_v2.argtypes = [ctypes.c_uint64, ctypes.c_ubyte, ctypes.c_size_t]
        self.lib.cuMemcpyDtoD_v2.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_size_t]
        self.lib.cuMemAllocHost_v2.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t]
        self.lib.cuMemFreeHost.argtypes = [ctypes.c_void_p]
        self._buffers: list[int] = []
        self._host: list[int] = []

    @staticmethod
    def _check(code, what):
        if code != 0:
            raise RuntimeError(f"CUDA driver call {what} failed with error {code}")

    def current(self):
        self._check(self.lib.cuCtxSetCurrent(self.ctx), "cuCtxSetCurrent")

    def alloc(self, nbytes: int) -> int:
        ptr = ctypes.c_uint64()
        self._check(self.lib.cuMemAlloc_v2(ctypes.byref(ptr), max(int(nbytes), 1)), "cuMemAlloc")
        self._check(self.lib.cuMemsetD8_v2(ptr.value, 0, max(int(nbytes), 1)), "cuMemsetD8")
        self._buffers.append(ptr.value)
        return ptr.value

    def alloc_host(self, nbytes: int) -> np.ndarray:
        """Page-locked host memory as a uint8 array (fast, DMA-able copies)."""
        ptr = ctypes.c_void_p()
        self._check(self.lib.cuMemAllocHost_v2(ctypes.byref(ptr), max(int(nbytes), 1)), "cuMemAllocHost")
        self._host.append(ptr.value)
        return np.ctypeslib.as_array((ctypes.c_uint8 * max(int(nbytes), 1)).from_address(ptr.value))

    def copy_device(self, dst: int, src: int, nbytes: int) -> None:
        """Device-to-device copy on the legacy stream (no host synchronisation), as torch's tensor copy."""
        self._check(self.lib.cuMemcpyDtoD_v2(dst, src, nbytes), "cuMemcpyDtoD")

    def upload(self, ptr: int, array: np.ndarray) -> None:
        a = np.ascontiguousarray(array)
        self._check(self.lib.cuMemcpyHtoD_v2(ptr, a.ctypes.data, a.nbytes), "cuMemcpyHtoD")

    def download(self, ptr: int, out: np.ndarray) -> np.ndarray:
        self._check(self.lib.cuMemcpyDtoH_v2(out.ctypes.data, ptr, out.nbytes), "cuMemcpyDtoH")
        return out

    def synchronize(self) -> None:
        self._check(self.lib.cuCtxSynchronize(), "cuCtxSynchronize")

    def close(self) -> None:
        for ptr in self._buffers:
            self.lib.cuMemFree_v2(ptr)
        for ptr in self._host:
            self.lib.cuMemFreeHost(ptr)
        self._buffers.clear()
        self._host.clear()
        self.lib.cuDevicePrimaryCtxRelease(self.dev)


class _DLDevice(ctypes.Structure):
    _fields_ = [("device_type", ctypes.c_int32), ("device_id", ctypes.c_int32)]


class _DLDataType(ctypes.Structure):
    _fields_ = [("code", ctypes.c_uint8), ("bits", ctypes.c_uint8), ("lanes", ctypes.c_uint16)]


class _DLTensor(ctypes.Structure):
    _fields_ = [("data", ctypes.c_void_p), ("device", _DLDevice), ("ndim", ctypes.c_int32), ("dtype", _DLDataType),
                ("shape", ctypes.POINTER(ctypes.c_int64)), ("strides", ctypes.POINTER(ctypes.c_int64)),
                ("byte_offset", ctypes.c_uint64)]


_PyCapsule_GetPointer = ctypes.pythonapi.PyCapsule_GetPointer
_PyCapsule_GetPointer.restype = ctypes.c_void_p
_PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]


def _dlpack_pointer(obj) -> tuple[int, tuple]:
    """Device address and shape of an (H, W, 3) uint8 contiguous CUDA DLPack frame (Nyx's render_frame result)."""
    capsule = obj.__dlpack__()
    tensor = _DLTensor.from_address(_PyCapsule_GetPointer(capsule, b"dltensor"))
    shape = tuple(tensor.shape[i] for i in range(tensor.ndim))
    if tensor.dtype.code != 1 or tensor.dtype.bits != 8 or len(shape) != 3:
        raise ValueError(f"unexpected Nyx frame: dtype code {tensor.dtype.code}/{tensor.dtype.bits} bits, {shape}")
    if tensor.strides:
        strides = tuple(tensor.strides[i] for i in range(tensor.ndim))
        if strides != (shape[1] * shape[2], shape[2], 1):
            raise ValueError(f"non-contiguous Nyx frame: strides {strides}")
    return int(tensor.data or 0) + int(tensor.byte_offset), shape


def _dlpack_frame(obj, cuda: _Cuda) -> np.ndarray:
    """Copy an (H, W, 3) uint8 CUDA DLPack frame (Nyx's render_frame result) to a new host array."""
    capsule = obj.__dlpack__()
    tensor = _DLTensor.from_address(_PyCapsule_GetPointer(capsule, b"dltensor"))
    shape = tuple(tensor.shape[i] for i in range(tensor.ndim))
    if tensor.dtype.code != 1 or tensor.dtype.bits != 8 or len(shape) != 3:
        raise ValueError(f"unexpected Nyx frame: dtype code {tensor.dtype.code}/{tensor.dtype.bits} bits, {shape}")
    if tensor.strides:
        strides = tuple(tensor.strides[i] for i in range(tensor.ndim))
        if strides != (shape[1] * shape[2], shape[2], 1):
            raise ValueError(f"non-contiguous Nyx frame: strides {strides}")
    out = np.empty(shape, dtype=np.uint8)
    cuda.download(int(tensor.data or 0) + int(tensor.byte_offset), out)
    del capsule
    return out


# --------------------------------------------------------------------------------------------- pose math
def quat_mul(a, b) -> np.ndarray:
    """Hamilton product of wxyz quaternions (a then b in the frame of a: world = a * b)."""
    aw, ax, ay, az = np.moveaxis(np.asarray(a, dtype=np.float64), -1, 0)
    bw, bx, by, bz = np.moveaxis(np.asarray(b, dtype=np.float64), -1, 0)
    return np.stack([aw * bw - ax * bx - ay * by - az * bz,
                     aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw], axis=-1)


IDENTITY_QUAT = np.array([1.0, 0.0, 0.0, 0.0])


def genesis_quat_mul(u, v) -> np.ndarray:
    """genesis.utils.geom._np_quat_mul (Apache-2.0), the numpy product Genesis composes entity poses with while it
    builds them: its 8-multiplication form, normalised. Kept for its rounding (an axis-aligned turn keeps a 1e-16
    residue in a zero component, which float32 preserves)."""
    w1, x1, y1, z1 = (float(c) for c in u)
    w2, x2, y2, z2 = (float(c) for c in v)
    ww = (z1 + x1) * (x2 + y2)
    yy = (w1 - y1) * (w2 + z2)
    zz = (w1 + y1) * (w2 - z2)
    xx = ww + yy + zz
    qq = 0.5 * (xx + (z1 - x1) * (x2 - y2))
    out = np.array([qq - ww + (z1 - y1) * (y2 - z2), qq - xx + (x1 + w1) * (x2 + w2),
                    qq - yy + (w1 - x1) * (y2 + z2), qq - zz + (z1 + y1) * (w2 - x2)])
    return out / np.sqrt(np.sum(np.square(out)))


def quat_rotate(q, v) -> np.ndarray:
    """Rotate vectors v by wxyz quaternions q."""
    q = np.asarray(q, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    w, u = q[..., :1], q[..., 1:]
    t = 2.0 * np.cross(u, v)
    return v + w * t + np.cross(u, t)


def quat_to_R(q) -> np.ndarray:
    w, x, y, z = (float(c) for c in q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def euler_xyz_to_quat(rpy, degrees=False) -> np.ndarray:
    """Extrinsic x-y-z (roll, pitch, yaw) Euler angles to wxyz, as urdfpy / Genesis read URDF origins."""
    r, p, y = (math.radians(a) if degrees else float(a) for a in rpy)
    cr, sr, cp, sp, cy, sy = math.cos(r / 2), math.sin(r / 2), math.cos(p / 2), math.sin(p / 2), math.cos(y / 2), math.sin(y / 2)
    return np.array([cr * cp * cy + sr * sp * sy, sr * cp * cy - cr * sp * sy,
                     cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy])


def _f32(x) -> np.ndarray:
    return np.asarray(x, dtype=np.float32)


def camera_quat_f32(pos, lookat, up, *, device: str = "cpu") -> tuple[np.ndarray, np.ndarray]:
    """float32 position and wxyz rotation (Z-up) of a camera at pos looking at lookat, bit for bit as the plugin
    computes them: Genesis' pos_lookat_up_to_T + R_to_quat on float32 tensors, on the device the plugin uses (the
    Genesis host's compute backend, see NyxDirect).

    torch's float32 kernels decide the last bit (CPU: a vectorised sqrt that is not IEEE-rounded; CUDA: the norm's
    reduction order, contracted products and the scripted kernels), so when torch is importable the same scripted
    operations run on the same device; otherwise a numpy replica is used, which can differ by an ulp."""
    torch = _torch()
    if torch is not None and (device == "cpu" or torch.cuda.is_available()):
        return _camera_quat_torch(torch, pos, lookat, up, device)
    p, l, u = _f32(pos), _f32(lookat), _f32(up)
    norm = _norm_cpu
    z = (p - l).astype(np.float32)
    z_norm = norm(z)
    z = (z / max(z_norm, np.float32(EPS))).astype(np.float32)
    if z_norm < EPS:
        z = np.array((0.0, 1.0, 0.0) if abs(u[1]) < 0.5 else (0.0, 0.0, 1.0), dtype=np.float32)
    x = _cross_fma(u, z)
    x_norm = norm(x)
    x = (x / max(x_norm, np.float32(EPS))).astype(np.float32)
    R = np.stack([x, _cross_fma(z, x), z], axis=1).astype(np.float32)
    if x_norm < EPS:
        R = np.eye(3, dtype=np.float32)
    return p, _R_to_quat_f32(R)


def camera_quats_f32(poses, *, device: str = "cpu") -> tuple[np.ndarray, np.ndarray]:
    """camera_quat_f32 of several (pos, lookat, up): the same unbatched kernels per camera (as the plugin's per-camera
    calls), and one transfer back from the device for all of them (each transfer waits for the device)."""
    torch = _torch()
    if torch is None or (device != "cpu" and not torch.cuda.is_available()):
        out = [camera_quat_f32(*pose, device=device) for pose in poses]
        return np.stack([p for p, _ in out]), np.stack([q for _, q in out])
    quats = [_camera_quat_torch(torch, *pose, device, to_host=False) for pose in poses]
    # float64 -> float32 rounds the same way on the host as on the device
    return np.stack([np.asarray(pose[0], dtype=np.float64).astype(np.float32) for pose in poses]), \
        torch.stack(quats).cpu().numpy()


_TORCH = None
_WARM: set = set()


def _torch():
    """torch with Genesis' two scripted camera kernels (genesis/utils/geom.py, Apache-2.0, unchanged), or None."""
    global _TORCH
    if _TORCH is None:
        try:
            import torch
        except ImportError:
            _TORCH = False
            return None
        @torch.jit.script
        def _tc_R_to_quat(R, out=None):
            if out is None:
                quat = torch.zeros(R.shape[:-2] + (4,), dtype=R.dtype, device=R.device)
            else:
                quat = out
            r11, r12, r13 = R[..., 0, 0], R[..., 0, 1], R[..., 0, 2]
            r21, r22, r23 = R[..., 1, 0], R[..., 1, 1], R[..., 1, 2]
            r31, r32, r33 = R[..., 2, 0], R[..., 2, 1], R[..., 2, 2]
            trace = r11 + r22 + r33
            c0 = trace > 0.0
            c1 = (r11 > r22) & (r11 > r33)
            c2 = r22 > r33
            s = torch.where(
                c0,
                torch.sqrt(trace + 1.0) * 2,
                torch.where(
                    c1,
                    torch.sqrt(1.0 + r11 - r22 - r33) * 2,
                    torch.where(
                        c2,
                        torch.sqrt(1.0 + r22 - r11 - r33) * 2,
                        torch.sqrt(1.0 + r33 - r11 - r22) * 2,
                    ),
                ),
            )
            return torch.where(
                c0[..., None],
                torch.stack([0.25 * s, (r32 - r23) / s, (r13 - r31) / s, (r21 - r12) / s], dim=-1),
                torch.where(
                    c1[..., None],
                    torch.stack([(r32 - r23) / s, 0.25 * s, (r12 + r21) / s, (r13 + r31) / s], dim=-1),
                    torch.where(
                        c2[..., None],
                        torch.stack([(r13 - r31) / s, (r12 + r21) / s, 0.25 * s, (r23 + r32) / s], dim=-1),
                        torch.stack([(r21 - r12) / s, (r13 + r31) / s, (r23 + r32) / s, 0.25 * s], dim=-1),
                    ),
                ),
            )

        @torch.jit.script
        def _tc_z_up_to_R(z, eps: float, up=None, out: torch.Tensor | None = None):
            if out is None:
                R = torch.empty(z.shape[:-1] + (3, 3), dtype=z.dtype, device=z.device)
            else:
                R = out
            R[..., 2] = z
            x, y, z = R[..., 0], R[..., 1], R[..., 2]
            z_norm = torch.linalg.vector_norm(z, ord=2, dim=-1, keepdim=True)
            z /= z_norm.clamp(min=eps)
            zero_mask = z_norm < eps
            if up is None:
                torch.where(zero_mask, torch.tensor((0.0, 1.0, 0.0), device=z.device, dtype=z.dtype), z, out=z)
            else:
                up_mask = up[..., 1:2].abs() < 0.5
                torch.where(zero_mask & up_mask, torch.tensor((0.0, 1.0, 0.0), device=z.device, dtype=z.dtype), z, out=z)
                torch.where(zero_mask & ~up_mask, torch.tensor((0.0, 0.0, 1.0), device=z.device, dtype=z.dtype), z, out=z)
            if up is not None:
                x[:] = torch.cross(torch.broadcast_to(up, z.shape), z, dim=-1)
            else:
                up_mask = z[..., 2:].abs() < 1.0 - eps
                torch.where(up_mask, z[..., 1], z[..., 2], out=x[..., 0])
                torch.where(up_mask, -z[..., 0], 0.0, out=x[..., 1])
                torch.where(up_mask, 0.0, -z[..., 0], out=x[..., 2])
            x_norm = torch.linalg.vector_norm(x, ord=2, dim=-1, keepdim=True)
            x /= x_norm.clamp(min=eps)
            zero_x_mask = x_norm < eps
            torch.where(zero_x_mask[..., None], torch.eye(3, device=z.device, dtype=z.dtype), R, out=R)
            torch.where(~zero_x_mask, torch.cross(z, x, dim=-1), y, out=y)
            return R

        _TORCH = (torch, _tc_z_up_to_R, _tc_R_to_quat)
    return None if _TORCH is False else _TORCH[0]


def _camera_quat_torch(torch, pos, lookat, up, device, *, to_host=True):
    """The plugin's update_camera_tensor / camera_get_quaternion arithmetic (float32 tensors on `device`)."""
    _, z_up_to_R, R_to_quat = _TORCH
    dev = torch.device(device)
    if dev.type not in _WARM:                 # the profiling executor's first runs, as in a long-running host
        for _ in range(3):
            w = torch.tensor((0.3, -0.2, 1.1), dtype=torch.float32, device=dev)
            T = torch.zeros((4, 4), dtype=torch.float32, device=dev)
            R_to_quat(z_up_to_R(w, EPS, up=torch.tensor((0.0, 0.0, 1.0), dtype=torch.float32, device=dev),
                                out=T[..., :3, :3]))
        _WARM.add(dev.type)
    p, l, u = (torch.as_tensor(np.asarray(v, dtype=np.float64), device=dev).to(torch.float32) for v in (pos, lookat, up))
    T = torch.zeros((4, 4), dtype=torch.float32, device=dev)
    T[..., 3, 3] = 1.0
    T[..., :3, 3] = p
    z_up_to_R(p - l, EPS, up=u, out=T[..., :3, :3])
    q = R_to_quat(T[..., :3, :3])
    return (p.cpu().numpy(), q.cpu().numpy()) if to_host else q


def _fma32(a, b, c):
    """float32 fused multiply-add: the float64 product of two float32 values is exact."""
    return np.float32(np.float64(a) * np.float64(b) + np.float64(c))


def _cross_fma(a, b) -> np.ndarray:
    f = np.float32
    return np.array([_fma32(a[j], b[k], -f(a[k] * b[j])) for j, k in ((1, 2), (2, 0), (0, 1))], dtype=f)


def _norm_cpu(v):
    f = np.float32
    return f(np.sqrt(f(f(f(v[0] * v[0]) + f(v[1] * v[1])) + f(v[2] * v[2]))))


def _R_to_quat_f32(R) -> np.ndarray:
    """genesis.utils.geom._tc_R_to_quat in float32 scalar operations (exact where sqrt is IEEE-rounded, e.g. CUDA)."""
    f = np.float32
    r11, r12, r13 = R[0]
    r21, r22, r23 = R[1]
    r31, r32, r33 = R[2]
    trace = f(f(r11 + r22) + r33)
    if trace > 0.0:
        s = f(np.sqrt(f(trace + f(1.0))) * f(2))
        q = (f(f(0.25) * s), f(f(r32 - r23) / s), f(f(r13 - r31) / s), f(f(r21 - r12) / s))
    elif r11 > r22 and r11 > r33:
        s = f(np.sqrt(f(f(f(1.0) + r11) - r22) - r33) * f(2))
        q = (f(f(r32 - r23) / s), f(f(0.25) * s), f(f(r12 + r21) / s), f(f(r13 + r31) / s))
    elif r22 > r33:
        s = f(np.sqrt(f(f(f(1.0) + r22) - r11) - r33) * f(2))
        q = (f(f(r13 - r31) / s), f(f(r12 + r21) / s), f(f(0.25) * s), f(f(r23 + r32) / s))
    else:
        s = f(np.sqrt(f(f(f(1.0) + r33) - r11) - r22) * f(2))
        q = (f(f(r21 - r12) / s), f(f(r13 + r31) / s), f(f(r23 + r32) / s), f(f(0.25) * s))
    return np.array(q, dtype=np.float32)


def lookat_T(pos, lookat, up) -> np.ndarray:
    """float64 camera-to-world transform (Genesis' numpy pos_lookat_up_to_T: columns x = up x z, y = z x x, z = pos - lookat)."""
    pos, lookat, up = (np.asarray(v, dtype=np.float64) for v in (pos, lookat, up))
    z = pos - lookat
    n = np.sqrt(np.sum(np.square(z)))
    z = z / n if n > EPS else np.array((0.0, 1.0, 0.0) if abs(up[1]) < 0.5 else (0.0, 0.0, 1.0))
    x = np.cross(up, z)
    xn = np.linalg.norm(x)
    T = np.eye(4)
    if xn > EPS:
        x = x / xn
        T[:3, :3] = np.stack([x, np.cross(z, x), z], axis=1)
    T[:3, 3] = pos
    return T


# --------------------------------------------------------------------------------------------- surfaces / materials
@dataclass
class Surface:
    """What the plugin's exporter reads of a Genesis surface (its shortcut fields and texture slots)."""
    kind: str = "Default"
    color: tuple | None = None
    opacity: float | None = None
    roughness: float | None = None
    metallic: float | None = None
    emissive: tuple | None = None
    diffuse: Any = None                 # None | ("color", rgba) | ("image", path or None, metadata texture key)
    normal: str | None = None           # image path
    emissive_texture: Any = None
    double_sided: bool | None = None

    @classmethod
    def plastic(cls, color, roughness, metallic=None):
        color = tuple(float(c) for c in color)
        return cls(kind="Plastic", color=color, roughness=float(roughness),
                   metallic=None if metallic is None else float(metallic), diffuse=("color", color))

    @classmethod
    def from_spec(cls, parameters: dict, visual_root=None):
        """topogym.world.visuals.surfaces.from_spec: gs.surfaces.Default(**options), a diffuse image path allowed."""
        o = dict(parameters or {})
        image = o.pop("diffuse_texture_path", None)
        s = cls(kind="Default")
        if image is not None:
            s.diffuse = ("image", str(Path(image).expanduser().resolve()), None)
        for key in ("color", "emissive"):
            if o.get(key) is not None:
                setattr(s, key, tuple(float(c) for c in o.pop(key)))
        for key in ("opacity", "roughness", "metallic"):
            if o.get(key) is not None:
                setattr(s, key, float(o.pop(key)))
        if o.get("double_sided") is not None:
            s.double_sided = bool(o.pop("double_sided"))
        unsupported = {k: v for k, v in o.items() if v is not None and k not in ("vis_mode", "smooth")}
        if unsupported:
            raise NotImplementedError(f"surface options not supported by nyx_direct: {sorted(unsupported)}")
        if s.color is not None:
            s.diffuse = ("color", s.color)
        if s.emissive is not None:
            s.emissive_texture = ("color", s.emissive)
        return s

    def finish(self, rule, visual_root) -> None:
        """topogym.world.visuals.nyx.apply_finishes for one entity's surfaces."""
        color = tuple(float(v) for v in rule["color"])
        self.color = color
        self.diffuse = ("color", color)
        self.metallic = float(rule["metallic"])
        self.roughness = float(rule["roughness"])
        if "diffuse_map" in rule:
            self.diffuse = ("image", str(visual_root(rule["diffuse_map"])), None)
        if "normal_map" in rule:
            self.normal = str(visual_root(rule["normal_map"]))


def material_override(nps, surface: Surface, *, plane_size=None, genesis_assets=None, overridden=False):
    """gs_nyx_plugin's material override of a surface (MaterialAsset): albedo / opacity, emission, roughness,
    metalness, albedo / normal / emission textures, double-sided, a textured plane's UV scale. `overridden`: the
    surface replaces a mesh file's own materials (a glTF entity whose surface has a texture: Genesis'
    is_visual_overwritten), so the file's textures are unset first."""
    mat = nps.MaterialAsset()
    P = nps.EMaterialProperty
    if overridden:
        for flag, attr in ((P.AlbedoTexture, "albedoTexture"), (P.NormalTexture, "normalTexture"),
                           (P.ArmTexture, "armTexture"), (P.EmissionTexture, "emissionTexture")):
            mat.set_properties(flag)
            setattr(mat, attr, "")
    if surface.color is not None:
        mat.set_properties(P.AlbedoColor)
        alpha = 1.0 if surface.opacity is None else surface.opacity
        mat.albedoColor = nps.float4(surface.color[0], surface.color[1], surface.color[2], alpha)
    elif surface.opacity is not None:
        mat.set_properties(P.AlbedoColor)
        mat.albedoColor = nps.float4(1.0, 1.0, 1.0, surface.opacity)
    has_emission = False
    if surface.emissive is not None:
        mat.set_properties(P.Emission)
        mat.emission = nps.float3(*surface.emissive)
        has_emission = True
    elif isinstance(surface.emissive_texture, tuple) and surface.emissive_texture[0] == "color":
        c = np.atleast_1d(np.asarray(surface.emissive_texture[1])).ravel()
        mat.set_properties(P.Emission)
        mat.emission = nps.float3(float(c[0]), float(c[1]) if c.size > 1 else float(c[0]),
                                  float(c[2]) if c.size > 2 else float(c[0]))
        has_emission = True
    if surface.roughness is not None:
        mat.set_properties(P.PerceptualRoughness)
        mat.perceptualRoughness = surface.roughness
    if surface.metallic is not None:
        mat.set_properties(P.Metalness)
        mat.metalness = surface.metallic

    def texture(value, flag, attr):
        if value is None:
            return False
        mat.set_properties(flag)
        if value[0] == "image":
            path, key = value[1], value[2]
            if path:
                setattr(mat, attr, path)
            elif key:
                setattr(mat, attr, os.path.relpath(os.path.abspath(os.path.join(genesis_assets, key)), ".")
                        .replace("\\", "/"))
        else:
            setattr(mat, attr, "")
        return True

    has_diffuse = texture(surface.diffuse, P.AlbedoTexture, "albedoTexture")
    texture(None if surface.normal is None else ("image", surface.normal, None), P.NormalTexture, "normalTexture")
    has_emission = texture(surface.emissive_texture, P.EmissionTexture, "emissionTexture") or has_emission
    mat.set_properties(P.Sidedness)
    mat.sidedness = nps.EMaterialSidedness.Double
    if has_diffuse and plane_size is not None:
        mat.set_properties(P.UVScale)
        mat.uvScale = nps.float2(float(plane_size[0]), float(plane_size[1]))
    if has_emission:
        mat.set_properties(P.AlbedoColor)
        mat.albedoColor = nps.float4(0.0, 0.0, 0.0, 1.0)
        mat.set_properties(P.Metalness)
        mat.metalness = 1.0
    return mat


def full_material(nps, surface: Surface, *, genesis_assets=None):
    """The exporter's complete material of a dynamic mesh (no mesh file to fall back on): albedo always (white
    unless coloured), roughness / metalness when set, image textures, double-sided only when the surface says so."""
    mat = nps.MaterialAsset()
    P = nps.EMaterialProperty
    mat.set_properties(P.AlbedoColor)
    alpha = 1.0 if surface.opacity is None else surface.opacity
    c = surface.color if surface.color is not None else (1.0, 1.0, 1.0)
    mat.albedoColor = nps.float4(c[0], c[1], c[2], alpha)
    if surface.roughness is not None:
        mat.set_properties(P.PerceptualRoughness)
        mat.perceptualRoughness = surface.roughness
    if surface.metallic is not None:
        mat.set_properties(P.Metalness)
        mat.metalness = surface.metallic
    rel = lambda path: os.path.relpath(os.path.abspath(path if os.path.isabs(path) else os.path.join(genesis_assets, path)),
                                       ".").replace("\\", "/")
    if isinstance(surface.diffuse, tuple) and surface.diffuse[0] == "image" and surface.diffuse[1]:
        mat.set_properties(P.AlbedoTexture)
        mat.albedoTexture = rel(surface.diffuse[1])
    if surface.normal:
        mat.set_properties(P.NormalTexture)
        mat.normalTexture = rel(surface.normal)
    if surface.double_sided:
        mat.set_properties(P.Sidedness)
        mat.sidedness = nps.EMaterialSidedness.Double
    return mat


def color_material(nps, rgba_u8):
    """The exporter's material of a vertex-coloured visual geometry: albedo = its main colour / 255."""
    mat = nps.MaterialAsset()
    mat.set_properties(nps.EMaterialProperty.AlbedoColor)
    c = np.asarray(rgba_u8, dtype=np.float64) / 255.0
    mat.albedoColor = nps.float4(c[0], c[1], c[2], c[3])
    return mat


def _u8_color(rgba) -> np.ndarray:
    """trimesh's float -> uint8 colour conversion (ColorVisuals of a surface colour)."""
    from trimesh.visual.color import to_rgba
    return np.asarray(to_rgba(np.asarray(rgba, dtype=np.float64)), dtype=np.uint8).reshape(-1)[:4]


# --------------------------------------------------------------------------------------------- scene description
@dataclass
class Slot:
    """One rigid visual geometry of the Genesis scene (one Nyx reference / per-frame transform)."""
    entity: str
    node: str                       # reference node name: URDF link, MJCF "<link>_<k>", else ""
    body: str | None                # MuJoCo body carrying it (None: static)
    local_pos: np.ndarray
    local_quat: np.ndarray
    static_pos: np.ndarray | None = None
    static_quat: np.ndarray | None = None
    shape: tuple = ()               # geometry for the raster depth: ("plane", size) | ("box", size) | ("mesh", v, f)
    carrier: str | None = None      # a fixed entity's link: its MuJoCo body, drawn there when not welded to the world


@dataclass
class EntityRecord:
    name: str
    kind: str                       # plane | box | sphere | cylinder | mjcf | urdf | mesh | gltf | fem | pbd
    slots: list = field(default_factory=list)
    instances: list = field(default_factory=list)   # functions (nps, uuid) -> InstanceAsset fields


class NyxScene:
    """The Genesis-equivalent Nyx scene of one TopoGym tabletop instance, from its declarations (no Genesis)."""

    def __init__(self, env_cfg, robot_cfg, specs, *, manifest=None, genesis_assets=None, fem_birth=None,
                 pbd_birth=None, carriers=None):
        from omegaconf import OmegaConf
        self.env_cfg = env_cfg
        self.robot_cfg = robot_cfg
        self.specs = list(specs)
        self.genesis_assets = genesis_assets or _genesis_assets_dir()
        self.cfg = OmegaConf.to_container(env_cfg, resolve=True)
        # the MuJoCo scene's manifest: which body carries each entity link (scene.json "entities")
        self._bodies = {(name, link["name"]): link["body"] for name, record in ((manifest or {}).get("entities") or {}).items()
                        for link in record.get("links", [])}
        # FEM vertices at birth where the instance freezes them (an IPC settled state, see settled_fem_birth)
        self.fem_birth = dict(fem_birth or {})
        # the PBD solver's frozen state at birth where the instance restores one (see frozen_pbd_birth)
        self.pbd_birth = pbd_birth
        # free rigid entities carried by a MuJoCo body of another model of the same part (a FEM setting's ring, discs,
        # beads or handle on its chain's bodies; chain_cord_host): {entity: (body name, its birth position, its birth
        # wxyz)}, the entity drawn at body pose * (birth body pose)^-1 * entity pose, as render_bridge.bind_body
        self.carriers = dict(carriers or {})
        self.entities: list[EntityRecord] = []
        self._build()

    def _body(self, entity: str, link: str) -> str:
        """The MuJoCo body of an entity's link: the manifest's, a single-link entity's only body, else the scene
        builder's naming (<entity>::<link>, the entity itself for its base)."""
        if (entity, link) in self._bodies:
            return self._bodies[(entity, link)]
        own = [body for (name, _), body in self._bodies.items() if name == entity]
        if len(own) == 1:
            return own[0]
        return f"{entity}::{link}" if link != entity else entity

    # ------------------------------------------------------------------ declarations -> entities
    def _visual_root(self, name):
        from topogym.assets.library import visual_asset_path
        return visual_asset_path(name)

    def _rules(self):
        presentation = self.cfg.get("presentation") or {}
        return list(presentation.get("appearance", []) or []) + list(self.cfg.get("appearance", []) or [])

    def _finish(self, name, surface: Surface) -> Surface:
        rule = None
        for r in self._rules():
            if fnmatchcase(name, str(r["pattern"])):
                rule = r
        if rule is not None:
            surface.finish(rule, self._visual_root)
        return surface

    def _static_box(self, name, pos, size, surface, quat=(1.0, 0.0, 0.0, 0.0)):
        e = EntityRecord(name, "box")
        e.surface = self._finish(name, surface)
        e.pos, e.quat, e.size = tuple(float(v) for v in pos), tuple(float(v) for v in quat), tuple(float(v) for v in size)
        e.slots.append(Slot(name, "", None, np.zeros(3), np.array([1.0, 0, 0, 0]), shape=("box", e.size)))
        self._static_slots(e)
        return e

    def _build(self):
        from topogym.assets.surfaces import ROLE_ROUGHNESS
        world = self.cfg["world"]
        if bool(world.get("plane", {}).get("enabled", True)):
            e = EntityRecord("ground", "plane")
            e.plane_size = (1e3, 1e3)
            e.surface = self._finish("ground", Surface(kind="Default", diffuse=("image", None, "textures/checker.png")))
            e.slots.append(Slot("ground", "", None, np.zeros(3), np.array([1.0, 0, 0, 0]), np.zeros(3),
                                np.array([1.0, 0, 0, 0]), shape=("plane", e.plane_size)))
            self.entities.append(e)
        table = world["table"]
        self.entities.append(self._static_box("table", table["pos"], table["size"],
                                              Surface.plastic(table["color"], ROLE_ROUGHNESS["table"])))
        for name, pos, size, color in self._table_frame(table):
            self.entities.append(self._static_box(name, pos, size, Surface.plastic(color, ROLE_ROUGHNESS["frame"])))
        stage = world.get("stage")
        if stage is not None and bool(stage.get("enabled", True)):
            self.entities.append(self._static_box("stage", stage["pos"], stage["size"],
                                                  Surface.plastic(stage["color"], ROLE_ROUGHNESS["stage"])))
        self.entities.append(self._robot())
        for spec in self.specs:
            self.entities.append(self._task_entity(spec))
        from topogym.world.lab import compact_lab_layout
        for item in compact_lab_layout():
            self.entities.append(self._static_box(item["name"], item["pos"], item["size"],
                                                  Surface.plastic(item["color"], item["roughness"], item["metallic"])))

    def _table_frame(self, table):
        """topogym.world.tabletop.StandardTabletopBuilder._add_table_frame: the decorative rim and apron boxes."""
        frame = table.get("frame")
        if frame is not None and not bool(frame.get("enabled", True)):
            return []
        get = (lambda k, d: d) if frame is None else (lambda k, d: frame.get(k, d))
        band, height = float(get("band_width", 0.06)), float(get("height", 0.015))
        color = tuple(get("color", [0.40, 0.26, 0.14]))
        if band <= 0.0 or height <= 0.0:
            return []
        pos, size = [float(v) for v in table["pos"]], [float(v) for v in table["size"]]
        frames = self.cfg.get("frames")
        surface_z = (float(frames["table_surface"]["origin"][2]) if frames is not None
                     else float(np.array([0.0, 0.0, pos[2] + 0.5 * size[2]], dtype=float)[2]))
        sx, sy, sz = size
        if band >= 0.5 * min(sx, sy):
            return []
        min_x, max_x = pos[0] - 0.5 * sx, pos[0] + 0.5 * sx
        min_y, max_y = pos[1] - 0.5 * sy, pos[1] + 0.5 * sy
        zc = surface_z + 0.5 * height
        inner = sx - 2.0 * band
        bars = [("x_min", (min_x + 0.5 * band, pos[1], zc), (band, sy, height)),
                ("x_max", (max_x - 0.5 * band, pos[1], zc), (band, sy, height)),
                ("y_min", (pos[0], min_y + 0.5 * band, zc), (inner, band, height)),
                ("y_max", (pos[0], max_y - 0.5 * band, zc), (inner, band, height))]
        if bool(get("sides", True)):
            t = float(get("side_thickness", 0.012))
            if t > 0.0:
                bars += [("side_x_min", (min_x - 0.5 * t, pos[1], pos[2]), (t, sy + 2.0 * t, sz)),
                         ("side_x_max", (max_x + 0.5 * t, pos[1], pos[2]), (t, sy + 2.0 * t, sz)),
                         ("side_y_min", (pos[0], min_y - 0.5 * t, pos[2]), (sx, t, sz)),
                         ("side_y_max", (pos[0], max_y + 0.5 * t, pos[2]), (sx, t, sz))]
        return [(f"table_frame_{label}", p, s, color) for label, p, s in bars]

    # ------------------------------------------------------------------ the robot (MJCF, one instance per visual geom)
    def _robot(self):
        from topogym.assets.robot import robot_asset
        return self._mjcf("robot", Path(robot_asset(self.robot_cfg)), Surface(kind="Default"))

    def _mjcf(self, name, path, surface, fixed=False, pos=None, quat=None):
        """An MJCF entity: one instance per visual geometry (node "<link>_<k>"), its mesh as Genesis reads it."""
        e = EntityRecord(name, "mjcf")
        e.surface = self._finish(name, surface)
        if e.surface.color is not None:
            raise NotImplementedError(f"{name}: a finish rule on an MJCF entity (textured export) is not supported")
        e.geoms, e.path = [], path
        for g in mjcf_visual_geoms(compile_mjcf(path)):
            link = g["body"]
            k = sum(1 for x in e.geoms if x["body"] == link)
            g["node"] = f"{link}_{k}"
            e.geoms.append(g)
            e.slots.append(Slot(name, g["node"], None if fixed else self._body(name, link),
                                np.asarray(g["pos"], dtype=np.float64), np.asarray(g["quat"], dtype=np.float64),
                                shape=("mesh", g["trimesh"].vertices, g["trimesh"].faces)))
        if fixed:
            e.pos, e.quat = pos, quat
            self._static_slots(e)
        return e

    # ------------------------------------------------------------------ task entities
    def _task_entity(self, spec):
        kind = spec.morph_type
        if spec.physics_model == "fem_elastic":
            return self._fem(spec)
        if spec.physics_model == "pbd_cloth":
            return self._pbd(spec)
        if spec.physics_model != "rigid":
            raise NotImplementedError(f"{spec.name}: physics model {spec.physics_model} is not supported yet")
        e = EntityRecord(spec.name, kind)
        e.surface = self._finish(spec.name, Surface.from_spec(spec.surface))
        e.pos = tuple(float(v) for v in spec.position_m)
        e.quat = tuple(float(v) for v in spec.quaternion_wxyz)
        e.fixed = bool(spec.fixed)
        options = dict(spec.morph_options or {})
        e.options = options
        if kind == "mjcf":
            if e.fixed:
                raise NotImplementedError(f"{spec.name}: a fixed MJCF entity encodes its base in the model")
            return self._mjcf(spec.name, Path(spec.asset_path), Surface.from_spec(spec.surface))
        if kind == "urdf":
            e.path = Path(spec.asset_path)
            visuals = urdf_visuals(e.path)
            carried = not e.fixed and spec.name in self.carriers
            if carried and len({v[0] for v in visuals}) != 1:
                raise NotImplementedError(f"{spec.name}: a carried URDF entity must have one link")
            for link, origin_pos, origin_quat, shape in visuals:
                body, pos, quat = (None if e.fixed else self._body(spec.name, link)), np.asarray(origin_pos), \
                    np.asarray(origin_quat)
                if carried:
                    body, pos, quat = self._carried(spec.name, e, pos, quat)
                # a fixed entity is fixed at its base only: a link behind a joint (lock_picking's rotor discs on their
                # hinges) moves in the MuJoCo model, and _bind draws it at its body when that body is not welded
                e.slots.append(Slot(spec.name, link, body, pos, quat, shape=shape,
                                    carrier=self._body(spec.name, link) if e.fixed else None))
            if e.fixed:
                self._static_slots(e)
        elif kind == "mesh":
            e.path = Path(spec.asset_path)
            if os.path.splitext(str(e.path))[1].lower() in (".glb", ".gltf"):
                return self._gltf(spec, e, options)
            scale = options.get("scale", 1.0)
            e.slots.append(Slot(spec.name, "", None if e.fixed else self._body(spec.name, spec.name), np.zeros(3),
                                np.array([1.0, 0, 0, 0]), shape=_mesh_shape(e.path, scale)))
            if e.fixed:
                self._static_slots(e)
        elif kind == "box":
            e.size = tuple(float(v) for v in options["size"])
            e.slots.append(Slot(spec.name, "", None if e.fixed else self._body(spec.name, spec.name), np.zeros(3),
                                np.array([1.0, 0, 0, 0]), shape=("box", e.size)))
            if e.fixed:
                self._static_slots(e)
        elif kind == "cylinder":      # a primitive cylinder (radius, height; centred, along z): drawn as a mesh file
            import tempfile
            import trimesh
            tm = trimesh.creation.cylinder(radius=float(options["radius"]), height=float(options["height"]), sections=64)
            folder = Path(tempfile.mkdtemp(prefix="nyx_cyl_"))
            e.path = folder / f"{spec.name}.obj"
            tm.export(str(e.path))
            e.kind = "mesh"
            e.options = dict(options, file_meshes_are_zup=True)
            e.slots.append(Slot(spec.name, "", None if e.fixed else self._body(spec.name, spec.name), np.zeros(3),
                                np.array([1.0, 0, 0, 0]), shape=_mesh_shape(e.path, 1.0)))
            if e.fixed:
                self._static_slots(e)
        else:
            raise NotImplementedError(f"{spec.name}: morph {kind} is not supported yet")
        return e

    def _carried(self, name, e, origin_pos, origin_quat):
        """(MuJoCo body, local position, local wxyz) of a carried entity's visual geometry: its root link at the morph
        pose (as Genesis composes a URDF root: genesis_quat_mul with identity) seen from the carrier body's birth pose."""
        body, b_pos, b_quat = self.carriers[name]
        b_inv = np.array([b_quat[0], -b_quat[1], -b_quat[2], -b_quat[3]], dtype=np.float64)
        e_quat = genesis_quat_mul(np.asarray(e.quat, dtype=np.float64), IDENTITY_QUAT)
        offset_q = quat_mul(b_inv, e_quat)
        offset_p = quat_rotate(b_inv, np.asarray(e.pos, dtype=np.float64) - np.asarray(b_pos, dtype=np.float64))
        return body, offset_p + quat_rotate(offset_q, origin_pos), quat_mul(offset_q, origin_quat)

    def _gltf(self, spec, e, options):
        """A glTF mesh morph, as the plugin exports it: the entity whole (Nyx loads the file, its nodes and its own
        materials, which a textured surface overrides), at the morph pose; one reference per mesh Genesis makes of the
        file (gltf_mesh_groups), each at the entity's link pose. Genesis imports a glTF Y-up (its vertices turned to
        Z-up, imported_as_zup False); file_meshes_are_zup records the turn back as the morph's offset_quat, which the
        root link composes (_align_link)."""
        if not e.fixed:
            raise NotImplementedError(f"{spec.name}: a free glTF mesh entity is not supported yet")
        e.kind = "gltf"
        zup = bool(options.get("file_meshes_are_zup"))
        # morphs.Mesh._resolve_zup: the compensating turn (1, -1, 0, 0) composed onto the identity offset; a 3-vector
        # scale swaps its y and z
        e.offset_quat = genesis_quat_mul(IDENTITY_QUAT, np.array([1.0, -1.0, 0.0, 0.0])) if zup else IDENTITY_QUAT
        scale = options.get("scale", 1.0)
        scale = (float(scale),) * 3 if isinstance(scale, (int, float)) else tuple(float(v) for v in scale)
        if zup:
            scale = (scale[0], scale[2], scale[1])
        e.scale = scale
        # gltf_utils.parse_mesh_glb: is_visual_overwritten = the morph's surface has a texture (its colour counts)
        e.overridden = Surface.from_spec(spec.surface).diffuse is not None
        groups = gltf_mesh_groups(e.path, bool(options.get("group_by_material", False)))
        shape = _gltf_shape(e.path, scale)
        for k in range(len(groups)):
            e.slots.append(Slot(spec.name, "", None, np.zeros(3), IDENTITY_QUAT, shape=shape if k == 0 else ("none",)))
        self._static_slots(e)
        return e

    def _fem(self, spec):
        """A FEM volume (topogym.world.physics.fem.add_volume): one Nyx DynamicMesh over all its vertices, its surface
        triangles as Genesis' FEMEntity extracts them from the tetrahedra, zero UVs; vertices stream every frame."""
        e = EntityRecord(spec.name, "fem")
        e.surface = self._finish(spec.name, Surface.from_spec(spec.surface))
        with np.load(Path(spec.volume_path), allow_pickle=False) as data:
            rest, spawn, elements = (data[key].copy() for key in ("rest", "spawn", "elements"))
        if tuple(spec.quaternion_wxyz) != (1.0, 0.0, 0.0, 0.0):
            raise ValueError("Explicit FEM volume currently requires identity orientation")
        spawn = spawn + np.asarray(spec.position_m)
        verts = spawn.astype(np.float64)
        if spec.name in self.fem_birth:
            e.birth_vertices = np.array(self.fem_birth[spec.name], dtype=np.float64)
            if e.birth_vertices.shape != verts.shape:
                raise ValueError(f"{spec.name}: frozen birth vertices {e.birth_vertices.shape}, volume {verts.shape}")
        else:
            com = verts.mean(axis=0)
            # FEMEntity.instantiate: rotate about the vertex mean by the (identity) morph rotation, offset 0
            e.birth_vertices = (verts - com) @ np.eye(3).T + com + np.zeros(3)
        e.material_coordinates = rest.astype(np.float64)
        e.triangles = fem_surface_triangles(elements)
        e.uvs = np.zeros((len(verts), 2), dtype=np.float32)
        return e

    def _pbd(self, spec):
        """A PBD cloth: one Nyx dynamic mesh over its visual vertices, which Genesis draws as weighted sums of
        supporting particles (PBDSolver.vverts_info, 12 per vertex), with the visual mesh's UVs and faces. Those tables
        come from the PBD solver's state the instance freezes (frozen_pbd_birth); nothing is recomputed. The particles
        come from the MuJoCo cloth once bound (bind_cloth); until then, the frozen state's. One PBD entity per scene
        (the archive is the solver's)."""
        if self.pbd_birth is None:
            raise NotImplementedError(f"{spec.name}: a PBD cloth needs the instance's frozen PBD state")
        if any(x.kind == "pbd" for x in self.entities):
            raise NotImplementedError(f"{spec.name}: more than one PBD entity is not supported yet")
        e = EntityRecord(spec.name, "pbd")
        e.surface = self._finish(spec.name, Surface.from_spec(spec.surface))
        if e.surface.double_sided is None:
            e.surface.double_sided = True       # Scene.add_entity: a cloth material's surface defaults to double-sided
        state = self.pbd_birth
        e.birth_particles = np.asarray(state["particles"], dtype=np.float64)
        e.support_idxs = np.asarray(state["support_idxs"], dtype=np.int64)
        e.support_weights = np.asarray(state["support_weights"], dtype=np.float64)
        e.uvs = np.asarray(state["uvs"]).astype(np.float32)
        e.triangles = np.asarray(state["faces"], dtype=np.int32)
        e.birth_vertices = pbd_visual_vertices(e.birth_particles, e.support_idxs, e.support_weights)
        return e

    def _static_slots(self, e):
        """World poses of a fixed entity's visual geometries, as Genesis holds them: its root link composed with the
        morph quaternion (a scene file's base by _parse_scene, then every root by _align_link's morph offset: identity,
        or a glTF's z-up turn), each geometry's local pose on top, normalised (qd_transform_quat_by_quat)."""
        root_q = np.asarray(e.quat, dtype=np.float64)
        if e.kind == "urdf":
            root_q = genesis_quat_mul(root_q, IDENTITY_QUAT)
        root_q = genesis_quat_mul(root_q, getattr(e, "offset_quat", IDENTITY_QUAT))
        root_p = np.asarray(e.pos, dtype=np.float64)
        for s in e.slots:
            q = quat_mul(root_q, s.local_quat)
            s.static_quat = q / np.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
            s.static_pos = root_p + quat_rotate(root_q, s.local_pos)

    # ------------------------------------------------------------------ cameras, lights, environment
    def camera_defs(self) -> list[dict]:
        """The rig as NyxCameraSensor records it (topogym.sensors.renderers.nyx.camera_kwargs + the sensor options)."""
        out = []
        renderer = self.cfg["renderer"]
        for name, cam in self.cfg["cameras"].items():
            d = dict(name=name, res=list(cam["res"]), pos=list(cam["pos"]), lookat=list(cam["lookat"]),
                     up=list(cam.get("up", [0, 0, 1])), fov=float(cam["fov"]), near=float(cam.get("near", 0.1)),
                     far=float(cam.get("far", 20.0)), spp=int(renderer["spp"]), denoise=bool(renderer["denoise"]),
                     attach=None)
            attach = cam.get("attach")
            if attach is not None and attach.get("enabled", True):
                offset = attach.get("offset_T")
                if offset is None:
                    offset = lookat_T(attach.get("offset_pos", [0, 0, 0]), attach.get("offset_lookat", [0.1, 0, 0]),
                                      attach.get("offset_up", [0, 0, 1]))
                d["attach"] = dict(entity=str(attach.get("entity", "robot")), link=str(attach.get("link", "hand")),
                                   offset_T=np.asarray(offset, dtype=np.float64))
            out.append(d)
        return out

    def lights(self) -> list[dict]:
        return list(self.cfg["renderer"].get("lights") or [])

    # ------------------------------------------------------------------ export (gs_nyx SDK)
    def export(self, folder: Path, *, camera_device: str = "cpu") -> dict:
        """Write nyx_scene.json (nps.export_scene_file) and the robot's visual-geometry OBJ files into folder; return
        the reference table and slot layout the renderer needs. camera_device: see NyxDirect."""
        import gs_nyx.nyx_py_sdk as nps
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        asset = nps.SceneAsset()
        asset.version = 1
        # Nyx resolves relative URIs against <scene folder>/<rootFolder>; the URIs here are relative to the working
        # directory, as the plugin's (whose folder is __nyx_cache__/<id>, rootFolder "../../").
        asset.rootFolder = os.path.relpath(os.getcwd(), folder.resolve()).replace("\\", "/") + "/"
        # the exporter's order: rigid entities first, then FEM (the deformable index space of the renderer)
        ordered = ([e for e in self.entities if e.kind not in ("fem", "pbd")] + [e for e in self.entities if e.kind == "fem"]
                   + [e for e in self.entities if e.kind == "pbd"])
        n_instances = sum(len(e.geoms) if e.kind == "mjcf" else (len(e.slots) if e.kind == "mesh" else 1)
                          for e in ordered)
        cams, lights = self.camera_defs(), self.lights()
        asset.instance_resize(n_instances)
        asset.camera_resize(len(cams))
        asset.light_resize(len(lights))
        asset.env_map_resize(1)
        asset.light_field_resize(0)
        I, P = nps.EInstanceType, nps.EPrimitiveType
        yup = nps.float3_z_up_to_y_up_a
        references, uuids = [], {}
        index = 0

        def entity_pose(inst, pos, quat):
            inst.position = yup(nps.float3(pos[0], pos[1], pos[2]))
            q = nps.quaternion(quat[0], quat[1], quat[2], quat[3])
            inst.rotation = nps.quaternion_z_up_to_y_up_a(nps.quaternion_wxyz_to_xyzw(q))

        def zero_pose(inst):
            inst.position = yup(nps.float3(0.0, 0.0, 0.0))
            inst.rotation = nps.quaternion_z_up_to_y_up_a(nps.quaternion_wxyz_to_xyzw(nps.quaternion(1.0, 0.0, 0.0, 0.0)))

        deformables, v_start, t_start = [], 0, 0
        for e in ordered:
            uuid = nps.generate_uuid()
            uuids[e.name] = uuid
            if e.kind in ("fem", "pbd"):
                inst = asset.get_instance(index)
                inst.type = I.DynamicMesh
                inst.dynamicMesh_numVertices = len(e.birth_vertices)
                inst.dynamicMesh_numTriangles = len(e.triangles)
                inst.position = nps.float3(0.0, 0.0, 0.0)          # vertices stream in world space
                inst.rotation = nps.quaternion(0.0, 0.0, 0.0, 1.0)
                inst.scale = yup(nps.float3(1.0, 1.0, 1.0))
                inst.matOverride = full_material(nps, e.surface, genesis_assets=self.genesis_assets)
                inst.smooth, inst.enabled, inst.uuid = False, True, uuid
                asset.set_instance(index, inst)
                index += 1
                deformables.append(dict(entity=e, uuid=uuid, v_start=v_start, n_vertices=len(e.birth_vertices),
                                        t_start=t_start, n_triangles=len(e.triangles)))
                v_start += len(e.birth_vertices)
                t_start += len(e.triangles)
                continue
            if e.kind == "mjcf":
                for g in e.geoms:
                    inst = asset.get_instance(index)
                    zero_pose(inst)
                    inst.type = I.Mesh
                    inst.convertAxis = True
                    inst.scale = yup(nps.float3(1.0, 1.0, 1.0))
                    mesh_name = self._export_geom(folder, g)
                    inst.mesh_uri = os.path.relpath(folder / mesh_name).replace("\\", "/")
                    inst.matOverride = color_material(nps, g["rgba_u8"])
                    inst.smooth, inst.enabled, inst.uuid = False, True, uuid
                    inst.name = g["node"]
                    asset.set_instance(index, inst)
                    index += 1
                continue
            if e.kind == "mesh":
                for _ in e.slots:
                    inst = asset.get_instance(index)
                    zero_pose(inst)
                    inst.type = I.Mesh
                    inst.convertAxis = bool(e.options.get("file_meshes_are_zup", True))
                    scale = e.options.get("scale", 1.0)
                    s = (scale, scale, scale) if isinstance(scale, (int, float)) else tuple(scale)
                    inst.scale = yup(nps.float3(*s))
                    inst.mesh_uri = os.path.relpath(str(e.path)).replace("\\", "/")
                    inst.matOverride = color_material(nps, _u8_color(_rgba(e.surface)))
                    inst.smooth, inst.enabled, inst.uuid = False, True, uuid
                    asset.set_instance(index, inst)
                    index += 1
                continue
            inst = asset.get_instance(index)
            if e.kind == "gltf":
                entity_pose(inst, e.pos, e.quat)
                inst.type = I.Mesh
                inst.mesh_uri = os.path.abspath(str(e.path)).replace("\\", "/")
                inst.convertAxis = False             # the vgeoms' imported_as_zup: a glTF is imported Y-up
                inst.scale = yup(nps.float3(*e.scale))
                inst.matOverride = material_override(nps, e.surface, genesis_assets=self.genesis_assets,
                                                     overridden=e.overridden)
            elif e.kind == "urdf":
                entity_pose(inst, e.pos, e.quat)
                inst.type = I.SubScene
                inst.subscene_uri = os.path.abspath(str(e.path)).replace("\\", "/")
                inst.convertAxis = bool(e.options.get("file_meshes_are_zup", True))
                scale = e.options.get("scale", 1.0)
                s = (scale, scale, scale) if isinstance(scale, (int, float)) else tuple(scale)
                inst.scale = yup(nps.float3(*s))
                inst.matOverride = material_override(nps, e.surface, genesis_assets=self.genesis_assets)
            elif e.kind == "plane":
                entity_pose(inst, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
                inst.type = I.Primitive
                inst.primitive_type = P.Plane
                inst.scale = yup(nps.float3(e.plane_size[0], e.plane_size[1], 1.0))
                inst.matOverride = material_override(nps, e.surface, plane_size=e.plane_size,
                                                     genesis_assets=self.genesis_assets)
            elif e.kind == "box":
                entity_pose(inst, e.pos, e.quat)
                inst.type = I.Primitive
                inst.primitive_type = P.Box
                inst.scale = yup(nps.float3(*e.size))
                inst.matOverride = material_override(nps, e.surface, genesis_assets=self.genesis_assets)
            else:
                raise NotImplementedError(e.kind)
            inst.smooth, inst.enabled, inst.uuid = False, True, uuid
            asset.set_instance(index, inst)
            index += 1
        assert index == n_instances, (index, n_instances)
        for i, cam in enumerate(cams):
            c = asset.get_camera(i)
            c.position = yup(nps.float3(*cam["pos"]))
            _, q = camera_quat_f32(cam["pos"], cam["lookat"], cam["up"], device=camera_device)
            qx = nps.quaternion_conjugate(nps.quaternion_z_up_to_y_up_a(nps.quaternion_wxyz_to_xyzw(
                nps.quaternion(float(q[0]), float(q[1]), float(q[2]), float(q[3])))))
            c.rotation = nps.quaternion_mul(nps.quaternion(0.5, 0.5, 0.5, 0.5), qx)
            c.fovY = math.radians(cam["fov"])
            c.resolution = nps.uint2(int(cam["res"][0]), int(cam["res"][1]))
            c.aperture, c.focalLength = 2.8, 10.0
            c.nearPlane, c.farPlane = cam["near"], cam["far"]
            c.spp, c.denoise = cam["spp"], cam["denoise"]
            c.toneMapper, c.antiAliasing = nps.EToneMapper.Reinhard, nps.EAntiAliasing.SMAA
            asset.set_camera(i, c)
        for i, light in enumerate(lights):
            asset.set_light(i, light_asset(nps, light))
        env = nps.EnvironmentMapAsset()
        env.texture = str(self._visual_root(self.cfg["renderer"]["env_map"]))
        env.layout = nps.EEnvMapLayout.LongLat
        env.multiplier = float(self.cfg["renderer"]["env_intensity"])
        asset.set_env_map(0, env)
        path = folder / SCENE_FILE
        nps.export_scene_file(str(path), asset)
        slots = [s for e in ordered for s in e.slots]
        for s in slots:
            references.append((uuids[s.entity], s.node))
        references += [(d["uuid"], "") for d in deformables]
        return dict(path=path, references=references, slots=slots, cameras=cams, deformables=deformables)

    def _export_geom(self, folder: Path, g) -> str:
        mesh = g["trimesh"]
        data = mesh.export(file_type="obj")
        data = data.encode() if isinstance(data, str) else data
        name = hashlib.sha256(data).hexdigest()[:16] + ".obj"
        target = folder / name
        if not target.exists():
            target.write_bytes(data)
        return name


def _rgba(surface: Surface):
    c = surface.color if surface.color is not None else (1.0, 1.0, 1.0)
    alpha = c[3] if len(c) > 3 else 1.0
    if surface.opacity is not None:
        alpha = surface.opacity
    return (c[0], c[1], c[2], alpha)


def light_asset(nps, d: dict):
    """A light dict of the renderer config as the Nyx sensor converts it (Z-up -> Y-up)."""
    light = nps.LightAsset()
    kind = d.get("type", "directional")
    yup = nps.float3_z_up_to_y_up_a
    if kind == "point":
        light.type = nps.ELightType.Point
        light.point_position = yup(nps.float3(*d.get("pos", (0, 0, 5))))
        light.point_range = d.get("range", 100.0)
        light.unit = nps.ELightUnit.Lumen
    elif kind == "directional":
        light.type = nps.ELightType.Directional
        light.directional_direction = yup(nps.float3(*d.get("dir", (0, 0, -1))))
        light.unit = nps.ELightUnit.Lux
    elif kind == "spot":
        light.type = nps.ELightType.Spot
        light.spot_position = yup(nps.float3(*d.get("pos", (0, 0, 5))))
        light.spot_direction = yup(nps.float3(*d.get("dir", (0, 0, -1))))
        light.spot_innerAngle = d.get("inner_angle", 15.0)
        light.spot_outerAngle = d.get("outer_angle", 30.0)
        light.spot_range = d.get("range", 100.0)
        light.unit = nps.ELightUnit.Lumen
    else:
        raise ValueError(f"unknown light type {kind}")
    color = d.get("color", (1, 1, 1))
    light.color = nps.float3(color[0], color[1], color[2])
    light.intensity = d.get("intensity", 1.0)
    light.shadow = d.get("shadow", True)
    return light


def _genesis_assets_dir():
    """Where genesis-world keeps its textures (the ground plane's checker), found without importing genesis."""
    from importlib.util import find_spec
    spec = find_spec("genesis")
    if spec is None or not spec.submodule_search_locations:
        return str(Path(__file__).resolve().parent / "nyx_assets")
    return str(Path(list(spec.submodule_search_locations)[0]) / "assets")


# --------------------------------------------------------------------------------------------- MJCF / URDF readers
def compile_mjcf(path: Path):
    """The MjModel Genesis' MJCF loader compiles (genesis.utils.mjcf.build_model): includes inlined, asset search
    directories absolute, Genesis' default constraint time constants (they do not touch visual meshes)."""
    import mujoco
    path = Path(path)
    tree = ET.parse(path)
    root = tree.getroot()
    stack = [(root, Path(""))]
    while stack:
        node, parent = stack.pop()
        for inc in tuple(node.findall("include")):
            inc_path = parent / inc.attrib["file"]
            inc_root = ET.parse(path.parent / inc_path).getroot()
            for mesh in inc_root.findall(".//mesh"):
                mesh.attrib["file"] = str(inc_path.parent / mesh.attrib["file"])
            for child in inc_root:
                root.append(child)
            root.remove(inc)
            stack.append((inc_root, inc_path))
    compiler = root.find("compiler")
    if compiler is None:
        compiler = ET.SubElement(root, "compiler")
    for name in ("assetdir", "meshdir", "texturedir"):
        compiler.attrib[name] = str(path.parent / compiler.attrib.get(name, ""))
    default = root.find("default")
    if default is None:
        default = ET.SubElement(root, "default")
    for group_name, params in (("geom", ("solref",)), ("joint", ("solreflimit", "solreffriction")),
                               ("equality", ("solref",))):
        group = default.find(group_name)
        if group is None:
            group = ET.SubElement(default, group_name)
        for p in params:
            group.attrib.setdefault(p, str(0.005))
    return mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="utf8"))


def mjcf_visual_geoms(mj) -> list[dict]:
    """Genesis' visual geometries of an MJCF (genesis.utils.mjcf.parse_geom / parse_geoms): per body in order, the
    visual geoms (contype = conaffinity = 0), then the body's collision geoms of groups 0-2 duplicated as visuals.
    Each comes as the trimesh Genesis renders (vertices split per (vertex, normal[, uv]), vertex colours from the
    geom's material or rgba) with its local pose."""
    import mujoco
    import trimesh
    out = []
    per_body: dict[int, list] = {}
    for i in range(mj.ngeom):
        b = int(mj.geom_bodyid[i])
        if b < 0:
            continue
        per_body.setdefault(b, []).append(i)
    for b in range(mj.nbody):
        geoms = per_body.get(b, [])
        visual = [i for i in geoms if not (mj.geom_contype[i] or mj.geom_conaffinity[i])]
        duplicated = [i for i in geoms if (mj.geom_contype[i] or mj.geom_conaffinity[i]) and mj.geom_group[i] in (0, 1, 2)]
        # The world body's geoms (#108's fixture in its worldbody): Genesis keeps them on the entity's base link "world",
        # which the MuJoCo scene builds as the static body "<entity>::world" (mjcf_entity.py); drawn on that body.
        for i in visual + duplicated:
            g = _mj_geom_trimesh(mj, i, is_col=i in duplicated)
            if g is None:
                continue
            g["body"] = mujoco.mj_id2name(mj, mujoco.mjtObj.mjOBJ_BODY, b)
            g["pos"] = np.array(mj.geom_pos[i], dtype=np.float64)
            g["quat"] = np.array(mj.geom_quat[i], dtype=np.float64)
            out.append(g)
    return out


def _mj_geom_trimesh(mj, i, *, is_col: bool):
    import mujoco
    import trimesh
    from trimesh.visual.color import ColorVisuals
    mat_id = int(mj.geom_matid[i])
    if mat_id >= 0:
        if mj.mat_texid[mat_id][int(mujoco.mjtTextureRole.mjTEXROLE_RGB)] >= 0 or \
                mj.mat_texid[mat_id][int(mujoco.mjtTextureRole.mjTEXROLE_RGBA)] >= 0:
            raise NotImplementedError("textured MJCF materials are not supported yet")
        rgba = np.asarray(mj.mat_rgba[mat_id], dtype=np.float32)
    else:
        rgba = np.asarray(mj.geom_rgba[i], dtype=np.float32)
    kind = int(mj.geom_type[i])
    size = mj.geom_size[i]
    G = mujoco.mjtGeom
    if kind == G.mjGEOM_MESH:
        m = int(mj.geom_dataid[i])
        v0, nv = int(mj.mesh_vertadr[m]), int(mj.mesh_vertnum[m])
        n0, nn = int(mj.mesh_normaladr[m]), int(mj.mesh_normalnum[m])
        f0, nf = int(mj.mesh_faceadr[m]), int(mj.mesh_facenum[m])
        vertices = mj.mesh_vert[v0:v0 + nv]
        normals = mj.mesh_normal[n0:n0 + nn]
        faces = mj.mesh_face[f0:f0 + nf]
        norm_faces = mj.mesh_facenormal[f0:f0 + nf]
        index = [faces.ravel(), norm_faces.ravel()]
        if int(mj.mesh_texcoordadr[m]) != -1:     # split per texcoord too; an untextured material drops the uvs
            index.append(mj.mesh_facetexcoord[f0:f0 + nf].ravel())
        uniq, inv = np.unique(np.stack(index, axis=1), axis=0, return_inverse=True)
        params = dict(vertices=vertices[uniq[:, 0]], faces=inv.reshape(-1, 3).astype(np.int64),
                      vertex_normals=normals[uniq[:, 1]])
    elif kind == G.mjGEOM_BOX:
        tm = trimesh.creation.box(extents=size * 2)
        params = dict(vertices=tm.vertices, faces=tm.faces)
    elif kind == G.mjGEOM_SPHERE:
        tm = trimesh.creation.icosphere(radius=size[0], subdivisions=2) if is_col else trimesh.creation.icosphere(radius=size[0])
        params = dict(vertices=tm.vertices, faces=tm.faces)
    elif kind == G.mjGEOM_CYLINDER:
        tm = trimesh.creation.cylinder(radius=size[0], height=size[1] * 2)
        params = dict(vertices=tm.vertices, faces=tm.faces)
    elif kind == G.mjGEOM_CAPSULE:
        tm = (trimesh.creation.capsule(radius=size[0], height=size[1] * 2, count=(8, 12)) if is_col
              else trimesh.creation.capsule(radius=size[0], height=size[1] * 2))
        params = dict(vertices=tm.vertices, faces=tm.faces)
    else:
        raise NotImplementedError(f"MJCF geom type {kind} is not supported yet")
    # Genesis: SimpleMaterial(diffuse=rgba) -> colour factor (uint8 diffuse / 255) -> ColorTexture -> vertex colours.
    # A collision geom copied as a visual one (group 0-2) is first a collision mesh with surfaces.Collision(), grey
    # (0.5, 0.5, 0.5) with the material's opacity: its trimesh's material colour applies only where it has texture
    # coordinates (a mesh with UVs); otherwise the grey vertex colours are what the copy keeps (genesis utils/mjcf.py
    # parse_geom / parse_geoms, engine/mesh.py from_trimesh; checked against Genesis 1.2.1: rgba .9 .8 .6 .6 -> 128 128
    # 128 153).
    from trimesh.visual.material import SimpleMaterial
    diffuse_u8 = SimpleMaterial(diffuse=rgba).diffuse
    color = tuple(np.array(diffuse_u8, dtype=np.float32) / 255.0)
    if is_col and not (kind == G.mjGEOM_MESH and int(mj.mesh_texcoordadr[int(mj.geom_dataid[i])]) != -1):
        color = (0.5, 0.5, 0.5, color[3])
    mesh = trimesh.Trimesh(**params, process=False)
    mesh.visual = ColorVisuals(vertex_colors=np.tile(np.array(color), [len(mesh.vertices), 1]))
    mesh.vertex_normals          # Genesis reads every visual mesh's normals: cached, the OBJ export writes them
    return dict(trimesh=mesh, rgba_u8=np.asarray(mesh.visual.main_color, dtype=np.uint8), geom=i)


def chain_cord_host(instance_path) -> dict | None:
    """A FEM setting whose cord is a MuJoCo chain (task parameter cord_model "chain": slotted_post_ring and orbits on
    MuJoCo) as render_bridge._chain_cord_host shows it, without Genesis: {"specs": the FEM setting's declared entities
    (cord_model "fem", declared and finalized as Env.reset does, into a temporary folder), "binding": the chain setting's
    render_host_binding() (the cord's chain bodies and material spans, the MuJoCo bodies carrying the rigid parts),
    "assets": the TemporaryDirectory holding the generated files}. None for any other instance. The process' random
    streams are left as they were (Env.reset seeds them before declaring)."""
    import json
    import random
    import tempfile
    inst = json.loads(Path(instance_path).read_text())
    cfg = dict(inst["simulator"])
    params = dict(cfg.get("task_parameters") or {})
    if params.get("cord_model") != "chain":
        return None
    from topogym.config.registry import task_definition, variation_registration
    from topogym.config.scene import load_scene_config
    from topogym.simulator.config import SimulatorConfig
    from topogym.utils.variant_rng import seed_process
    seed = int(cfg["seed"])
    variation = variation_registration(cfg["task_id"], cfg["variation_id"], seed)["variation_id"]
    host = {k: v for k, v in cfg.items() if k not in ("physics_engine", "mujoco_scene", "mujoco_settled_state")}
    host.update(task_parameters={**params, "cord_model": "fem"}, compute_backend="cuda", reset_physics_steps=0)
    scene_cfg = load_scene_config(SimulatorConfig(**host))
    table = scene_cfg.env.world.table
    top = float(table.pos[2] + table.size[2] / 2)
    try:
        import torch
    except ImportError:
        torch = None
    saved = (random.getstate(), np.random.get_state(), None if torch is None else torch.get_rng_state(),
             torch.cuda.get_rng_state_all() if torch is not None and torch.cuda.is_available() else None)
    folder = tempfile.TemporaryDirectory(prefix="nyx-direct-cord-")
    try:
        out = {}
        for model in ("chain", "fem"):
            seed_process(seed)
            task = task_definition(cfg["task_id"], variation)({**params, "cord_model": model}, seed=seed)
            assets = Path(folder.name) / model / "assets"
            spec = task.declare(assets, top)
            if model == "chain":
                out["binding"] = task.render_host_binding()
            else:
                out["specs"] = list(task.finalize_spec(spec, asset_dir=assets, scene_config=scene_cfg).entities)
    except BaseException:
        folder.cleanup()
        raise
    finally:
        random.setstate(saved[0])
        np.random.set_state(saved[1])
        if torch is not None:
            torch.set_rng_state(saved[2])
            if saved[3] is not None:
                torch.cuda.set_rng_state_all(saved[3])
    out["assets"] = folder
    return out


def settled_fem_birth(instance_path) -> dict[str, np.ndarray]:
    """{FEM entity: (N, 3) float64 vertices} at birth of a frozen instance that restores an IPC settled state
    (simulator.ipc_settled_state; topogym.world.physics.ipc_settled_state stores them as the archive's "fem" payload
    and checks the restored Genesis vertices against it bit for bit); {} when it has none."""
    import json
    from topogym.world.initial_state import load_numeric_archive
    path = Path(instance_path)
    settled = json.loads(path.read_text())["simulator"].get("ipc_settled_state")
    if not settled:
        return {}
    payload, _ = load_numeric_archive(Path(settled) if Path(settled).is_absolute() else path.parent / settled)
    return {name: np.asarray(v, dtype=np.float64) for name, v in payload["fem"].items()}


def frozen_pbd_birth(instance_path) -> dict | None:
    """The PBD solver's state at birth of a frozen instance that restores one (simulator.task_parameters.
    initial_state_path, topogym.world.initial_state's numeric archive, as the Genesis host restores it): particle
    positions, the visual vertices' supports (indices, weights), the visual mesh's UVs and faces; None without one."""
    import json
    from topogym.world.initial_state import load_numeric_archive
    path = Path(instance_path)
    archive = (json.loads(path.read_text())["simulator"].get("task_parameters") or {}).get("initial_state_path")
    if not archive:
        return None
    archive = Path(archive) if Path(archive).is_absolute() else path.parent / archive
    payload, _ = load_numeric_archive(archive)
    buffers = payload["buffers"]
    if "PBDSolver/vverts_info" not in buffers:
        return None

    def value(key):
        v = buffers[key]
        return v["value"] if isinstance(v, dict) and "value" in v else v

    info = value("PBDSolver/vverts_info")
    return dict(particles=np.asarray(value("PBDSolver/particles")["pos"], dtype=np.float64)[:, 0, :],
                support_idxs=np.asarray(info["support_idxs"]), support_weights=np.asarray(info["support_weights"]),
                uvs=np.asarray(value("PBDSolver/vverts_uvs")), faces=np.asarray(value("PBDSolver/vfaces_indices")))


def pbd_visual_vertices(particles, support_idxs, support_weights) -> np.ndarray:
    """Genesis' PBD visual vertices (PBDSolver._kernel_update_render_fields): per vertex, from zero, the sum over its
    supports in order of particle position x weight, in float64."""
    p = np.asarray(particles, dtype=np.float64)
    out = np.zeros((len(support_idxs), 3), dtype=np.float64)
    for j in range(support_idxs.shape[1]):
        out += p[support_idxs[:, j]] * support_weights[:, j:j + 1]
    return out


def fem_surface_triangles(elements) -> np.ndarray:
    """Boundary triangles of a tetrahedral mesh, in Genesis' FEMEntity order and orientation (each tetrahedron's
    faces (0 2 1), (1 2 3), (0 1 3), (0 3 2); faces seen once; rows sorted as np.unique sorts them)."""
    v = np.asarray(elements, dtype=np.int32)
    el2tri = np.stack([v[:, [0, 2, 1]], v[:, [1, 2, 3]], v[:, [0, 1, 3]], v[:, [0, 3, 2]]], axis=1)
    all_tri = el2tri.reshape(-1, 3)
    _, unique_idcs, cnt = np.unique(np.sort(all_tri, axis=1), axis=0, return_counts=True, return_index=True)
    return all_tri[unique_idcs][cnt == 1]


def urdf_visuals(path: Path) -> list[tuple]:
    """(link name, origin xyz, origin wxyz, depth shape) of every visual geometry Genesis makes of a URDF, links in
    document order: one per <visual>, except a mesh file holding several meshes, which Genesis' URDF loader makes one
    geometry each (a glTF's primitives, gltf_utils.parse_mesh_glb without grouping; other formats as urdfpy loads them).
    Each is one reference of the link; the first carries the whole file's depth shape, the others none."""
    path = Path(path)
    root = ET.parse(path).getroot()
    out = []
    for link in root.findall("link"):
        for vis in link.findall("visual"):
            origin = vis.find("origin")
            xyz = [0.0, 0.0, 0.0] if origin is None else [float(v) for v in origin.get("xyz", "0 0 0").split()]
            rpy = [0.0, 0.0, 0.0] if origin is None else [float(v) for v in origin.get("rpy", "0 0 0").split()]
            geometry = vis.find("geometry")
            mesh, box = geometry.find("mesh"), geometry.find("box")
            count = 1
            if mesh is not None:
                name = mesh.get("filename")
                name = name[len("package://"):] if name.startswith("package://") else name
                scale = [float(v) for v in mesh.get("scale", "1 1 1").split()]
                shape = _mesh_shape(path.parent / name, scale)
                count = _mesh_count(path.parent / name)
            elif box is not None:
                shape = ("box", tuple(float(v) for v in box.get("size").split()))
            else:
                raise NotImplementedError(f"{path.name}: URDF visual geometry {[c.tag for c in geometry]}")
            for k in range(count):
                out.append((link.get("name"), np.array(xyz), euler_xyz_to_quat(rpy), shape if k == 0 else ("none",)))
    return out


def _mesh_count(path) -> int:
    """How many meshes Genesis' URDF loader makes of a visual mesh file: a glTF's (node, primitive) instances, else the
    meshes of the file as trimesh loads it (urdfpy's load_meshes)."""
    import trimesh
    loaded = trimesh.load(str(path), process=False)
    if isinstance(loaded, trimesh.Scene):
        return len(loaded.graph.nodes_geometry) if str(path).lower().endswith((".glb", ".gltf")) else len(loaded.dump())
    return 1


def gltf_mesh_groups(path, group_by_material: bool = False) -> list:
    """The meshes Genesis makes of a glTF file (gltf_utils.parse_mesh_glb), in its order: the scene's mesh nodes in
    parse_glb_tree's walk (each node's children before the node), and per node one mesh per material of its
    primitives (one per material over the whole file when grouped by material); primitives of a mode other than
    triangles / strip / fan are skipped. Read from the file's JSON (no glTF library)."""
    import json
    import struct
    data = Path(path).read_bytes()
    if data[:4] == b"glTF":
        length, kind = struct.unpack_from("<II", data, 12)
        if kind != 0x4E4F534A:
            raise ValueError(f"{path}: the first GLB chunk is not JSON")
        doc = json.loads(data[20:20 + length])
    else:
        doc = json.loads(data)
    nodes, meshes = doc.get("nodes", []), doc.get("meshes", [])

    def walk(i):
        out = []
        for child in nodes[i].get("children", []):
            out += walk(child)
        if nodes[i].get("mesh") is not None:
            out.append(nodes[i]["mesh"])
        return out

    entries = [m for n in doc["scenes"][doc.get("scene") or 0]["nodes"] for m in walk(n)]
    groups = []
    for i, m in enumerate(entries):
        for primitive in meshes[m]["primitives"]:
            draco = "KHR_draco_mesh_compression" in (primitive.get("extensions") or {})
            if not draco and primitive.get("mode", 4) not in (4, 5, 6):
                continue
            key = primitive.get("material") if group_by_material else (i, primitive.get("material"))
            if key not in groups:
                groups.append(key)
    return groups


def _gltf_shape(path, scale) -> tuple:
    """A glTF file's visual geometry as Genesis holds it, for the raster depth: its nodes' meshes (trimesh, node
    transforms applied), turned from Y-up to Z-up (mesh_utils.Y_UP_TRANSFORM: (x, y, z) -> (x, -z, y)), scaled."""
    import trimesh
    mesh = trimesh.load(str(path), force="mesh", process=False)
    v = np.asarray(mesh.vertices, dtype=np.float64)
    v = np.stack([v[:, 0], -v[:, 2], v[:, 1]], axis=1) * np.asarray(scale, dtype=np.float64)
    return ("mesh", v, np.asarray(mesh.faces, dtype=np.int64))


def _mesh_shape(path, scale) -> tuple:
    """A visual mesh file as ("mesh", vertices, faces) for the raster depth (scaled as the morph or URDF scales it)."""
    import trimesh
    mesh = trimesh.load(str(path), force="mesh", process=False)
    s = np.broadcast_to(np.asarray(scale, dtype=np.float64), (3,))
    return ("mesh", np.asarray(mesh.vertices, dtype=np.float64) * s, np.asarray(mesh.faces, dtype=np.int64))


# --------------------------------------------------------------------------------------------- the renderer
class NyxDirect:
    """gs-nyx driven from MuJoCo states: start, load the exported scene, allocate, then per frame the plugin's calls."""

    def __init__(self, scene: NyxScene, folder, *, device: int = 0, mj_model=None, camera_device: str = "cpu"):
        import gs_nyx.nyx_py_sdk as nps
        import gs_nyx.nyx_py_renderer as npr
        self.nps, self.npr = nps, npr
        self.scene = scene
        # Where the plugin's camera arithmetic runs: on the Genesis host's compute backend (Genesis makes it torch's
        # default device), for the exported and the per-frame poses of every camera. MuJoCo instances freeze
        # compute_backend "cpu"; a Genesis release instance on "cuda" computes them on the GPU.
        self.camera_device = camera_device
        nps.startup()
        self._sdk_started = True
        t0 = time.perf_counter()
        exported = scene.export(Path(folder), camera_device=camera_device)
        self.export_s = time.perf_counter() - t0
        self.scene_path = exported["path"]
        self.slots: list[Slot] = exported["slots"]
        self.references = exported["references"]
        self.deformables = exported["deformables"]
        self.cams: list[dict] = exported["cameras"]
        self.names = [c["name"] for c in self.cams]
        _preload_nvrtc()
        self.cuda = _Cuda(device)
        self.renderer = npr.NyxRenderer()
        params = npr.BridgeStartupParams()
        params.cudaDevice = int(device)
        params.renderMode = npr.ERenderMode.FastPathTracer
        params.debugView = npr.EDebugView.Meshlet
        params.maxViewportWidth = max(int(c["res"][0]) for c in self.cams)
        params.maxViewportHeight = max(int(c["res"][1]) for c in self.cams)
        params.openWindow = False
        self.renderer.startup(params)
        self.cuda.current()
        if not self.renderer.load_scene_from_file(str(self.scene_path)):
            raise RuntimeError(f"Nyx could not load {self.scene_path}")
        desc = npr.BridgeUpdateDesc()
        desc.numCameras = len(self.cams)
        desc.numRigidGeom = len(self.slots)
        n_dv = sum(d["n_vertices"] for d in self.deformables)
        n_dt = sum(d["n_triangles"] for d in self.deformables)
        desc.numDeformVertices, desc.numDeformTriangles, desc.numDeformObjects = n_dv, n_dt, len(self.deformables)
        desc.reference_resize(len(exported["references"]))
        for i, (uuid, node) in enumerate(exported["references"]):
            ref = desc.get_reference(i)
            ref.targetUUID = uuid
            ref.nodeName = node
            desc.set_reference(i, ref)
        if not self.renderer.allocate_scene_buffers(desc):
            raise RuntimeError("Nyx could not allocate the scene buffers")
        n, c = len(self.slots), len(self.cams)
        # One page-locked host block and one device block hold the four input arrays (one copy per frame); the
        # arrays the plugin keeps as separate float32 CUDA tensors are views at 256-byte aligned offsets.
        sizes = dict(cam_pos=c * 12, cam_quat=c * 16, geom_pos=n * 12, geom_quat=n * 16, deform_pos=n_dv * 12)
        offsets, total = {}, 0
        for key, size in sizes.items():
            offsets[key] = total
            total += -(-size // 256) * 256
        self._host_inputs = self.cuda.alloc_host(total)
        self._dev_inputs = self.cuda.alloc(total)
        view = lambda key, cols: self._host_inputs[offsets[key]:offsets[key] + sizes[key]].view(np.float32).reshape(-1, cols)
        self.cam_pos, self.cam_quat = view("cam_pos", 3), view("cam_quat", 4)
        self.geom_pos, self.geom_quat = view("geom_pos", 3), view("geom_quat", 4)
        self.deform_pos = view("deform_pos", 3)
        self._inputs_nbytes = total
        data = npr.BridgeUpdateData()
        data.numCameras = c
        data.camPosPtr, data.camRotPtr = self._dev_inputs + offsets["cam_pos"], self._dev_inputs + offsets["cam_quat"]
        data.numRigidGeom = n
        data.rigidGeomPosPtr = self._dev_inputs + offsets["geom_pos"]
        data.rigidGeomRotPtr = self._dev_inputs + offsets["geom_quat"]
        if self.deformables:
            # static deformable data, uploaded once (the plugin's _upload_static_deformable_data): UVs and the
            # triangle indices in the shared vertex space
            uvs = np.concatenate([d["entity"].uvs for d in self.deformables]).astype(np.float32)
            tri = np.concatenate([d["entity"].triangles.astype(np.int32) + d["v_start"] for d in self.deformables])
            self._dev_uvs, self._dev_tri = self.cuda.alloc(uvs.nbytes), self.cuda.alloc(tri.nbytes)
            self.cuda.upload(self._dev_uvs, uvs)
            self.cuda.upload(self._dev_tri, tri.reshape(-1))
            data.numDeformVertices, data.numDeformTriangles, data.numDeformObjects = n_dv, n_dt, len(self.deformables)
            data.deformVertexPosPtr = self._dev_inputs + offsets["deform_pos"]
            data.deformVertexUVsPtr, data.deformTriangleIndicesPtr = self._dev_uvs, self._dev_tri
            for d in self.deformables:
                self.deform_pos[d["v_start"]:d["v_start"] + d["n_vertices"]] = d["entity"].birth_vertices.astype(np.float32)
        self._skins: dict = {}
        self._data = data
        self._frame_shapes = [(int(cam["res"][1]), int(cam["res"][0]), 3) for cam in self.cams]
        self._frame_offsets = np.cumsum([0] + [int(np.prod(sh)) for sh in self._frame_shapes])
        self._dev_frames = self.cuda.alloc(int(self._frame_offsets[-1]))
        self._host_frames = self.cuda.alloc_host(int(self._frame_offsets[-1]))
        # static parts of the per-frame input
        self._body_ids = None
        self._mj_model = None
        self._slot_pos64 = np.zeros((n, 3))
        self._slot_quat64 = np.tile([1.0, 0.0, 0.0, 0.0], (n, 1))
        for i, s in enumerate(self.slots):
            if s.body is None:
                self._slot_pos64[i], self._slot_quat64[i] = s.static_pos, s.static_quat
                self.geom_pos[i] = _f32(s.static_pos)
                self.geom_quat[i] = _f32(s.static_quat)
        self._raster = None
        self.cam_T = np.zeros((len(self.cams), 4, 4))       # float64 camera-to-world (Z-up, looking along -z)
        for i, cam in enumerate(self.cams):
            if cam["attach"] is None:
                self.cam_pos[i], self.cam_quat[i] = camera_quat_f32(cam["pos"], cam["lookat"], cam["up"],
                                                                    device=camera_device)
                self.cam_T[i] = lookat_T(cam["pos"], cam["lookat"], cam["up"])
        self._frames: dict | None = None
        self.timing = dict(update_s=0.0, render_s=0.0, updates=0, renders=0)

    @classmethod
    def from_world(cls, world, folder=None, *, instance=None, **kwargs):
        """From a built MuJoCo world (MujocoWorld): its declarations, its model, its rope chains and its cloths. `instance` (its
        frozen instance.json) names today's render host as rcb_topogym._render_bridge chooses it: a rope instance
        renders on the released Genesis instance it was born from (instance_assets/render_host/), so the ropes' birth
        vertices are that instance's IPC settled state and the camera arithmetic runs on its compute backend. Every
        rope chain then drives its rope (bind_chain at the chain's birth, qpos0), as on the host."""
        import json
        import mujoco
        host, explicit_device = None, "camera_device" in kwargs
        if instance is not None:
            path = Path(instance).resolve()
            render_host = path.parent / "instance_assets" / "render_host" / "instance.json"
            host = render_host if render_host.is_file() else path
            if not explicit_device:
                backend = json.loads(host.read_text())["simulator"].get("compute_backend", "cpu")
                kwargs["camera_device"] = "cpu" if backend == "cpu" else "cuda"
        # A FEM setting whose cord is a MuJoCo chain (task parameter cord_model "chain": slotted_post_ring, orbits) is
        # drawn as the FEM setting, as render_bridge draws it: its declarations, the FEM cord skinned on the chain and its
        # free rigid parts carried by the MuJoCo bodies that hold them (chain_cord_host).
        cord = None if host is None else chain_cord_host(host)
        specs, carriers = world._specs, None
        if cord is not None:
            if not explicit_device:
                kwargs["camera_device"] = "cuda"      # the bridge's FEM host computes its cameras on CUDA (_chain_cord_host)
            birth = mujoco.MjData(world.model)
            mujoco.mj_kinematics(world.model, birth)      # qpos0: the authored pose, where the FEM scene is born
            specs = cord["specs"]
            carriers = {}
            for entity, body in cord["binding"]["bodies"].items():
                b = mujoco.mj_name2id(world.model, mujoco.mjtObj.mjOBJ_BODY, body)
                if b < 0:
                    raise KeyError(f"{entity}: carrier body {body!r} not in the MuJoCo model")
                carriers[entity] = (body, np.array(birth.xpos[b]), np.array(birth.xquat[b]))
        scene = NyxScene(world.env_cfg, world.robot_cfg, specs, manifest=world.manifest,
                         fem_birth=None if host is None else settled_fem_birth(host),
                         pbd_birth=None if host is None else frozen_pbd_birth(host), carriers=carriers)
        owned = folder is None
        folder = Path(folder) if folder is not None else Path("__nyx_cache__") / f"direct-{os.getpid()}-{id(world):x}"
        nyx = cls(scene, folder, mj_model=world.model, **kwargs)
        nyx._owned_folder = folder if owned else None
        if cord is not None:
            nyx._cord_assets = cord["assets"]                 # the FEM declarations' generated files, kept while rendering
            binding = cord["binding"]
            nyx.chain_cord_report = nyx.bind_chain(binding["entity"], world.model, birth, bodies=binding["chain"],
                                                   link_s=binding["link_s_m"])
        for name, rope in (getattr(world, "_ropes", None) or {}).items():
            birth = mujoco.MjData(world.model)
            mujoco.mj_kinematics(world.model, birth)
            # A rope born from a MuJoCo birth archive (no IPC settled state, so no frozen FEM birth here) has its chain
            # built at that birth (qpos0) while its volume spawns straight: the skin binds the chain's own birth
            # vertices (RopeChain.birth, which belong to qpos0), not the spawn (2026-10-14: the redesigned knot tiers
            # rendered their ropes straight, the skin bound to the spawn at the knotted qpos0)
            d = next((x for x in nyx.deformables if x["entity"].name == name), None)
            if d is not None and name not in scene.fem_birth and np.shape(rope.birth) == d["entity"].birth_vertices.shape:
                d["entity"].birth_vertices = np.asarray(rope.birth, dtype=np.float64)
                nyx.deform_pos[d["v_start"]:d["v_start"] + d["n_vertices"]] = d["entity"].birth_vertices.astype(np.float32)
            nyx.bind_chain(name, world.model, birth, bodies=[int(b) for b in rope.bodies], link_s=rope.s_nodes)
        for name, cloth in (getattr(world, "_cloths", None) or {}).items():
            nyx.bind_cloth(name, cloth)
        return nyx

    def _bind(self, mj_model):
        import mujoco
        ids = []
        for s in self.slots:
            if s.body is None:
                # a fixed entity's link whose MuJoCo body moves (not welded to the world: behind a joint) is drawn at
                # that body, as a free entity's link; every other fixed slot keeps its static pose
                b = -1 if s.carrier is None else mujoco.mj_name2id(mj_model, mujoco.mjtObj.mjOBJ_BODY, s.carrier)
                ids.append(b if b >= 0 and int(mj_model.body_weldid[b]) != 0 else -1)
                continue
            b = mujoco.mj_name2id(mj_model, mujoco.mjtObj.mjOBJ_BODY, s.body)
            if b < 0:
                raise KeyError(f"MuJoCo body {s.body!r} (visual geometry of {s.entity}) not in the model")
            ids.append(b)
        self._body_ids = np.array(ids)
        cams = []
        for cam in self.cams:
            if cam["attach"] is None:
                cams.append(-1)
                continue
            body = self.scene._body(cam["attach"]["entity"], cam["attach"]["link"])
            b = mujoco.mj_name2id(mj_model, mujoco.mjtObj.mjOBJ_BODY, body)
            if b < 0:
                raise KeyError(f"camera {cam['name']}: MuJoCo body {body!r} not in the model")
            cams.append(b)
        self._cam_bodies = cams
        self._mj_model = mj_model
        moving = self._body_ids >= 0
        self._moving = np.nonzero(moving)[0]
        self._local_pos = np.array([self.slots[i].local_pos for i in self._moving], dtype=np.float64)
        self._local_quat = np.array([self.slots[i].local_quat for i in self._moving], dtype=np.float64)

    def update(self, mj_model, mj_data) -> None:
        """Compute this state's per-frame input (visual-geometry and camera poses) on the host."""
        t = time.perf_counter()
        if self._mj_model is not mj_model:
            self._bind(mj_model)
        bodies = self._body_ids[self._moving]
        bpos = np.asarray(mj_data.xpos, dtype=np.float64)[bodies]
        bquat = np.asarray(mj_data.xquat, dtype=np.float64)[bodies]
        pos = bpos + quat_rotate(bquat, self._local_pos)
        quat = quat_mul(bquat, self._local_quat)
        self._slot_pos64[self._moving], self._slot_quat64[self._moving] = pos, quat
        self.geom_pos[self._moving] = pos.astype(np.float32)
        self.geom_quat[self._moving] = quat.astype(np.float32)
        attached, poses = [], []
        for i, b in enumerate(self._cam_bodies):
            if b < 0:
                continue
            T = np.eye(4)
            T[:3, :3] = quat_to_R(mj_data.xquat[b])
            T[:3, 3] = mj_data.xpos[b]
            C = T @ self.cams[i]["attach"]["offset_T"]
            self.cam_T[i] = C
            pos = C[:3, 3]
            attached.append(i)
            poses.append((pos, pos - C[:3, 2], C[:3, 1]))
        if attached:
            self.cam_pos[attached], self.cam_quat[attached] = camera_quats_f32(poses, device=self.camera_device)
        for name, (d, skin) in self._skins.items():
            self.deform_pos[d["v_start"]:d["v_start"] + d["n_vertices"]] = skin(mj_data).astype(np.float32)
        self._frames = None
        self.timing["update_s"] += time.perf_counter() - t
        self.timing["updates"] += 1

    def render(self, cameras=None) -> dict[str, np.ndarray]:
        """RGB (H, W, 3) uint8 per camera: one pass for the rig, the plugin's native call order."""
        if self._frames is None:
            t = time.perf_counter()
            self.cuda.current()
            self.renderer.update()
            self.cuda.upload(self._dev_inputs, self._host_inputs)
            self.renderer.update_scene_buffers(self._data)
            self.renderer.set_env_map(0)
            for i in range(len(self.names)):
                self.cuda.synchronize()               # as the plugin's torch.cuda.synchronize() before each frame
                ptr, shape = _dlpack_pointer(self.renderer.render_frame(i))
                if shape != self._frame_shapes[i]:
                    raise ValueError(f"camera {self.names[i]}: Nyx frame {shape}, expected {self._frame_shapes[i]}")
                self.cuda.copy_device(self._dev_frames + int(self._frame_offsets[i]), ptr, int(np.prod(shape)))
            self.cuda.synchronize()
            self.cuda.download(self._dev_frames, self._host_frames)
            self._frames = {name: self._host_frames[self._frame_offsets[i]:self._frame_offsets[i + 1]]
                            .reshape(self._frame_shapes[i]).copy() for i, name in enumerate(self.names)}
            self.timing["render_s"] += time.perf_counter() - t
            self.timing["renders"] += 1
        names = self.names if cameras is None else [cameras] if isinstance(cameras, str) else list(cameras)
        return {n: self._frames[n] for n in names}

    def bind_chain(self, entity: str, mj_model, mj_data, bodies=None, link_s=None) -> dict:
        """Let a MuJoCo body chain drive the FEM entity `entity`, as render_bridge.bind_chain does on the host:
        linear-blend skinning of its birth vertices (NyxScene: the instance's frozen birth, else the volume's spawn)
        by material arc length (render_bridge.ChainSkin). Bind once, with mj_data at birth."""
        from render_bridge import ChainSkin, MappingError, _chain_bodies
        d = next((x for x in self.deformables if x["entity"].name == entity), None)
        if d is None:
            raise KeyError(f"{entity} is not a deformable of this scene")
        e = d["entity"]
        ids = _chain_bodies(mj_model, entity, bodies)
        rest = np.asarray(e.birth_vertices, dtype=np.float64)
        material_s = np.asarray(e.material_coordinates[:, 0], dtype=np.float64)
        pos = np.asarray(mj_data.xpos, dtype=np.float64)[ids]
        rot = np.asarray(mj_data.xmat, dtype=np.float64)[ids].reshape(-1, 3, 3)
        if link_s is None:
            link_s = np.linspace(material_s.min(), material_s.max(), len(ids) + 1)
            joints = np.linalg.norm(np.diff(pos, axis=0), axis=1)
            if len(ids) > 1 and np.abs(joints - np.diff(link_s)[:-1]).max() > 0.05 * np.diff(link_s).max():
                raise MappingError(f"{entity}: chain links are not equal material spans; pass link_s")
        link_s = np.asarray(link_s, dtype=np.float64)
        if link_s.shape != (len(ids) + 1,) or np.any(np.diff(link_s) <= 0):
            raise MappingError(f"{entity}: link_s needs {len(ids) + 1} increasing values")
        skin = ChainSkin(ids, rest, material_s, link_s, pos, rot)
        self._skins[entity] = (d, lambda data, skin=skin: skin(data.xpos, data.xmat))
        error = np.linalg.norm(skin(mj_data.xpos, mj_data.xmat) - rest, axis=1).max()
        return dict(entity=entity, kind="fem chain skin", vertices=len(rest), links=len(ids), birth_max_error_m=float(error))

    def bind_cloth(self, entity: str, cloth) -> dict:
        """Let a MuJoCo cloth (topogym.world.mujoco.cloth.Cloth) drive the PBD cloth `entity`: its particles are the
        cloth's particle view of the flex (Cloth.particles_of(Cloth.vertices(data)): each particle a fixed barycentric
        combination of flex vertices, as the task, grasp and evaluation see them), and the visual vertices are Genesis'
        weighted sums of their supporting particles (pbd_visual_vertices)."""
        d = next((x for x in self.deformables if x["entity"].name == entity), None)
        if d is None or d["entity"].kind != "pbd":
            raise KeyError(f"{entity} is not a PBD cloth of this scene")
        e = d["entity"]
        if len(cloth.particle_rest) != len(e.birth_particles):
            raise ValueError(f"{entity}: the MuJoCo cloth has {len(cloth.particle_rest)} particles, the PBD state "
                             f"{len(e.birth_particles)}")
        view = lambda data, cloth=cloth, e=e: pbd_visual_vertices(cloth.particles_of(cloth.vertices(data)),  # noqa: E731
                                                                  e.support_idxs, e.support_weights)
        self._skins[entity] = (d, view)
        birth = cloth.particles_of(cloth.birth)
        e.birth_vertices = pbd_visual_vertices(birth, e.support_idxs, e.support_weights)
        self.deform_pos[d["v_start"]:d["v_start"] + d["n_vertices"]] = e.birth_vertices.astype(np.float32)
        return dict(entity=entity, kind="pbd particles: the cloth's particle view of its flex", particles=len(birth),
                    flex_vertices=len(cloth.birth),
                    birth_offset_from_frozen_pbd_m=float(np.linalg.norm(birth - e.birth_particles, axis=1).max()))

    def depth(self, cameras=None) -> dict[str, np.ndarray]:
        """z-depth (H, W) float32 m per camera from MuJoCo's raster of the same visual geometry (0 = none / beyond far)."""
        if self._raster is None:
            self._raster = RasterDepth(self.scene, self.slots, self.cams, [s.shape for s in self.slots],
                                       pixel_offset=GENESIS_DEPTH_SAMPLE, deformables=self.deformables)
        depth = self._raster.render(self._slot_pos64, self._slot_quat64, self.cam_T, self.deform_pos)
        names = self.names if cameras is None else [cameras] if isinstance(cameras, str) else list(cameras)
        return {n: depth[n] for n in names}

    def inputs(self) -> dict[str, np.ndarray]:
        """This frame's input buffers (as render_bridge.nyx_inputs reports the plugin's)."""
        out = dict(geom_pos=self.geom_pos.copy(), geom_quat=self.geom_quat.copy(), cam_pos=self.cam_pos.copy(),
                   cam_quat=self.cam_quat.copy())
        if self.deformables:
            out["deform_verts"] = self.deform_pos.copy()
        return out

    def close(self) -> None:
        if self._raster is not None:
            self._raster.close()
            self._raster = None
        if self.renderer is not None:
            self.renderer.unload_scene()
            self.renderer.shutdown()
            self.renderer = None
        if self.cuda is not None:
            self.cuda.close()
            self.cuda = None
        if getattr(self, "_sdk_started", False):
            self.nps.shutdown()
            self._sdk_started = False
        if getattr(self, "_owned_folder", None) is not None:
            import shutil
            shutil.rmtree(self._owned_folder, ignore_errors=True)
            self._owned_folder = None
        if getattr(self, "_cord_assets", None) is not None:
            self._cord_assets.cleanup()
            self._cord_assets = None


# --------------------------------------------------------------------------------------------- the Session's rig
class _DirectCamera:
    """A camera of DirectRig: the headless rig's calibration (res, fov, near, far, transform, the wrist mount's
    move_to_attach) and nyx_direct's frames, from one pass of the whole rig per state."""

    def __init__(self, rig, name: str, camera):
        self._rig, self._name, self._camera = rig, name, camera

    @property
    def _attached_link(self):
        return self._camera._attached_link

    def move_to_attach(self) -> None:
        self._camera.move_to_attach()

    def invalidate_frame(self) -> None:
        self._rig._rgb = None

    def render(self, rgb=True, depth=False, **_):
        return (self._rig.rgb()[self._name] if rgb else None, self._rig.depth()[self._name] if depth else None, None, None)

    def __getattr__(self, name):              # res, fov, near, far, transform
        if name.startswith("__"):
            raise AttributeError(name)
        return getattr(self._camera, name)


class DirectRig:
    """The Session's camera rig on nyx_direct (rcb_topogym, RCB_RENDER=direct): the interface of render_bridge's
    HeadlessRig (.world.cameras, update, close) whose cameras show Nyx frames instead of black ones. The headless rig of
    the same scene supplies the calibration the sensor path reads; NyxDirect renders the whole rig in one pass per state
    (as the plugin's shared pass) and draws depth with MuJoCo's raster. Neither touches the physics data: the headless
    rig's forward kinematics on its own MjData feed both."""

    def __init__(self, nyx: NyxDirect, headless):
        from types import SimpleNamespace
        if set(headless.world.cameras) != set(nyx.names):
            raise ValueError(f"camera rigs differ: {sorted(headless.world.cameras)} vs {sorted(nyx.names)}")
        self.nyx, self._headless = nyx, headless
        self.world = SimpleNamespace(cameras={name: _DirectCamera(self, name, camera)
                                              for name, camera in headless.world.cameras.items()})
        self._rgb = self._depth = None

    def update(self, mj_model, mj_data) -> None:
        import mujoco
        self._headless.update(mj_model, mj_data)
        data = self._headless.data
        if mj_model.nflex:
            mujoco.mj_flex(mj_model, data)
        self.nyx.update(mj_model, data)
        self._rgb = self._depth = None

    def rgb(self) -> dict[str, np.ndarray]:
        if self._rgb is None:
            self._rgb = self.nyx.render()
        return self._rgb

    def depth(self) -> dict[str, np.ndarray]:
        if self._depth is None:
            self._depth = self.nyx.depth()
        return self._depth

    def close(self) -> None:
        self.nyx.close()
        self._headless.close()


def rig(instance_path, world, headless) -> DirectRig:
    """The DirectRig of a built MuJoCo world: NyxDirect on its render host's route (from_world with the instance) and
    `headless`, render_bridge's headless rig of the same scene (rcb_topogym._render_bridge builds both)."""
    return DirectRig(NyxDirect.from_world(world, instance=instance_path), headless)


class RasterDepth:
    """Geometric z-depth (m along the optical axis) per camera: MuJoCo's OpenGL raster of the visual geometry Nyx
    renders (every rigid slot as a mocap body carrying its visual mesh or primitive, every deformable as a world mesh
    of its surface triangles whose vertices are re-uploaded each frame), the stand-in for Genesis' raster depth camera
    (Nyx has no depth output). Needs an OpenGL context (MUJOCO_GL=egl headless)."""

    def __init__(self, scene: NyxScene, slots, cams, meshes, *, pixel_offset=(0.0, 0.0), deformables=()):
        import mujoco
        self.cams = cams
        spec = mujoco.MjSpec()
        spec.compiler.degree = False
        width = max(int(c["res"][0]) for c in cams)
        height = max(int(c["res"][1]) for c in cams)
        spec.visual.global_.offwidth, spec.visual.global_.offheight = width, height
        spec.stat.extent = 1.0
        spec.visual.map.znear = min(float(c["near"]) for c in cams)
        spec.visual.map.zfar = max(float(c["far"]) for c in cams)
        for i, (slot, geom) in enumerate(zip(slots, meshes)):
            body = spec.worldbody.add_body(name=f"slot{i}", mocap=True)
            kind = geom[0]
            if kind == "mesh":
                vertices, faces = geom[1], geom[2]
                spec.add_mesh(name=f"mesh{i}", uservert=np.asarray(vertices, dtype=np.float64).reshape(-1).tolist(),
                              userface=np.asarray(faces, dtype=np.int64).reshape(-1).tolist(),
                              inertia=mujoco.mjtMeshInertia.mjMESH_INERTIA_SHELL)
                body.add_geom(type=mujoco.mjtGeom.mjGEOM_MESH, meshname=f"mesh{i}", contype=0, conaffinity=0)
            elif kind == "box":
                body.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=0.5 * np.asarray(geom[1], dtype=np.float64),
                              contype=0, conaffinity=0)
            elif kind == "plane":
                body.add_geom(type=mujoco.mjtGeom.mjGEOM_PLANE, size=[0.5 * geom[1][0], 0.5 * geom[1][1], 1.0],
                              contype=0, conaffinity=0)
            elif kind != "none":           # "none": a further reference of a geometry drawn by its first one
                raise NotImplementedError(kind)
        surfaces = []
        for k, d in enumerate(deformables):
            tri = np.asarray(d["entity"].triangles, dtype=np.int64)
            used = np.unique(tri)
            spec.add_mesh(name=f"deform{k}", uservert=np.asarray(d["entity"].birth_vertices)[used].reshape(-1).tolist(),
                          userface=np.searchsorted(used, tri).reshape(-1).tolist(),
                          inertia=mujoco.mjtMeshInertia.mjMESH_INERTIA_SHELL)
            spec.worldbody.add_geom(name=f"deform{k}", type=mujoco.mjtGeom.mjGEOM_MESH, meshname=f"deform{k}",
                                    contype=0, conaffinity=0)
            surfaces.append((d, used))
        for i, cam in enumerate(cams):
            body = spec.worldbody.add_body(name=f"camera{i}", mocap=True)
            camera = body.add_camera(name=f"cam{i}", fovy=float(cam["fov"]))
            if any(pixel_offset):
                # pinhole intrinsics in pixels (focal f = H / 2 / tan(fovy / 2)), the principal point moved by
                # pixel_offset: where a multisampled depth buffer's resolved sample sits inside the pixel
                w, h = int(cam["res"][0]), int(cam["res"][1])
                f = 0.5 * h / math.tan(math.radians(float(cam["fov"])) / 2)
                camera.resolution = [w, h]
                camera.sensor_size = [w * 1e-3, h * 1e-3]
                camera.focal_pixel = [f, f]
                camera.principal_pixel = [float(pixel_offset[0]), float(pixel_offset[1])]
        self.model = spec.compile()
        self.data = mujoco.MjData(self.model)
        self.n_slots = len(slots)
        mujoco.mj_kinematics(self.model, self.data)
        # MuJoCo moves a mesh's vertices into its inertial frame (the geom carries that frame), so a frame's world
        # vertices go in as geom_xmat^T (v - geom_xpos)
        self._surfaces = []
        for k, (d, used) in enumerate(surfaces):
            mesh = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_MESH, f"deform{k}")
            geom = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, f"deform{k}")
            adr, num = int(self.model.mesh_vertadr[mesh]), int(self.model.mesh_vertnum[mesh])
            p, R = self.data.geom_xpos[geom].copy(), self.data.geom_xmat[geom].reshape(3, 3).copy()
            back = self.model.mesh_vert[adr:adr + num].astype(np.float64) @ R.T + p
            if num != len(used) or np.abs(back - np.asarray(d["entity"].birth_vertices)[used]).max() > 1e-5:
                raise NotImplementedError(f"{d['entity'].name}: MuJoCo changed the deformable surface mesh")
            self._surfaces.append((mesh, adr, num, d["v_start"] + used, p, R))
        # mujoco.Renderer's depth path (its GL backend is fixed when mujoco is imported, by MUJOCO_GL), with the
        # context chosen here: EGL unless MUJOCO_GL names another.
        self._gl = _gl_context(width, height)
        self._gl.make_current()
        self._mjr = mujoco.MjrContext(self.model, mujoco.mjtFontScale.mjFONTSCALE_150.value)
        mujoco.mjr_setBuffer(mujoco.mjtFramebuffer.mjFB_OFFSCREEN.value, self._mjr)
        self._mjr.readDepthMap = mujoco.mjtDepthMap.mjDEPTH_ZEROFAR
        self._scene = mujoco.MjvScene(self.model, maxgeom=max(1000, 2 * self.model.ngeom))
        self._option = mujoco.MjvOption()
        self._camera = mujoco.MjvCamera()
        self._camera.type = mujoco.mjtCamera.mjCAMERA_FIXED

    def render(self, slot_pos, slot_quat, cam_T, deform_vertices=None) -> dict[str, np.ndarray]:
        import mujoco
        self._gl.make_current()
        for mesh, adr, num, rows, p, R in self._surfaces:
            self.model.mesh_vert[adr:adr + num] = (np.asarray(deform_vertices[rows], dtype=np.float64) - p) @ R
            mujoco.mjr_uploadMesh(self.model, self._mjr, mesh)
        self.data.mocap_pos[:self.n_slots] = slot_pos
        self.data.mocap_quat[:self.n_slots] = slot_quat
        for i, T in enumerate(cam_T):
            self.data.mocap_pos[self.n_slots + i] = T[:3, 3]
            q = np.empty(4)
            mujoco.mju_mat2Quat(q, np.ascontiguousarray(T[:3, :3]).reshape(-1))
            self.data.mocap_quat[self.n_slots + i] = q
        mujoco.mj_kinematics(self.model, self.data)
        mujoco.mj_camlight(self.model, self.data)
        extent = self.model.stat.extent
        znear = np.float32(self.model.vis.map.znear * extent)
        zfar = np.float32(self.model.vis.map.zfar * extent)
        c_coef = -(zfar + znear) / (zfar - znear)
        d_coef = -(np.float32(2) * zfar * znear) / (zfar - znear)
        c_coef = np.float32(-0.5) * c_coef - np.float32(0.5)          # reversed Z
        d_coef = np.float32(-0.5) * d_coef
        out = {}
        for i, cam in enumerate(self.cams):
            w, h = int(cam["res"][0]), int(cam["res"][1])
            self._camera.fixedcamid = i
            mujoco.mjv_updateScene(self.model, self.data, self._option, None, self._camera,
                                   mujoco.mjtCatBit.mjCAT_ALL.value, self._scene)
            self._scene.flags[mujoco.mjtRndFlag.mjRND_SEGMENT] = True
            self._scene.flags[mujoco.mjtRndFlag.mjRND_IDCOLOR] = True
            rect = mujoco.MjrRect(0, 0, w, h)
            mujoco.mjr_render(rect, self._scene, self._mjr)
            raw = np.empty((h, w), dtype=np.float32)
            mujoco.mjr_readPixels(None, raw, rect, self._mjr)
            depth = np.flipud((d_coef / (raw.astype(np.float64) + c_coef)).astype(np.float32)).copy()
            far = min(float(cam["far"]), 65.535)
            depth[~np.isfinite(depth) | (depth <= 0) | (depth >= np.float32(zfar) * (1 - 1e-6)) | (depth > far)] = 0
            out[cam["name"]] = depth
        return out

    def close(self):
        if self._mjr is not None:
            self._mjr.free()
            self._mjr = None
        if self._gl is not None:
            self._gl.free()
            self._gl = None


def _gl_context(width: int, height: int):
    """An offscreen OpenGL context for MuJoCo's renderer: EGL (headless GPUs) unless MUJOCO_GL asks otherwise."""
    gl = os.environ.get("MUJOCO_GL", "").lower().strip()
    if gl == "osmesa":
        from mujoco.osmesa import GLContext
    elif gl in ("glfw", "glx"):
        from mujoco.glfw import GLContext
    else:
        from mujoco.egl import GLContext
    return GLContext(width, height)


def _preload_nvrtc():
    """As the plugin does before creating the renderer: the NVRTC builtins library, globally, when installed."""
    try:
        from importlib.metadata import distribution
        dist = distribution("nvidia_cuda_nvrtc")
        for f in dist.files:
            if f.name.startswith("libnvrtc-builtins.so.1"):
                ctypes.CDLL(str(dist.locate_file(f)), ctypes.RTLD_GLOBAL)
                break
    except Exception:          # noqa: BLE001 -- optional, as in the plugin
        pass
