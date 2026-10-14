"""Same scene (renderer rule 2): a non-default renderer draws the default renderer's scene. The geometry, kinematics,
cameras and the colour a viewer sees of every untextured geom must be identical; a re-textured surface keeps its mean
colour within TEXTURE_TOL. Only lights, materials (specular, shininess, reflectance, textures with the same mean
colour) and image quality may differ. The same rule as scripts/olympiad/showcase/looks.same_scene, without the
sport-specific decor exception (decor is presentation-only and never part of a renderer's player picture).

Same kinematics (renderer rule 6): a presentation scene (renderers/presentation.py, spectators only) may differ from
the match scene in appearance and by added visual-only geoms, never in bodies, joints, frames, inertias or cameras;
same_kinematics() checks it before a renderer draws one, pose_diff() compares body poses over recorded states."""
from __future__ import annotations

import numpy as np

SAME = ("nq", "nv", "nbody", "njnt", "ngeom", "nmesh", "ncam", "nmocap",
        "body_parentid", "body_pos", "body_quat", "body_mass", "jnt_type", "jnt_qposadr", "jnt_pos", "jnt_axis",
        "geom_type", "geom_bodyid", "geom_size", "geom_pos", "geom_quat", "geom_group", "geom_dataid",
        "mesh_vertnum", "mesh_vert", "mesh_face",
        "cam_mode", "cam_bodyid", "cam_pos", "cam_quat", "cam_fovy")
DEFAULT_RGBA = (0.5, 0.5, 0.5, 1.0)
TEXTURE_TOL = 0.02
MESH = 7                   # mjtGeom.mjGEOM_MESH


def effective_rgba(m, g):
    rgba = m.geom_rgba[g]
    if m.geom_matid[g] >= 0 and np.allclose(rgba, DEFAULT_RGBA):
        return m.mat_rgba[m.geom_matid[g]]
    return rgba


def _texid(m, g):
    import mujoco as mj
    mid = m.geom_matid[g]
    return int(m.mat_texid[mid, mj.mjtTextureRole.mjTEXROLE_RGB]) if mid >= 0 else -1


def _mean_colour(m, g):
    """Mean drawn colour of a geom (texture mean x material/geom colour), 0..1 RGB."""
    rgba = np.asarray(effective_rgba(m, g)[:3], float)
    t = _texid(m, g)
    if t < 0:
        return rgba
    h, w, c = m.tex_height[t], m.tex_width[t], m.tex_nchannel[t]
    px = m.tex_data[m.tex_adr[t]:m.tex_adr[t] + h * w * c].reshape(-1, c)[:, :3]
    return rgba * (px.mean(0) / 255.0)


SPARE = "_ro_cam"          # the renderers' own spare cameras (renderers/mujoco), posed per frame: not scene cameras


def _scene_cams(m):
    return [i for i in range(m.ncam) if not (m.camera(i).name or "").startswith(SPARE)]


def same_scene(m0, m1) -> list:
    """Differences between the default model m0 and the renderer's model m1 (empty list = the same scene)."""
    bad = []
    c0, c1 = _scene_cams(m0), _scene_cams(m1)
    for name in SAME:
        a, b = np.asarray(getattr(m0, name)), np.asarray(getattr(m1, name))
        if name.startswith("cam_"):
            a, b = a[c0], b[c1]
        elif name == "ncam":
            a, b = np.asarray(len(c0)), np.asarray(len(c1))
        if np.shape(a) != np.shape(b) or not np.array_equal(a, b):
            bad.append(name)
    if bad:
        return bad
    if m0.vis.global_.fovy != m1.vis.global_.fovy:
        bad.append("vis.global.fovy")
    for g in range(m0.ngeom):
        t0, t1 = _texid(m0, g) >= 0, _texid(m1, g) >= 0
        if not t0 and not t1:
            if not np.allclose(effective_rgba(m0, g), effective_rgba(m1, g)):
                bad.append(f"colour of geom {m0.geom(g).name or g}")
        elif float(np.abs(_mean_colour(m0, g) - _mean_colour(m1, g)).max()) > TEXTURE_TOL:
            bad.append(f"mean colour of textured geom {m0.geom(g).name or g}")
    return bad


# ------------------------------------------------------------------------------------- presentation scenes (spectators)
VISUAL_PREFIX = "_vis:"    # the name prefix of a presentation scene's added geoms (renderers/presentation.py)
KINEMATICS = ("nq", "nv", "nu", "nbody", "njnt", "nmocap", "nsite", "qpos0",
              "body_parentid", "body_rootid", "body_weldid", "body_mocapid", "body_jntnum", "body_jntadr",
              "body_dofnum", "body_dofadr", "body_pos", "body_quat", "body_ipos", "body_iquat", "body_mass",
              "body_inertia", "jnt_type", "jnt_bodyid", "jnt_qposadr", "jnt_dofadr", "jnt_pos", "jnt_axis",
              "jnt_range", "dof_bodyid", "dof_jntid", "dof_armature", "dof_damping", "actuator_trnid",
              "site_bodyid", "site_pos", "site_quat", "opt.timestep", "opt.gravity")
MATCH_GEOM = ("geom_type", "geom_bodyid", "geom_size", "geom_pos", "geom_quat", "geom_contype", "geom_conaffinity",
              "geom_condim", "geom_priority", "geom_friction", "geom_solref", "geom_solimp", "geom_margin", "geom_gap")
CAMERA = ("cam_mode", "cam_bodyid", "cam_pos", "cam_quat", "cam_fovy")


def _arr(m, name):
    o = m
    for part in name.split("."):
        o = getattr(o, part)
    return np.asarray(o)


def visual_geoms(m) -> list:
    return [g for g in range(m.ngeom) if (m.geom(g).name or "").startswith(VISUAL_PREFIX)]


def _mesh_verts(m, g):
    i = m.geom_dataid[g]
    return m.mesh_vert[m.mesh_vertadr[i]:m.mesh_vertadr[i] + m.mesh_vertnum[i]]


def same_kinematics(m0, m1) -> list:
    """Differences between the match model m0 and a presentation model m1 (empty list = the same kinematics):
    every body, joint, dof, frame, inertia, site, mocap body and scene camera is identical; m0's geoms are all in m1,
    in the same order, with the same geometry, pose and contact properties (only their appearance may change:
    group, colour, material, e.g. a collision mesh moved to the hidden group 3); every other geom of m1 is an added
    visual geom (name prefix VISUAL_PREFIX) that never collides (contype = conaffinity = 0) and is drawn (group
    0..2). Body masses and inertias being equal, the added geoms carry no mass. So the same qpos puts every body at
    the same pose in both models: a presentation scene changes only what a spectator sees."""
    bad = []
    for name in KINEMATICS:
        a, b = _arr(m0, name), _arr(m1, name)
        if a.shape != b.shape or not np.array_equal(a, b):
            bad.append(name)
    c0, c1 = _scene_cams(m0), _scene_cams(m1)
    if len(c0) != len(c1):
        bad.append("ncam")
    else:
        bad += [n for n in CAMERA if not np.array_equal(_arr(m0, n)[c0], _arr(m1, n)[c1])]
    if bad:
        return bad
    extra = visual_geoms(m1)
    keep = [g for g in range(m1.ngeom) if g not in set(extra)]
    if len(keep) != m0.ngeom:
        return [f"{len(keep)} match geoms in the presentation scene for {m0.ngeom}"]
    bad += [n for n in MATCH_GEOM if not np.array_equal(_arr(m0, n), _arr(m1, n)[keep])]
    for g0, g1 in enumerate(keep):
        if (m0.geom(g0).name or "") != (m1.geom(g1).name or ""):
            bad.append(f"name of geom {g0}")
        elif m0.geom_dataid[g0] >= 0 and m0.geom_type[g0] == MESH and not np.array_equal(_mesh_verts(m0, g0),
                                                                                       _mesh_verts(m1, g1)):
            bad.append(f"mesh of geom {m0.geom(g0).name or g0}")
    for g in extra:
        if m1.geom_contype[g] or m1.geom_conaffinity[g] or not 0 <= m1.geom_group[g] <= 2:
            bad.append(f"added geom {m1.geom(g).name} collides or is not drawn")
    return bad


def pose_diff(m0, m1, states) -> float:
    """The largest difference of any body's (and site's) world position or orientation between the two models over
    the given states ({"qpos", optional "mocap_pos", "mocap_quat"}); 0.0 = bit-identical poses."""
    import mujoco as mj
    d0, d1 = mj.MjData(m0), mj.MjData(m1)
    worst = 0.0
    for st in states:
        for m, d in ((m0, d0), (m1, d1)):
            d.qpos[:] = np.asarray(st["qpos"], float)
            if m.nmocap and "mocap_pos" in st:
                d.mocap_pos[:] = np.asarray(st["mocap_pos"], float).reshape(m.nmocap, 3)
            if m.nmocap and "mocap_quat" in st:
                d.mocap_quat[:] = np.asarray(st["mocap_quat"], float).reshape(m.nmocap, 4)
            mj.mj_kinematics(m, d)
        for a, b in ((d0.xpos, d1.xpos), (d0.xquat, d1.xquat), (d0.xmat, d1.xmat), (d0.site_xpos, d1.site_xpos)):
            if np.asarray(a).size:
                worst = max(worst, float(np.abs(np.asarray(a) - np.asarray(b)).max()))
    return worst
