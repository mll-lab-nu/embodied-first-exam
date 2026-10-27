"""The services of the sidecar (registered on import; Newton is imported lazily inside each constructor).

``softbody.world``  VBD cloth sheet / sleeve and / or cable with kinematic colliders   (``worlds/softbody.py``)
    create: ``cfg`` = soft world config (``softbody_geom.spec.world_cfg``); arrays ``collider_q0`` ``(C, 7)`` and, for a cable,
    ``cable_points`` ``(S+1, 3)``.  Methods (``rpc_*``):
    * ``step``   arrays ``collider_q`` ``(C, 7)``; header ``frames`` (default 1) -> state arrays
    * ``reset``  optional arrays ``particle_q``, ``cable_points``, ``collider_q`` -> state arrays
    * ``state``  -> state arrays;  ``mesh`` -> ``triangles`` ``(T, 3)``, ``rest`` ``(P, 3)``, ``pinned`` (cloth)
    * ``anchor_particles`` / ``anchor_segments``  arrays ``ids``; header ``slot``;  ``release_particles`` / ``release_segments``
    State arrays: ``particle_q`` ``(P, 3)``, ``particle_qd`` (cloth); ``cable_nodes`` ``(S+1, 3)``, ``cable_seg_q`` ``(S, 7)``,
    ``cable_seg_qd`` ``(S, 6)`` (cable).

``mpm.dough``  implicit-MPM dough with kinematic tools  (``worlds/mpm.py``)
    create: ``cfg`` (dough world description + ``pvol``), array ``points`` ``(n, 3)``, optional ``poses`` ``(T, 7)``.
    ``step`` (array ``poses`` -> array ``q`` ``(n, 3)`` + header ``time`` / ``wrench`` / ``stats``), ``reset``, ``read``, ``stats``.

``fem.plugpad``  tetrahedral VBD plug pinched by the two gel pads  (``worlds/fem.py``)
    create: ``cfg`` = world cfg, array ``pads`` ``(2, 7)``; ``step`` array ``pads`` -> ``q`` ``(P, 3)``; ``reset``; ``mesh`` -> ``tris``; ``stats``.

``fem.plug``  the carrier variant: ``step`` array ``pose`` ``(7,)``; ``anchor`` / ``release``; ``reset``; ``mesh``; ``stats``.

All poses are ``x y z qx qy qz qw`` (xyzw), env-local metres.
"""

from __future__ import annotations

import time

import numpy as np

from .host import NewtonService, register_service


@register_service("softbody.world")
class SoftBodyService(NewtonService):
    def __init__(self, cfg, arrays):
        super().__init__(cfg, arrays)
        from .worlds.softbody import SoftWorld

        self.world = SoftWorld(cfg, arrays.get("collider_q0"), arrays.get("cable_points"))

    def describe(self):
        return self.world.describe()

    def close(self):
        self.world = None

    def rpc_step(self, h, a):
        t0 = time.perf_counter()
        self.world.step(a.get("collider_q"), int(h.get("frames", 1)))
        out = self.world.state()
        return {"seconds": time.perf_counter() - t0, "sim_time": self.world.sim_time}, out

    def rpc_reset(self, h, a):
        self.world.reset(a.get("particle_q"), a.get("cable_points"), a.get("collider_q"))
        return {}, self.world.state()

    def rpc_state(self, h, a):
        return {"sim_time": self.world.sim_time}, self.world.state()

    def rpc_mesh(self, h, a):
        w = self.world
        out = {}
        if w.has_cloth:
            out["triangles"] = np.asarray(w.cloth_tris, dtype=np.int32)
            out["rest"] = np.asarray(w.cloth_rest, dtype=np.float32)
            out["pinned"] = np.asarray(w.cloth_pinned, dtype=np.int32)
        return {}, out

    def rpc_anchor_particles(self, h, a):
        self.world.anchor_particles(a["ids"], int(h["slot"]))
        return {"anchored": len(a["ids"])}

    def rpc_release_particles(self, h, a):
        self.world.release_particles(a.get("ids"))
        return {}

    def rpc_anchor_segments(self, h, a):
        self.world.anchor_segments(a["ids"], int(h["slot"]))
        return {"anchored": len(a["ids"])}

    def rpc_release_segments(self, h, a):
        self.world.release_segments(a.get("ids"))
        return {}


@register_service("mpm.dough")
class DoughService(NewtonService):
    def __init__(self, cfg, arrays):
        super().__init__(cfg, arrays)
        from .worlds.mpm import DoughWorld

        self.world = DoughWorld(cfg, arrays["points"], float(cfg["pvol"]))
        if "poses" in arrays:
            self.world.reset(None, arrays["poses"])

    def describe(self):
        w = self.world
        return {"n": w.n, "tools": w.tool_names, "voxel": w.voxel, "dt": w.dt, "substeps": w.substeps, "pvol": w.pvol}

    def close(self):
        self.world = None

    def rpc_step(self, h, a):
        w = self.world
        for _ in range(int(h.get("repeat", 1))):
            w.step(a.get("poses"), h.get("substeps"))
        head = {"time": w.time}
        if h.get("wrench", True) and w.n_tools:
            head["wrench"] = [float(v) for v in w.tool_wrench(0)]
        if h.get("stats"):
            head["stats"] = w.stats()
        if h.get("check", False):
            w.check_grid()
        return head, ({"q": w.particles()} if h.get("return_q", True) else {})

    def rpc_reset(self, h, a):
        self.world.reset(a.get("points"), a.get("poses"))
        return {"time": 0.0}, {"q": self.world.particles()}

    def rpc_read(self, h, a):
        return {"time": self.world.time}, {"q": self.world.particles()}

    def rpc_stats(self, h, a):
        return self.world.stats()


@register_service("fem.plug")
class PlugService(NewtonService):
    def __init__(self, cfg, arrays):
        super().__init__(cfg, arrays)
        from .worlds.fem import PlugWorld

        self.world = PlugWorld(cfg)
        if "pose" in arrays:
            self.world.reset(arrays["pose"])

    def describe(self):
        w = self.world
        return {"n": w.n_nodes, "fps": w.fps, "substeps": w.substeps, "tris": int(len(w.tris)), "held": w.held}

    def close(self):
        self.world = None

    def rpc_step(self, h, a):
        w = self.world
        w.step(a.get("pose"), int(h.get("frames", 1)))
        return {"held": w.held}, {"q": w.particles()}

    def rpc_reset(self, h, a):
        self.world.reset(a.get("pose"))
        return {"held": self.world.held}, {"q": self.world.particles()}

    def rpc_anchor(self, h, a):
        return {"anchored": self.world.anchor()}

    def rpc_release(self, h, a):
        self.world.release()
        return {"held": self.world.held}

    def rpc_mesh(self, h, a):
        return {}, {"tris": self.world.tris.astype(np.int32)}

    def rpc_stats(self, h, a):
        return self.world.stats()


@register_service("fem.plugpad")
class PlugPadService(NewtonService):
    def __init__(self, cfg, arrays):
        super().__init__(cfg, arrays)
        from .worlds.fem import PlugPadWorld

        self.world = PlugPadWorld(cfg, np.asarray(arrays["pads"], np.float32).reshape(2, 7))

    def describe(self):
        w = self.world
        return {"n": w.n_nodes, "fps": w.fps, "substeps": w.substeps, "tris": int(len(w.tris))}

    def close(self):
        self.world = None

    def rpc_step(self, h, a):
        self.world.step(a.get("pads"), int(h.get("frames", 1)))
        return {}, {"q": self.world.particles()}

    def rpc_reset(self, h, a):
        self.world.reset(a.get("pads"))
        return {}, {"q": self.world.particles()}

    def rpc_mesh(self, h, a):
        return {}, {"tris": self.world.tris.astype(np.int32)}

    def rpc_stats(self, h, a):
        return self.world.stats()
