"""Operator-only CPU runtime evidence; container isolation is checked separately."""

import glob
import os


def gpu_devices():
    return sorted({path for pattern in ("/dev/nvidia*", "/dev/dri/*", "/dev/kfd") for path in glob.glob(pattern)})


def inspect_runtime(render=False):
    devices = gpu_devices()
    strict = os.environ.get("ROBOENGINEER_ENFORCE_CPU_ISOLATION") == "1"
    if strict and devices:
        raise RuntimeError("GPU device exposed to CPU evaluator")
    if os.environ.get("MUJOCO_GL") != "osmesa":
        raise RuntimeError("CPU evaluator requires OSMesa")
    if os.environ.get("CUDA_VISIBLE_DEVICES") not in ("", "-1"):
        raise RuntimeError("CUDA must be disabled in the evaluator")
    import mujoco

    result = {
        "schema": "roboengineer-cpu-runtime/1",
        "physics": "mujoco-cpu",
        "mujoco_version": mujoco.__version__,
        "policy_inference": "numpy-cpu",
        "render_backend": "osmesa",
        "gpu_devices": devices,
        "device_isolation_required": strict,
        "device_isolation_verified": strict and not devices,
        "software_renderer_verified": False,
        "renderer": None,
    }
    if render:
        from OpenGL import GL

        context = mujoco.GLContext(32, 32)
        try:
            context.make_current()
            raw = GL.glGetString(GL.GL_RENDERER)
            renderer = raw.decode("utf-8", errors="replace") if raw else ""
            software = any(value in renderer.lower() for value in ("llvmpipe", "softpipe", "software", "swrast"))
            if not software:
                raise RuntimeError("OSMesa software renderer could not be verified")
            result.update(renderer=renderer, software_renderer_verified=True)
        finally:
            context.free()
    return result
