"""Scene description -> MuJoCo model, plus the weld / gripper helpers the viewer uses.

Visual meshes are drawn in group 2 and never collide; collision geoms sit in the
hidden group 3 (tick it in the browser's Visibility Groups to inspect them).
Concave collision pieces are split with CoACD (cached). Every free body gets two
inactive welds: pin_<body> (to the world) and, with the gripper, grip_<body>.

python -m scripts.design_viewer.mjcf --scene hedgehog_in_cage_medium --gripper --seconds 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import pickle
import time

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from scripts.design_viewer import scenes

# Contact bits: a pair collides when one geom's contype meets the other's conaffinity.
STATIC, OBJECT, GRIPPER, HELD = 1, 2, 4, 8
GRIPPER_XML = scenes.ROOT/"assets"/"robots"/"robotiq_2f85"/"2f85.xml"
STANDOFF = .15  # pinch point to target at placement; keeps the fingers outside a 90 mm cage
WRIST_DAMPING = 8., .03  # translation N s/m, rotation N m s/rad: stops ~0.1 s after the mouse lets go


def build(scene, gripper=False):
    spec = mujoco.MjSpec.from_string(_base_xml(scene, gripper))
    for b in scene.bodies:
        body = spec.worldbody.add_body(name=b.name, pos=b.pos, quat=b.quat)
        if b.free:
            body.add_freejoint(name=f"{b.name}_free")
        spec.add_mesh(name=f"{b.name}_visual", uservert=b.visual.vertices.ravel(), userface=b.visual.faces.ravel(),
                      inertia=mujoco.mjtMeshInertia.mjMESH_INERTIA_SHELL)
        body.add_geom(type=mujoco.mjtGeom.mjGEOM_MESH, meshname=f"{b.name}_visual", rgba=b.rgba, group=2,
                      contype=0, conaffinity=0, mass=0)
        contype, conaffinity = (OBJECT, STATIC | OBJECT | GRIPPER) if b.free else (STATIC, OBJECT | GRIPPER)
        common = dict(contype=contype, conaffinity=conaffinity, group=3, density=b.density, rgba=(*b.rgba[:3], .5))
        for i, item in enumerate(_convex(b.collision)):
            if isinstance(item, trimesh.Trimesh):
                spec.add_mesh(name=f"{b.name}_c{i}", uservert=item.vertices.ravel(), userface=item.faces.ravel())
                body.add_geom(type=mujoco.mjtGeom.mjGEOM_MESH, meshname=f"{b.name}_c{i}", **common)
            else:
                _, p, q, r = item
                body.add_geom(type=mujoco.mjtGeom.mjGEOM_CAPSULE, fromto=[*p, *q], size=[r, 0, 0], **common)
    if gripper:
        wrist = spec.worldbody.add_body(name="wrist", gravcomp=1)
        wrist.add_freejoint(name="wrist_free")
        wrist.add_geom(type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[.005, 0, 0], contype=0, conaffinity=0, mass=.05, group=3)
        wrist.add_frame().attach_body(mujoco.MjSpec.from_file(str(GRIPPER_XML)).worldbody.first_body(), "g_", "")
        for body in spec.bodies:
            if body.name.startswith("g_"):
                body.gravcomp = 1
    for b in scene.bodies:
        for how, other in (("pin", "world"), ("grip", "wrist"))[:2 if gripper else 1]:
            if b.free:
                # MjSpec's default weld data is all zeros (torquescale 0 = no weld); set it explicitly.
                spec.add_equality(type=mujoco.mjtEq.mjEQ_WELD, name=f"{how}_{b.name}", name1=other, name2=b.name,
                                  objtype=mujoco.mjtObj.mjOBJ_BODY, active=False, solref=[.02, 1],
                                  data=[0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1])
    model = spec.compile()
    if gripper:
        g = np.array([model.body(i).name.startswith("g_") for i in model.geom_bodyid])
        solid = g & ((model.geom_contype | model.geom_conaffinity) > 0)
        model.geom_contype[solid], model.geom_conaffinity[solid] = GRIPPER, STATIC | OBJECT
        adr = model.joint("wrist_free").dofadr[0]
        model.dof_damping[adr:adr+3], model.dof_damping[adr+3:adr+6] = WRIST_DAMPING
        data = mujoco.MjData(model)
        place_gripper(model, data, grip_target(scene))
        qadr = model.joint("wrist_free").qposadr[0]
        model.qpos0[qadr:qadr+7] = data.qpos[qadr:qadr+7]  # Reset returns here
    return model


def _base_xml(scene, gripper):
    cable, equality = "", ""
    if "cord" in scene.extras:
        cable, equality = _cable(scene)
    option = (f'timestep="{scene.extras.get("timestep", .002)}" integrator="implicitfast" '
              f'cone="{"pyramidal" if cable else "elliptic"}"' + (' impratio="10"' if gripper else ""))
    return f"""<mujoco model="{scene.name}">
  <option {option}/>
  <statistic center="0 0 .1" extent=".5"/>
  {'<extension><plugin plugin="mujoco.elasticity.cable"/></extension>' if cable else ''}
  <default><geom friction=".3" condim="3" solref=".004 1"/></default>
  <worldbody>
    <light pos="0 0 1.5" dir="0 0 -1" directional="true"/>
    <geom name="floor" type="plane" size=".6 .6 .01" rgba=".82 .82 .8 1" contype="{STATIC}" conaffinity="{OBJECT | GRIPPER}"/>
    {cable}
  </worldbody>
  {equality}
</mujoco>"""


def _cable(scene, n=64):
    """MuJoCo cable for the slotted cord; both ends tied to the discs (Genesis: permanent attachment)."""
    cord, radius = scene.extras["cord"], scene.extras["layout"].rope_radius_m
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(cord, axis=0), axis=1))]
    s = np.linspace(0, arc[-1], n)
    vertices = np.column_stack([np.interp(s, arc, cord[:, i]) for i in range(3)])
    cable = f"""<composite prefix="cord" type="cable" vertex="{' '.join(map(str, vertices.ravel()))}" initial="free">
      <plugin plugin="mujoco.elasticity.cable">
        <config key="twist" value="1e6"/><config key="bend" value="2e5"/><config key="vmax" value="0"/>
      </plugin>
      <joint kind="main" damping=".002"/>
      <geom type="capsule" size="{radius}" density="1100" rgba=".9 .88 .8 1" contype="{OBJECT}" conaffinity="{STATIC | OBJECT | GRIPPER}"/>
    </composite>"""
    equality = """<equality>
    <connect body1="cordB_first" body2="disc_left" anchor="0 0 0"/>
    <connect body1="cordB_last" body2="disc_right" anchor="0 0 0"/>
  </equality>"""
    return cable, equality


def _convex(items, threshold=.02):
    out = []
    for item in items:
        if isinstance(item, trimesh.Trimesh) and not item.is_convex and item.convex_hull.volume > 1.01*abs(item.volume):
            out += _coacd(item, threshold)
        else:
            out.append(item)
    return out


def _coacd(mesh, threshold):
    key = hashlib.sha256(np.ascontiguousarray(mesh.vertices).tobytes()+np.ascontiguousarray(mesh.faces).tobytes()
                         + str(threshold).encode()).hexdigest()[:16]
    path = scenes.RUNS/"coacd"/f"{key}.pkl"
    if not path.exists():
        import coacd
        coacd.set_log_level("error")
        parts = coacd.run_coacd(coacd.Mesh(mesh.vertices, mesh.faces), threshold=threshold)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps([trimesh.Trimesh(v, f) for v, f in parts]))
    return pickle.loads(path.read_bytes())


def grip_target(scene):
    return next(b.pos for b in scene.bodies if b.name in ("ball", "target_ring"))


def place_gripper(model, data, target, azimuth_deg=0., standoff=STANDOFF):
    """Horizontal approach: fingers point at `target`, pinch point `standoff` away along the azimuth."""
    a = np.radians(azimuth_deg)
    rotation = Rotation.from_euler("z", azimuth_deg, degrees=True)*Rotation.from_euler("y", -90, degrees=True)
    q, v = model.joint("wrist_free").qposadr[0], model.joint("wrist_free").dofadr[0]
    data.qpos[q:q+3], data.qpos[q+3:q+7] = 0, rotation.as_quat()[[3, 0, 1, 2]]
    mujoco.mj_kinematics(model, data)
    pinch = data.site("g_pinch").xpos-data.xpos[model.body("wrist").id]
    data.qpos[q:q+3] = np.asarray(target)+standoff*np.array([np.cos(a), np.sin(a), 0])-pinch
    data.qvel[v:v+6] = 0
    mujoco.mj_forward(model, data)


def _set_weld(model, data, name, on):
    eq = model.equality(name).id
    if on:
        b1, b2 = model.eq_obj1id[eq], model.eq_obj2id[eq]
        r1 = Rotation.from_quat(data.xquat[b1][[1, 2, 3, 0]])
        relpos = r1.inv().apply(data.xpos[b2]-data.xpos[b1])
        relquat = (r1.inv()*Rotation.from_quat(data.xquat[b2][[1, 2, 3, 0]])).as_quat()[[3, 0, 1, 2]]
        model.eq_data[eq, :11] = [0, 0, 0, *relpos, *relquat, 1]
    data.eq_active[eq] = on


def hold(model, data, body, how):
    """how='pin': weld to the world where it is now; how='grip': weld to the wrist, fingers stop colliding with it."""
    _set_weld(model, data, f"{how}_{body}", True)
    if how == "grip":
        b = model.body(body).id
        geoms = (model.geom_bodyid == b) & (model.geom_contype > 0)
        model.geom_contype[geoms], model.geom_conaffinity[geoms] = HELD, STATIC | OBJECT
        model.body_gravcomp[b] = 1


def release(model, data, body=None):
    for eq in range(model.neq):
        name = model.equality(eq).name
        if name.startswith(("pin_", "grip_")) and (body is None or name.split("_", 1)[1] == body):
            data.eq_active[eq] = 0
            b = model.eq_obj2id[eq]
            held = (model.geom_bodyid == b) & (model.geom_contype == HELD)
            model.geom_contype[held], model.geom_conaffinity[held] = OBJECT, STATIC | OBJECT | GRIPPER
            model.body_gravcomp[b] = 0


def holds(model, data):
    return [model.equality(eq).name for eq in range(model.neq) if data.eq_active[eq]
            and model.equality(eq).name.startswith(("pin_", "grip_"))]


def has_gripper(model):
    return mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "wrist") >= 0


def save_pose(path, scene, gripper, model, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(scene=scene.name, overrides=scene.extras.get("overrides", {}), gripper=gripper,
                                    qpos=data.qpos.tolist(), ctrl=data.ctrl.tolist(), holds=holds(model, data)))+"\n")


def load_pose(path):
    """Rebuild the saved scene and restore qpos, controls and holds; returns (scene, model, data)."""
    pose = json.loads(Path(path).read_text())
    scene = scenes.build(pose["scene"], pose["overrides"])
    model = build(scene, pose["gripper"])
    data = mujoco.MjData(model)
    apply_pose(model, data, pose)
    return scene, model, data


def apply_pose(model, data, pose):
    release(model, data)
    data.qpos[:], data.qvel[:], data.ctrl[:] = pose["qpos"], 0, pose["ctrl"]
    mujoco.mj_forward(model, data)
    for name in pose["holds"]:
        how, body = name.split("_", 1)
        hold(model, data, body, how)


def penetration(model, data):
    return float(max(0., -data.contact.dist[:data.ncon].min(initial=0.)))


def cord_points(model, data):
    ids = [i for i in range(model.nbody) if model.body(i).name.startswith("cordB")]
    return data.xpos[ids].copy()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scene", nargs="*", default=None, help="default: every registered scene")
    parser.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE")
    parser.add_argument("--gripper", action="store_true")
    parser.add_argument("--seconds", type=float, default=1.)
    args = parser.parse_args()
    for name in args.scene or scenes.list_scenes():
        scene = scenes.build(name, scenes.parse_sets(args.set))
        start = time.perf_counter()
        model = build(scene, args.gripper)
        compiled = time.perf_counter()-start
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        initial, xpos = penetration(model, data), data.xpos.copy()
        steps = int(args.seconds/model.opt.timestep)
        start = time.perf_counter()
        for _ in range(steps):
            mujoco.mj_step(model, data)
        wall = time.perf_counter()-start
        drift = np.linalg.norm(data.xpos-xpos, axis=1).max()
        print(f"{name:34s} compile {compiled:4.1f} s, ngeom {model.ngeom:4d}, {wall/steps*1e3:.3f} ms/step "
              f"({steps*model.opt.timestep/wall:5.1f}x real time), t=0 penetration {initial*1e3:.2f} mm, "
              f"{args.seconds:g} s drift {drift*1e3:.1f} mm, finite {np.isfinite(data.qpos).all()}")


if __name__ == "__main__":
    main()
