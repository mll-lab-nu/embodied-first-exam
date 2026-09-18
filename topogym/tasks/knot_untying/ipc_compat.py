"""Task-scoped joint-axis adapter for Genesis 1.2.1 and pyuipc 0.0.25.

Genesis reverses revolute-joint edge vertices when declaring IPC joints.
The installed libuipc uses the edge's right-hand-rule axis. Without this
adapter, a positive Genesis angle drives the native collision body in the
opposite direction; the rendered robot and physical collision body diverge.
"""
from contextlib import contextmanager
from importlib.metadata import version


@contextmanager
def matching_revolute_axes():
    import uipc
    from genesis.engine.couplers.ipc_coupler import coupler as module
    if (version('genesis-world'), version('pyuipc')) != ('1.2.1', '0.0.25'):
        raise RuntimeError('External-articulation axis adapter requires a new audit for these backend versions')
    original = module.AffineBodyRevoluteJoint

    class ForwardAxisRevoluteJoint:
        def apply_to(self, geometry, *args, **kwargs):
            vertices = uipc.view(geometry.positions())
            vertices[:] = vertices[::-1].copy()
            return original().apply_to(geometry, *args, **kwargs)

    # Only declaration uses this constructor. Restore it before simulation;
    # no runtime poses, joint coordinates or collision states are overwritten.
    module.AffineBodyRevoluteJoint = ForwardAxisRevoluteJoint
    try:
        yield
    finally:
        module.AffineBodyRevoluteJoint = original
