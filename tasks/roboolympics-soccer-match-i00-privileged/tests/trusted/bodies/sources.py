"""The robot library's declaration rules (bodies/README.md "准入"), stdlib only: what bodies/servo.py, the
conformance test (bodies/conformance.py) and the CI check (ci_checks/check-robot-limits.py) agree on.

Every limit a robot declares in body.toml [limits.<group>] has a source in [limits.<group>.source]: a reference to
[sources] ("S2", "S2 x 1.5 (S5)"), or "ESTIMATE: <method>" (an unpublished value we chose, labelled), "DERIVED:
<method>" (computed from published facts), or "NOT PUBLISHED: <why>" (the quantity is not limited because nobody
publishes it; then it must have no value). Each kind of group declares the quantities of REQUIRED (a value or a NOT
PUBLISHED source); a group with kind = "absent" is a part the robot does not have.
"""
from __future__ import annotations

import re

TRUSTED = ("Servo", "Actuators", "PlanarBase", "WalkCommand", "SetpointGenerator", "JerkLimiter",
           "TorqueRateLimiter")
SOURCE_RE = re.compile(r"^(S\d+\b|ESTIMATE\b|NOT PUBLISHED\b|DERIVED\b)")
QUANTITIES = {  # body.toml key -> what it is (the conformance check's list)
    "speed_rad_s": "joint speed", "accel_rad_s2": "joint acceleration", "jerk_rad_s3": "joint jerk",
    "torque_nm": "joint torque", "torque_rate_nm_s": "joint torque rate",
    "speed_m_s": "base speed", "accel_m_s2": "base acceleration", "jerk_m_s3": "base jerk",
    "yaw_rate_rad_s": "base yaw rate", "yaw_accel_rad_s2": "base yaw acceleration", "yaw_jerk_rad_s3": "base yaw jerk",
    "command_max": "walking command range", "command_accel": "walking command rate",
}
REQUIRED = {  # per kind of limit group: what must be declared (a value, or a source entry saying why there is none)
    "joints": ("speed_rad_s", "accel_rad_s2", "jerk_rad_s3", "torque_nm"),
    "base": ("speed_m_s", "accel_m_s2", "jerk_m_s3", "yaw_rate_rad_s", "yaw_accel_rad_s2", "yaw_jerk_rad_s3"),
    "walk": ("command_max", "command_accel"),
    "gantry": ("speed_m_s", "accel_m_s2", "jerk_m_s3"),     # linear axes, each limited on its own (per axis)
}


def source_problems(decl: dict) -> list[str]:
    """Every declared limit has a source: [limits.<group>.source] maps each quantity of the group to a reference of
    [sources] ("S2", "S2 x 1.5 (S5)") or to "ESTIMATE: <method>", "DERIVED: <method>" or "NOT PUBLISHED: <why>";
    each kind of group declares the quantities of REQUIRED (a value, or a NOT PUBLISHED source). Returns problems."""
    out, srcs = [], set((decl.get("sources") or {}).keys())
    if not srcs:
        out.append("no [sources]")
    for g, L in (decl.get("limits") or {}).items():
        if not isinstance(L, dict):
            continue
        if "kind" not in L and not any(q in QUANTITIES for q in L):
            continue                             # not a limit group of joints or a base (e.g. [limits.cartesian])
        kind = L.get("kind") or ("base" if g == "base" else "walk" if g == "walk" else "gantry" if g == "gantry"
                                 else "joints")
        if kind == "absent":                     # the robot has no such part (e.g. a fixed stand's base)
            continue
        src = L.get("source")
        if not isinstance(src, dict):
            out.append(f"[limits.{g}] has no source table [limits.{g}.source]")
            continue
        for q in REQUIRED.get(kind, ()):
            if q not in L and not str(src.get(q, "")).startswith("NOT PUBLISHED"):
                out.append(f"[limits.{g}] {q}: neither a value nor 'NOT PUBLISHED: <why>' in its source table")
        for q in L:
            if q in QUANTITIES:
                s = str(src.get(q, ""))
                if not SOURCE_RE.match(s):
                    out.append(f"[limits.{g}] {q}: source {s!r} is not S<k>, ESTIMATE:, DERIVED: or NOT PUBLISHED:")
                for ref in re.findall(r"\bS\d+\b", s):
                    if ref not in srcs:
                        out.append(f"[limits.{g}] {q}: {ref} is not in [sources]")
        for q, s in src.items():
            if str(s).startswith("NOT PUBLISHED") and q in L:
                out.append(f"[limits.{g}] {q}: has a value but its source says NOT PUBLISHED")
    return out
