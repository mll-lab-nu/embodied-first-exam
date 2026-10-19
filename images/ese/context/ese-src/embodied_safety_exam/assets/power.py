"""Visible mains connections; an audit, not an electrical circuit simulator."""
from __future__ import annotations

import copy
import functools
import json
import math

import numpy as np


@functools.lru_cache(maxsize=32)
def _socket_face(kind, params, socket):
    from .catalog import build_files
    _, meta = build_files(kind, json.loads(params))
    zone = meta["zones"][socket]
    point = np.asarray(meta["sites"][zone["site"]], dtype=float).copy()
    point[2] -= float(zone["size"][-1]) / 2.0
    return tuple(point)


def connect_supply(scene, appliance, supply, socket="socket_0"):
    """Draw a static cord seated in an existing socket, without moving solids.

    The socket's own native metadata supplies the terminal position. This does
    not add a graspable plug, insertion task, or power-state propagation.
    """
    from embodied_safety_exam.sim import tf

    scene = copy.deepcopy(scene)
    objects = {obj["name"]: obj for obj in scene["objects"]}
    load, source = objects[appliance], objects[supply]
    if (load.get("params") or {}).get("toy"):
        return scene
    point = _socket_face(source["kind"], json.dumps(source.get("params") or {}, sort_keys=True), socket)
    lp, lq = tf.as_pose(load)
    sp, sq = tf.as_pose(source)
    lr, sr = tf.quat_to_mat(lq), tf.quat_to_mat(sq)
    end = lr.T @ (sp + sr @ point - lp)
    relative = lr.T @ sr
    load["params"] = {**(load.get("params") or {}), "cord": "socket",
                      "cord_terminal": (end * 1000).tolist(),
                      "cord_yaw": math.degrees(math.atan2(relative[1, 0], relative[0, 0]))}
    return scene


def audit_power_visuals(world, state):
    """Report contradictory visible connections or indicators of active devices.

    A missing visible cord is unspecified, not evidence of disconnection. An
    explicit loose plug cannot accompany `on`/`running`. A socket terminal must
    meet an actual socket face. Indicator colours must match the device state;
    intentionally non-glowing heating elements remain valid.
    """
    issues = []
    sockets = []
    for name, obj in world.objects.items():
        for zone in obj["meta"].get("zones", {}):
            if zone.startswith("socket"):
                point = _socket_face(obj["kind"], json.dumps(obj["meta"].get("params") or {}, sort_keys=True), zone)
                pos, quat = world.locate(name)
                from embodied_safety_exam.sim import tf
                sockets.append(pos + tf.quat_to_mat(quat) @ point)
    for name, device in state.devices.items():
        active = any(device.state.get(key) is True for key in ("on", "running"))
        connection = world.objects[device.obj]["meta"].get("power_connection")
        if active and connection:
            kind = connection["kind"]
            if kind == "loose":
                issues.append({"device": name, "issue": "active_with_loose_plug"})
            elif kind == "socket":
                from embodied_safety_exam.sim import tf
                pos, quat = world.locate(device.obj)
                point = pos + tf.quat_to_mat(quat) @ np.asarray(connection["terminal"])
                if not sockets or min(np.linalg.norm(point - target) for target in sockets) > 0.002:
                    issues.append({"device": name, "issue": "active_plug_not_seated_in_socket"})
        for key, value in device.state.items():
            for geom, rgba in device.looks.get(f"{key}={value}", {}).items():
                full = geom if "/" in geom else f"{device.obj}/{geom}"
                if not np.allclose(world.model.geom(full).rgba, rgba, rtol=0, atol=1e-6):
                    issues.append({"device": name, "issue": "indicator_disagrees_with_state", "geom": full})
    return issues
