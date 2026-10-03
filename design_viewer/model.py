"""Scene -> MuJoCo model, and pinning a body in place.

Visual meshes are drawn in group 2 and never collide; collision geoms sit in the hidden
group 3 (tick it under Visibility Groups in the browser to see them). Concave pieces are
split with CoACD (cached). Every free body has an inactive weld pin_<body> to the world.
"""
import hashlib
import pickle

import mujoco
import numpy as np
import trimesh

from design_viewer.scenes import CACHE


def build(scene):
    spec = mujoco.MjSpec.from_string(_base_xml(scene))
    for b in scene.bodies:
        body = spec.worldbody.add_body(name=b.name, pos=b.pos, quat=b.quat)
        if b.free:
            body.add_freejoint(name=f"{b.name}_free")
            # MjSpec's default weld data is all zeros (torquescale 0 = no weld); set it explicitly.
            spec.add_equality(type=mujoco.mjtEq.mjEQ_WELD, name=f"pin_{b.name}", name1="world", name2=b.name,
                              objtype=mujoco.mjtObj.mjOBJ_BODY, active=False, solref=[.02, 1],
                              data=[0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1])
        spec.add_mesh(name=f"{b.name}_visual", uservert=b.visual.vertices.ravel(), userface=b.visual.faces.ravel(),
                      inertia=mujoco.mjtMeshInertia.mjMESH_INERTIA_SHELL)
        body.add_geom(type=mujoco.mjtGeom.mjGEOM_MESH, meshname=f"{b.name}_visual", rgba=b.rgba, group=2,
                      contype=0, conaffinity=0, mass=0)
        common = dict(group=3, density=b.density, rgba=(*b.rgba[:3], .5))
        for i, item in enumerate(_convex(b.collision)):
            if isinstance(item, trimesh.Trimesh):
                spec.add_mesh(name=f"{b.name}_c{i}", uservert=item.vertices.ravel(), userface=item.faces.ravel())
                body.add_geom(type=mujoco.mjtGeom.mjGEOM_MESH, meshname=f"{b.name}_c{i}", **common)
            else:
                _, p, q, r = item
                body.add_geom(type=mujoco.mjtGeom.mjGEOM_CAPSULE, fromto=[*p, *q], size=[r, 0, 0], **common)
    return spec.compile()


def _base_xml(scene):
    cable, equality = _cable(scene) if "cord" in scene.extras else ("", "")
    return f"""<mujoco model="{scene.name}">
  <option timestep="{scene.extras.get('timestep', .002)}" integrator="implicitfast" cone="{'pyramidal' if cable else 'elliptic'}"/>
  <statistic center="0 0 .12" extent=".35"/>
  <!-- Mouse pull spring per kg of the grabbed body. MuJoCo's 100 cannot lift the 0.13 kg
       horseshoe ring that carries the 1 kg assembly (1000: +69 mm of a 100 mm pull). -->
  <visual><map stiffness="1000"/></visual>
  {'<extension><plugin plugin="mujoco.elasticity.cable"/></extension>' if cable else ''}
  <default><geom friction=".3" condim="3" solref=".004 1"/></default>
  <worldbody>
    <light pos="0 0 1.5" dir="0 0 -1" directional="true"/>
    <geom name="floor" type="plane" size=".4 .4 .01" rgba=".82 .82 .8 1"/>
    {cable}
  </worldbody>
  {equality}
</mujoco>"""


def _cable(scene, n=64):
    """MuJoCo cable for the slotted cord, both ends tied to the discs (a stand-in for the FEM cord)."""
    cord, radius = scene.extras["cord"], scene.extras["layout"].rope_radius_m
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(cord, axis=0), axis=1))]
    s = np.linspace(0, arc[-1], n)
    vertices = np.column_stack([np.interp(s, arc, cord[:, i]) for i in range(3)])
    cable = f"""<composite prefix="cord" type="cable" vertex="{' '.join(map(str, vertices.ravel()))}" initial="free">
      <plugin plugin="mujoco.elasticity.cable">
        <config key="twist" value="1e6"/><config key="bend" value="2e5"/><config key="vmax" value="0"/>
      </plugin>
      <joint kind="main" damping=".002"/>
      <geom type="capsule" size="{radius}" density="1100" rgba=".9 .88 .8 1"/>
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
    path = CACHE/"coacd"/f"{key}.pkl"
    if not path.exists():
        import coacd
        coacd.set_log_level("error")
        parts = coacd.run_coacd(coacd.Mesh(mesh.vertices, mesh.faces), threshold=threshold)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps([trimesh.Trimesh(v, f) for v, f in parts]))
    return pickle.loads(path.read_bytes())


def toggle_pin(model, data, body):
    """Weld `body` to the world where it is now (a second hand), or let it go if already pinned."""
    eq = model.equality(f"pin_{body}").id
    if not data.eq_active[eq]:
        b = model.body(body).id
        model.eq_data[eq, :11] = [0, 0, 0, *data.xpos[b], *data.xquat[b], 1]  # body pose relative to the world
    data.eq_active[eq] = not data.eq_active[eq]


def unpin_all(model, data):
    for body in pinned(model, data):
        data.eq_active[model.equality(f"pin_{body}").id] = 0


def pinned(model, data):
    return [model.equality(eq).name[4:] for eq in range(model.neq)
            if model.equality(eq).name.startswith("pin_") and data.eq_active[eq]]


def penetration(model, data):
    return float(max(0., -data.contact.dist[:data.ncon].min(initial=0.)))
