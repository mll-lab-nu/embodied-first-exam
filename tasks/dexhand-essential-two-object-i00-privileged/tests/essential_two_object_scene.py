"""Independent manipulation of two authentic, closed-shell walnut scans."""

import copy
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from essential_assets import asset_path
from essential_rotary_multi import build, reset, reset_history, snapshot
from essential_rotary_multi import features as _shared_features


def configure(source, spec):
    """Replace prototype spheres with matching scan visuals and collision hulls."""
    asset = source.find("asset")
    if asset is None:
        asset = ET.SubElement(source, "asset")
    ET.SubElement(asset, "material", name="collector_surface",
                  rgba="0.72 0.75 0.76 1", specular="0.15", shininess="0.1")
    tray_height = spec["parameters"]["deposit_position"][2]
    tray_position = spec["parameters"]["deposit_position"]
    world = source.find("worldbody")
    for x_sign in (-1, 1):
        for y_sign in (-1, 1):
            ET.SubElement(world, "geom", name=f"collector_foot_{x_sign}_{y_sign}",
                          type="cylinder", size="0.006 0.0225",
                          pos=f"{tray_position[0] + x_sign * 0.08} "
                              f"{tray_position[1] + y_sign * 0.08} 0.1225",
                          rgba="0.14 0.17 0.18 1")
    for geom in source.findall(".//geom"):
        name = geom.get("name") or ""
        if name == "ball_a_deposit" or name.startswith("deposit_wall_"):
            geom.attrib.pop("rgba", None)
            geom.set("material", "collector_surface")
        if name == "ball_a_deposit" and "collector_floor_half_height_m" in spec["parameters"]:
            half_height = spec["parameters"]["collector_floor_half_height_m"]
            size = list(map(float, geom.get("size").split()))
            position = list(map(float, geom.get("pos").split()))
            size[2] = half_height
            # Keep the visible receiving surface at the original height.
            position[2] = tray_height + 0.005 - half_height
            geom.set("size", " ".join(map(str, size)))
            geom.set("pos", " ".join(map(str, position)))
        if name == "ball_a_deposit" and "collector_contact_solref" in spec["parameters"]:
            # An explicitly authored compliant receiver changes only contacts
            # with its visible floor. No held-object contact is softened.
            geom.set("priority", "1")
            geom.set("condim", "6")
            geom.set("friction", "1.5 0.008 0.0004")
            geom.set("solref", " ".join(map(str, spec["parameters"]["collector_contact_solref"])))
            if "collector_contact_solimp" in spec["parameters"]:
                geom.set("solimp", " ".join(map(str, spec["parameters"]["collector_contact_solimp"])))
        if name == "ball_a_deposit" and spec["parameters"].get("collector_floor_geometry") == "heightfield":
            # A bounded flat heightfield has the same finite top, sides and
            # backing depth as the visible box. It is not an infinite plane.
            size = list(map(float, geom.get("size").split()))
            position = list(map(float, geom.get("pos").split()))
            visual = copy.deepcopy(geom)
            visual.set("name", "collector_floor_visual")
            visual.set("contype", "0")
            visual.set("conaffinity", "0")
            visual.set("density", "0")
            world.append(visual)
            rows = spec["parameters"].get("collector_heightfield_rows", 9)
            ET.SubElement(asset, "hfield", name="collector_floor_heightfield",
                          nrow=str(rows), ncol=str(rows),
                          size=f"{size[0]} {size[1]} 0.000001 {2 * size[2]}")
            position[2] += size[2]
            geom.set("pos", " ".join(map(str, position)))
            geom.set("type", "hfield")
            geom.set("hfield", "collector_floor_heightfield")
            geom.attrib.pop("size")
            geom.attrib.pop("material", None)
            geom.set("rgba", "0 0 0 0")
        if name.startswith("deposit_wall_"):
            size = list(map(float, geom.get("size").split()))
            position = list(map(float, geom.get("pos").split()))
            size[2] = 0.008
            position[2] = tray_height + 0.011
            geom.set("size", " ".join(map(str, size)))
            geom.set("pos", " ".join(map(str, position)))
    scale = spec["parameters"].get("walnut_max_extent_m", 0.028) / 0.032
    for label in ("a", "b"):
        prefix = "walnut_" + label
        source_label = spec["parameters"].get("walnut_mesh_" + label, label)
        source_prefix = "walnut_" + source_label
        for role in ("visual", "collision"):
            mesh = ET.SubElement(asset, "mesh", name=prefix + "_" + role,
                          file=asset_path(spec, source_prefix + "_" + role + ".obj"),
                          scale=" ".join([str(scale)] * 3))
            if role == "collision":
                # Native convex-hull LOD avoids excessive contact-facet jitter
                # while retaining the scan's non-spherical outer silhouette.
                mesh.set("maxhullvert", str(spec["parameters"].get("collision_max_hull_vertices", 64)))
        ET.SubElement(asset, "texture", name=prefix + "_texture", type="2d",
                      file=asset_path(spec, source_prefix + "_basecolor.png"))
        ET.SubElement(asset, "material", name=prefix + "_material",
                      texture=prefix + "_texture", specular="0.15", shininess="0.08")
        body = source.find(f".//body[@name='ball_{label}']")
        collision = body.find(f"geom[@name='task_ball_{label}']")
        collision.attrib.pop("size")
        collision.set("type", "mesh")
        collision.set("mesh", prefix + "_collision")
        collision.set("rgba", "0 0 0 0")
        for marker in list(body.findall("geom")):
            if (marker.get("name") or "").startswith("ball_" + label + "_marker"):
                body.remove(marker)
        ET.SubElement(body, "geom", name=prefix + "_visual", type="mesh",
                      mesh=prefix + "_visual", material=prefix + "_material",
                      contype="0", conaffinity="0", density="0")


WUJI_LINK_PREFIX = "r_wuji_r_"


def _wuji_finger(name):
    """Finger of a Wuji Hand 2.2 link body (``r_wuji_r_<finger>[_finger]_<link>``, hands.merge_wuji), else None.

    The finger is the token right after the vendor prefix, never a later link word (``r_wuji_r_ring_finger_middle``
    is the ring finger's middle phalanx). Sharpa Wave bodies never carry this prefix, so Sharpa features are unchanged.
    """
    if not name.startswith(WUJI_LINK_PREFIX):
        return None
    token = name[len(WUJI_LINK_PREFIX):].split("_")[0]
    return token if token in ("thumb", "index", "middle", "ring", "pinky") else None


def features(session):
    """Identify real hand contacts by ancestry, including unnamed vendor meshes."""
    result = _shared_features(session)
    model, data = session.model, session.data
    palm = model.body("right_hand_C_MC").id
    counts = {"a": 0, "b": 0}
    finger_force = {label: {} for label in counts}
    wrench = np.zeros(6)
    object_ids = {model.geom("task_ball_" + label).id: label for label in counts}
    for index in range(data.ncon):
        contact = data.contact[index]
        mujoco.mj_contactForce(model, data, index, wrench)
        force = float(np.linalg.norm(wrench[:3]))
        for object_geom, other_geom in ((contact.geom1, contact.geom2),
                                        (contact.geom2, contact.geom1)):
            if int(object_geom) not in object_ids:
                continue
            body = int(model.geom_bodyid[int(other_geom)])
            chain = []
            while body > 0 and body != palm:
                chain.append(model.body(body).name or "")
                body = int(model.body_parentid[body])
            if body != palm:
                continue
            label = object_ids[int(object_geom)]
            if force > 0.005:
                counts[label] += 1
            for finger in ("thumb", "index", "middle", "ring", "pinky"):
                if any(name.startswith("right_" + finger + "_") or _wuji_finger(name) == finger for name in chain):
                    # A mesh contact manifold can distribute a real finger's
                    # load over several points, each individually below 5 mN.
                    finger_force[label][finger] = finger_force[label].get(finger, 0.0) + force
    for label in counts:
        result[label + "_hand_contacts"] = float(counts[label])
        result[label + "_finger_contacts"] = float(sum(force > 0.005
            for force in finger_force[label].values()))
    return result
