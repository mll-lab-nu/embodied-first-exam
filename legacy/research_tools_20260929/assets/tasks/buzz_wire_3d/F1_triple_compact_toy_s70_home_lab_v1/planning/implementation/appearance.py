"""UV-mapped wood and continuous metal visuals for the collision-backed toy."""

from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation
import trimesh
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

from topogym.tasks.hedgehog_in_cage.appearance import wood_visual
from .geometry import capsule_mesh

TEXTURES = (
    Path(__file__).resolve().parents[3]
    / "assets/tasks/hedgehog_in_cage/classic_3star/materials"
)


def wood(mesh, *, light=False, tile=0.20):
    return wood_visual(
        mesh,
        TEXTURES / ("light_wood.png" if light else "dark_wood.png"),
        roughness=0.48 if light else 0.55,
        tile_size=tile,
        grain_horizontal=light,
    )


def metal(mesh, *, copper=False):
    mesh.visual = TextureVisuals(
        uv=np.zeros((len(mesh.vertices), 2)),
        material=PBRMaterial(
            name="brushed_copper" if copper else "stainless_wire",
            baseColorFactor=(0.72, 0.33, 0.16, 1) if copper else (0.68, 0.73, 0.77, 1),
            metallicFactor=0.9,
            roughnessFactor=0.25 if copper else 0.28,
        ),
    )
    return mesh


def replace_visuals(path, filenames):
    tree = ET.parse(path)
    link = tree.find("link")
    for node in link.findall("visual"):
        link.remove(node)
    for filename in filenames:
        node = ET.SubElement(link, "visual")
        ET.SubElement(ET.SubElement(node, "geometry"), "mesh", filename=filename)
    ET.indent(tree)
    tree.write(path, encoding="unicode", xml_declaration=True)


def restore_renderer_materials(entity):
    """Keep GLB PBR finishes through Genesis' diffuse-only mesh conversion.

    Restore only the visual material before rasterizer construction. The loaded
    vertices, collision meshes and dynamics are untouched.
    """
    for geom in entity.vgeoms:
        mesh = geom.vmesh
        path = mesh.metadata.get("mesh_path")
        if not path or Path(path).suffix != ".glb":
            continue
        original = trimesh.load(path, force="mesh", process=False)
        if not isinstance(original.visual, TextureVisuals):
            continue
        # Keep Genesis' UVs: its loader flips them twice before rasterization.
        uv = getattr(mesh.trimesh.visual, "uv", None)
        if uv is None:
            uv = np.zeros((len(mesh.trimesh.vertices), 2))
        mesh.trimesh.visual = TextureVisuals(
            uv=uv, material=original.visual.material.copy()
        )


def finish_assets(folder, wire):
    # One smooth visual tube avoids the bead-like joints of collision capsules.
    # Collision primitives remain exact and are independently checked.
    from .preview import tube_mesh

    layout = wire.layout
    if layout.finish == "toy_wood_copper":
        return finish_toy_assets(folder, wire)
    base = trimesh.creation.box(layout.base_size_m)
    wood(base, light=True, tile=0.26).export(folder / "base_wood.glb")
    metal(tube_mesh(wire.rail, layout.wire_radius_m, sides=20)).export(
        folder / "rail_metal.glb"
    )
    mounts = [
        capsule_mesh(a, b, r)
        for a, b, r, part in wire.fixed_capsules()
        if part != "wire"
    ]
    wood(trimesh.util.concatenate(mounts), tile=0.12).export(folder / "posts_wood.glb")
    replace_visuals(folder / "wire.urdf", ["rail_metal.glb", "posts_wood.glb"])

    segments = layout.tool_capsules()
    loop = tube_mesh(
        np.array([row[0] for row in segments[:-2]]), layout.loop_tube_radius_m, True, 20
    )
    metal(
        trimesh.util.concatenate([loop, capsule_mesh(*segments[-2][:3])]), copper=True
    ).export(folder / "ring_copper.glb")
    a, b, radius, _ = segments[-1]
    if layout.grip_shape == "box":
        grip = trimesh.creation.box(
            (
                layout.grip_length_m,
                2 * layout.grip_radius_m,
                2 * layout.grip_half_thickness_m,
            )
        )
        transform = np.eye(4)
        transform[:3, :3] = Rotation.from_euler(
            "x", layout.grip_flat_roll_deg, degrees=True
        ).as_matrix()
        transform[:3, 3] = (a + b) / 2
        grip.apply_transform(transform)
    else:
        grip = capsule_mesh(a, b, radius)
    wood(grip, light=True, tile=0.08).export(folder / "handle_wood.glb")
    replace_visuals(folder / "wand.urdf", ["ring_copper.glb", "handle_wood.glb"])


def toy_wood(mesh, tile=0.60):
    """Continuous pale wood grain, without repeated strips at UV wrap seams."""
    vertices = mesh.vertices[mesh.faces].reshape(-1, 3)
    normals = np.repeat(mesh.face_normals, 3, axis=0)
    dominant = np.repeat(np.argmax(abs(mesh.face_normals), axis=1), 3)
    u_axis = np.where(dominant == 0, 1, 0)
    v_axis = np.where(dominant == 2, 1, 2)
    rows = np.arange(len(vertices))
    uv = np.c_[vertices[rows, u_axis], vertices[rows, v_axis]] / tile + 0.5
    with Image.open(TEXTURES / "light_wood.png") as source:
        texture = source.convert("RGB")
    result = trimesh.Trimesh(
        vertices=vertices,
        faces=np.arange(len(vertices)).reshape(-1, 3),
        vertex_normals=normals,
        process=False,
    )
    result.visual = TextureVisuals(
        uv=uv,
        material=PBRMaterial(
            name="pale_toy_wood",
            baseColorTexture=texture,
            baseColorFactor=(0.90, 0.86, 0.77, 1),
            metallicFactor=0.0,
            roughnessFactor=0.62,
        ),
    )
    return result


def plinth_layers(size):
    """Two convex, cut-corner tiers contained by the original box envelope."""
    x, y, h = np.asarray(size) / 2
    corner = min(x, y) * 0.18

    def outline(inset):
        a, b = x - inset, y - inset
        return np.array(
            [
                [-a + corner, -b],
                [a - corner, -b],
                [a, -b + corner],
                [a, b - corner],
                [a - corner, b],
                [-a + corner, b],
                [-a, b - corner],
                [-a, -b + corner],
            ]
        )

    def tier(levels):
        vertices = np.vstack(
            [np.c_[outline(inset), np.full(8, z)] for z, inset in levels]
        )
        faces = [[0, i + 1, i] for i in range(1, 7)]
        top = (len(levels) - 1) * 8
        faces += [[top, top + i, top + i + 1] for i in range(1, 7)]
        for level in range(len(levels) - 1):
            for i in range(8):
                a, b = level * 8 + i, level * 8 + (i + 1) % 8
                faces += [[a, b, b + 8], [a, b + 8, a + 8]]
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
        mesh.fix_normals()
        if not mesh.is_watertight or not mesh.is_convex:
            raise ValueError("Toy plinth tiers must be closed convex collision meshes")
        return mesh

    return [
        tier([(-h, 0.002), (-h + 0.002, 0), (-h + 0.006, 0.001)]),
        tier([(-h + 0.006, 0.008), (-h + 0.008, 0.005), (h, 0.011)]),
    ]


def finish_toy_assets(folder, wire):
    from .preview import tube_mesh

    layout = wire.layout
    if layout.end_stop_shape != "block_mount":
        raise ValueError("Photo-style toy finish requires block mounts")
    layers = plinth_layers(layout.base_size_m)
    # URDF origin remains at the old deck centre; all physical supports share
    # the same generator as the IK and full-tool clearance checks.
    from .supports import support_boxes, support_spheres

    for layer in layers:
        layer.apply_translation([0, 0, layout.base_elevation_m])
    for centre, size, rotation, _ in support_boxes(wire):
        box = trimesh.creation.box(size)
        transform = np.eye(4)
        transform[:3, :3] = rotation.as_matrix()
        transform[:3, 3] = centre - [0, 0, layout.base_size_m[2] / 2]
        box.apply_transform(transform)
        layers.append(box)
    grain_tile = max(layout.base_size_m) * 1.04
    sphere_visuals = []
    for centre, radius, _ in support_spheres(wire):
        sphere = trimesh.creation.icosphere(subdivisions=3, radius=radius)
        sphere.apply_translation(centre - [0, 0, layout.base_size_m[2] / 2])
        sphere_visuals.append(sphere)
    toy_wood(
        trimesh.util.concatenate([*layers, *sphere_visuals]), tile=grain_tile
    ).export(folder / "base_wood.glb")
    root = ET.Element("robot", name="toy_plinth")
    link = ET.SubElement(root, "link", name="base")
    visual = ET.SubElement(link, "visual")
    ET.SubElement(ET.SubElement(visual, "geometry"), "mesh", filename="base_wood.glb")
    for i, layer in enumerate(layers):
        filename = f"base_collision_{i}.obj"
        layer.export(folder / filename)
        node = ET.SubElement(link, "collision")
        ET.SubElement(ET.SubElement(node, "geometry"), "mesh", filename=filename)
    for centre, radius, _ in support_spheres(wire):
        node = ET.SubElement(link, "collision")
        ET.SubElement(
            node,
            "origin",
            xyz=" ".join(map(str, centre - [0, 0, layout.base_size_m[2] / 2])),
        )
        ET.SubElement(ET.SubElement(node, "geometry"), "sphere", radius=str(radius))
    ET.indent(root)
    ET.ElementTree(root).write(
        folder / "base.urdf", encoding="unicode", xml_declaration=True
    )
    rail = metal(tube_mesh(wire.rail, layout.wire_radius_m, sides=24), copper=True)
    rail.visual.material.roughnessFactor = 0.36
    rail.export(folder / "rail_metal.glb")
    mounts = []
    for a, _, _, part in wire.fixed_capsules():
        if part == "stop":
            block = trimesh.creation.box(layout.mount_size_m)
            block.apply_translation(a)
            mounts.append(block)
    toy_wood(trimesh.util.concatenate(mounts), tile=grain_tile).export(
        folder / "posts_wood.glb"
    )
    replace_visuals(folder / "wire.urdf", ["rail_metal.glb", "posts_wood.glb"])
    segments = layout.tool_capsules()
    loop = tube_mesh(
        np.array([row[0] for row in segments[:-2]]), layout.loop_tube_radius_m, True, 24
    )
    metal(trimesh.util.concatenate([loop, capsule_mesh(*segments[-2][:3])])).export(
        folder / "ring_steel.glb"
    )
    a, b, radius, _ = segments[-1]
    if layout.grip_shape == "box":
        grip = trimesh.creation.box(
            (
                layout.grip_length_m,
                2 * layout.grip_radius_m,
                2 * layout.grip_half_thickness_m,
            )
        )
        transform = np.eye(4)
        transform[:3, :3] = Rotation.from_euler(
            "x", layout.grip_flat_roll_deg, degrees=True
        ).as_matrix()
        transform[:3, 3] = (a + b) / 2
        grip.apply_transform(transform)
    else:
        grip = capsule_mesh(a, b, radius)
    toy_wood(grip, tile=0.16).export(folder / "handle_wood.glb")
    replace_visuals(folder / "wand.urdf", ["ring_steel.glb", "handle_wood.glb"])
