"""Explicit diagnostic scenarios, distinct from the default-scene recordings."""
from dataclasses import replace
import numpy as np


def lifted_ring_class(task_class):
    class LiftedRing(task_class):
        def declare(self, *args, **kwargs):
            spec = super().declare(*args, **kwargs)
            return replace(spec, entities=tuple(
                replace(e, position_m=tuple(np.asarray(e.position_m)+[0, 0, .35]))
                if e.name == "target_ring" else e for e in spec.entities))
    return LiftedRing


def ring_sample(env, time):
    body = env.privileged.get("world")["bodies"]["target_ring"]
    return dict(time_s=float(time), z_m=float(body["position_m"][2]),
                vz_m_s=float(body["linear_velocity_m_s"][2]))


def check_gravity(samples):
    first, last = samples[0], samples[-1]
    elapsed = last["time_s"]-first["time_s"]
    acceleration = (last["vz_m_s"]-first["vz_m_s"])/elapsed
    drop = first["z_m"]-last["z_m"]
    assert abs(acceleration+9.81) < .15, acceleration
    assert abs(drop-.5*9.81*elapsed**2) < .003, drop
    return dict(acceleration_m_s2=acceleration, drop_m=drop, samples=samples,
                scope="target ring lifted 0.35 m at declaration only; no runtime pose writes")


def terminal_wand_class(task_class):
    """Separate endpoint diagnostic; it makes no mid-route traversal claim."""
    class TerminalWand(task_class):
        def declare(self, *args, **kwargs):
            from topogym.assets.geometry.buzz_wire_3d import endpoint_pose
            spec = super().declare(*args, **kwargs)
            position, rotation = endpoint_pose(self.route, 1)
            return replace(spec, entities=tuple(
                replace(e, position_m=tuple(self.origin+position),
                        quaternion_wxyz=tuple(rotation.as_quat()[[3,0,1,2]]))
                if e.name == "wand" else e for e in spec.entities))
    return TerminalWand
