"""Scene -> MuJoCo model, and holding a body in place.

Visual meshes are drawn in group 2 and never collide; collision geoms sit in the hidden
group 3 (tick it under Visibility Groups in the browser to see them). Concave pieces are
split with CoACD (cached). Every free body has an inactive weld hold_<body> to the world.
"""
import hashlib

import mujoco
import numpy as np
import trimesh

from design_viewer.scenes import CACHE, cached


def build(scene):
    spec = mujoco.MjSpec.from_string(_base_xml(scene))
    if "cord" in scene.extras:  # the task's cord ends in stop knots; they keep the beads on it
        v, r = _cord_vertices(scene), 1.6*scene.extras["layout"].rope_radius_m
        for name, x in (("cordB_first", 0.), ("cordB_last", np.linalg.norm(v[-1]-v[-2]))):
            spec.body(name).add_geom(type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[r, 0, 0], pos=[x, 0, 0],
                                     density=3300, rgba=(.9, .88, .8, 1))
    for b in scene.bodies:
        body = spec.worldbody.add_body(name=b.name, pos=b.pos, quat=b.quat)
        if b.free:
            body.add_freejoint(name=f"{b.name}_free")
            # MjSpec's default weld data is all zeros (torquescale 0 = no weld); set it explicitly.
            spec.add_equality(type=mujoco.mjtEq.mjEQ_WELD, name=f"hold_{b.name}", name1="world", name2=b.name,
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
    dt = scene.extras.get("timestep", .002)
    return f"""<mujoco model="{scene.name}">
  <option timestep="{dt}" integrator="implicitfast" cone="{'pyramidal' if cable else 'elliptic'}"/>
  <statistic center="0 0 .12" extent=".35"/>
  <!-- Mouse springs, scaled by the grabbed body's mass / inertia. MuJoCo's defaults (100, 500)
       barely move the horseshoe ring that carries the 1 kg assembly: 1.4 mm of a 10 cm pull,
       7 deg of a 45 deg turn; these give 69 mm and 36 deg with <3 mm contact penetration. -->
  <visual><map stiffness="1000" stiffnessrot="5000"/></visual>
  <!-- Stiff contacts (time constant two steps): MuJoCo contacts soften with the lighter body's
       mass, and a pulled ring otherwise squeezes the light cord into itself or the post. -->
  <default><geom friction=".3" condim="3" solref="{2*dt} 1" solimp=".95 .99 .001"/></default>
  <worldbody>
    <light pos="0 0 1.5" dir="0 0 -1" directional="true"/>
    <geom name="floor" type="plane" size=".4 .4 .01" rgba=".82 .82 .8 1"/>
    {cable}
  </worldbody>
  {equality}
</mujoco>"""


def _cord_vertices(scene, n=64):
    cord = scene.extras["cord"]
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(cord, axis=0), axis=1))]
    s = np.linspace(0, arc[-1], n)
    return np.column_stack([np.interp(s, arc, cord[:, i]) for i in range(3)])


def _cable(scene):
    """Slotted cord as a chain of capsules on ball joints, both ends tied to the discs (a stand-in for
    the FEM cord). No elasticity plugin: the browser's WebAssembly client crashes on plugins.
    MuJoCo contacts soften with the lighter body's mass, so the light cord gets two helpers: 3x a real
    cord's density (a hard-pulled ring no longer squeezes it through itself or the post) and joint
    armature, which adds inertia but no weight (a bead rolling on the table no longer pushes the
    cord out through its bore)."""
    vertices, radius = _cord_vertices(scene), scene.extras["layout"].rope_radius_m
    tip = np.linalg.norm(vertices[-1]-vertices[-2])  # cordB_last's frame starts one segment before the end
    cable = f"""<composite prefix="cord" type="cable" vertex="{' '.join(map(str, vertices.ravel()))}" initial="free">
      <joint kind="main" damping=".002" armature="1e-4"/>
      <geom type="capsule" size="{radius}" density="3300" rgba=".9 .88 .8 1"/>
    </composite>"""
    equality = f"""<contact>
    <exclude body1="cordB_first" body2="disc_left"/>
    <exclude body1="cordB_last" body2="disc_right"/>
  </contact>
  <equality>
    <connect body1="cordB_first" body2="disc_left" anchor="0 0 0"/>
    <connect body1="cordB_last" body2="disc_right" anchor="{tip} 0 0"/>
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

    def make():
        import coacd
        coacd.set_log_level("error")
        return [trimesh.Trimesh(v, f) for v, f in coacd.run_coacd(coacd.Mesh(mesh.vertices, mesh.faces), threshold=threshold)]
    return cached(CACHE/"coacd"/f"{key}.pkl", make)


def toggle_hold(model, data, body):
    """Weld `body` to the world where it is now (a second hand), or let it go if already held."""
    eq = model.equality(f"hold_{body}").id
    if not data.eq_active[eq]:
        b = model.body(body).id
        model.eq_data[eq, :11] = [0, 0, 0, *data.xpos[b], *data.xquat[b], 1]  # body pose relative to the world
    data.eq_active[eq] = not data.eq_active[eq]


def release_all(model, data):
    for body in held(model, data):
        data.eq_active[model.equality(f"hold_{body}").id] = 0


def held(model, data):
    return [model.equality(eq).name[5:] for eq in range(model.neq)
            if model.equality(eq).name.startswith("hold_") and data.eq_active[eq]]
