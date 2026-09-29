"""Scene regressions that lifecycle tests cannot detect."""
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import pytest
import trimesh

from topogym.config.registry import task_definition


def declare(task_id, path):
    task = task_definition(task_id)(seed=7)
    return task, task.declare(path, .9196429)


def test_free_horseshoe_ring_has_mass_gravity_and_no_attachment(tmp_path):
    _, spec = declare("horseshoe_ring", tmp_path)
    ring = next(e for e in spec.entities if e.name == "target_ring")
    tree = ET.parse(ring.asset_path)
    assert not ring.fixed and ring.material["gravity_compensation"] == 0
    assert float(tree.find(".//mass").get("value")) > 0
    assert not tree.findall(".//joint") and not spec.attachments


def test_buzz_scales_physics_and_has_visible_supported_endpoints(tmp_path):
    # Explicit procedural layout regression; registry base now selects authored F1.
    from topogym.tasks.buzz_wire_3d.common import BuzzWireTask
    task = BuzzWireTask(seed=7)
    spec = task.declare(tmp_path, .9196429)
    layout = task.layout
    np.testing.assert_allclose(layout.base_size_m, np.array([.826,.574,.045])*.6)
    assert layout.loop_radius_m == pytest.approx(.026*.6)
    assert layout.grip_length_m == pytest.approx(.070*.6)
    assert layout.supported_endpoints
    assert layout.endpoint_support_part == "stem"
    from topogym.assets.geometry.buzz_wire_3d import BuzzWireLayout
    baseline = BuzzWireLayout(horizontal_scale=.7,depth_scale=.7,height_scale=.7,
                              base_size_m=(.826,.574,.045))
    np.testing.assert_allclose(layout.control_points(),baseline.control_points()*.6+[0,0,.04])
    assert layout.template_id == baseline.template_id
    assert "vertical_switchbacks" in task.route.sections
    for e in spec.entities:
        tree = ET.parse(e.asset_path)
        assert len(tree.findall(".//visual")) == 1
        assert tree.findall(".//collision")
        mesh = Path(tree.find(".//visual/geometry/mesh").get("filename"))
        if not mesh.is_absolute(): mesh = Path(e.asset_path).parent/mesh
        visual = trimesh.load(mesh, force="mesh", process=False)
        assert len(visual.faces) > 0
    wand = next(e for e in spec.entities if e.name == "wand")
    assert not wand.fixed
    # The support deck is raised physically, not only in a visual mesh.
    base = ET.parse(tmp_path/"base.urdf")
    assert len(base.findall(".//collision")) >= 6
    from pygltflib import GLTF2
    for name in ("wire_visual.glb", "wand_visual.glb"):
        gltf = GLTF2().load(str(tmp_path/name))
        metals = sorted(m.pbrMetallicRoughness.metallicFactor for m in gltf.materials)
        assert metals == pytest.approx([0., .9])


def test_buzz_supports_stem_without_occupying_wooden_grip(tmp_path):
    from topogym.assets.geometry.buzz_wire_3d import endpoint_pose, support_boxes
    from topogym.tasks.buzz_wire_3d.common import BuzzWireTask
    task = BuzzWireTask(seed=7)
    task.declare(tmp_path, .9196429)
    seats = [box for box in support_boxes(task.route) if box[3] == "stem_saddle"]
    assert len(seats) == 2
    layout = task.layout
    grip_start = layout.loop_radius_m + layout.stem_length_m
    for end, (centre, size, rotation, _) in enumerate(seats):
        tool_position, tool_rotation = endpoint_pose(task.route, end)
        local = tool_rotation.inv().apply(centre-tool_position)
        assert local[0]-size[0]/2 > layout.loop_radius_m
        # The former seat overlapped the grasp envelope. Keep a measured gap
        # from the start of the wood, independently of its visual appearance.
        assert grip_start-(local[0]+size[0]/2) > .01
        top = centre[2]+size[2]/2
        assert top == pytest.approx(tool_position[2]-layout.loop_tube_radius_m)


def test_buzz_default_declares_selected_authored_f1(tmp_path):
    from topogym.assets.variation_resources import read_json
    task, spec = declare("buzz_wire_3d", tmp_path)
    frozen = read_json(task.layout_resource)
    assert task.variation_id == "buzz_wire_3d_easy"
    assert task.family_id == "F1_triple"
    np.testing.assert_allclose(task.layout.authored_controls_m, frozen["authored_controls_m"])
    np.testing.assert_allclose(task.layout.base_size_m, [.5201, .3689, .0175])
    assert task.layout.endpoint_support_part == "deck"
    assert task.layout.supported_endpoints
    assert all(Path(e.asset_path).is_file() for e in spec.entities)
    assert not next(e for e in spec.entities if e.name == "wand").fixed


def test_lock_has_physical_frames_and_unfixed_key_on_open_cradle(tmp_path):
    _, spec = declare("lock_picking", tmp_path)
    entities = {e.name:e for e in spec.entities}
    assert {"lock_base", "key_tray", "lock_goal_post", "lock_frame_0", "lock_frame_1", "lock_frame_2"} <= entities.keys()
    assert len([n for n in entities if n.startswith("key_cradle_")]) == 4
    assert not entities["lock_key"].fixed and not spec.attachments
    for i in range(3):
        frame = ET.parse(entities[f"lock_frame_{i}"].asset_path)
        assert frame.findall(".//collision")
        assert "engineering_plastic" in frame.find(".//visual/geometry/mesh").get("filename")


@pytest.mark.parametrize("name", ["lock_picking", "buzz_wire_3d", "horseshoe_ring", "orbits"])
def test_asset_bytes_reproduce_across_episode_folders(tmp_path,monkeypatch,name):
    import hashlib
    def manifest(folder):
        declare(name, folder)
        return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob("*") if p.is_file()}
    monkeypatch.chdir(tmp_path)
    assert manifest(Path("first")) == manifest(tmp_path/"second")


@pytest.mark.parametrize("name", ["rope_threading", "orbits", "slotted_post_ring"])
def test_fem_visuals_preserve_volume_and_physical_connections(name,tmp_path):
    task,spec = declare(name,tmp_path)
    for e in spec.entities:
        if e.physics_model == "fem_elastic":
            assert e.surface["metallic"] == 0 and e.surface["roughness"] >= .8
            assert Path(e.volume_path).is_file()
        else:
            if name == "rope_threading":
                assert Path(e.asset_path).suffix == ".glb"
            else:
                xml = ET.parse(e.asset_path)
                assert xml.find(".//visual/geometry/mesh").get("filename").endswith(".glb")
                collider = xml.find(".//collision/geometry/mesh").get("filename")
                assert collider.endswith(".obj")
                assert trimesh.load(Path(e.asset_path).parent/collider, force="mesh").is_watertight
            assert e.morph_options["file_meshes_are_zup"] is True
    if name in {"orbits","slotted_post_ring"}:
        assert len(spec.attachments)==2
    if name == "orbits":
        assert task.layout.base_length_m == pytest.approx(.47*.85)
        assert spec.metadata["placement_anchor"] == "base_center"
        np.testing.assert_allclose(spec.metadata["base_center_xy_m"], [-.1356786, 0.], atol=1e-12)
        base = next(e for e in spec.entities if e.name == "base")
        mesh = trimesh.load(Path(base.asset_path).parent / "base.obj", force="mesh", process=False)
        np.testing.assert_allclose(mesh.bounds.mean(0)[:2]+np.asarray(base.position_m)[:2],
                                   [-.1356786, 0.], atol=1e-8)
        np.testing.assert_allclose(mesh.extents[:2], [.18*.85, .47*.85], atol=1e-8)


def test_orbits_turn_preserves_rigid_geometry_and_fem_material_endpoints(tmp_path):
    """Every loaded mesh and FEM station must follow the same quarter-turn."""
    task_class = task_definition("orbits")
    before = task_class({"yaw_deg": 0., "base_center_xy_m": [0., 0.]}, seed=7)
    after = task_class(seed=7)
    a = before.declare(tmp_path / "before", .9196429)
    b = after.declare(tmp_path / "after", .9196429)
    quarter_turn = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
    translation = np.array([-.1356786, 0., 0.])
    assert a.attachments == b.attachments
    for first, second in zip(a.entities, b.entities, strict=True):
        assert first.name == second.name
        assert first.fixed == second.fixed
        assert first.material == second.material
        for suffix in ("obj", "glb"):
            name = f"{first.name}.{suffix}"
            mesh_a = trimesh.load(tmp_path / "before" / name, force="mesh", process=False)
            mesh_b = trimesh.load(tmp_path / "after" / name, force="mesh", process=False)
            world_a = mesh_a.vertices + first.position_m
            world_b = mesh_b.vertices + second.position_m
            np.testing.assert_allclose(world_b, world_a @ quarter_turn.T + translation, atol=5e-8)
        if first.volume_path is not None:
            with np.load(first.volume_path) as va, np.load(second.volume_path) as vb:
                for key in ("rest", "elements", "material_s_m", "radius_m", "end_stops"):
                    np.testing.assert_array_equal(va[key], vb[key])
                for key in ("spawn", "centerline"):
                    world_a = va[key] + first.position_m
                    world_b = vb[key] + second.position_m
                    np.testing.assert_allclose(world_b, world_a @ quarter_turn.T + translation, atol=1e-12)


@pytest.mark.parametrize("explicit_anchor", [False, True])
def test_orbits_assembly_anchor_keeps_original_center_meaning(tmp_path, explicit_anchor):
    config = {"center_xy_m": [-.1356786, -.24], "yaw_deg": 0.}
    if explicit_anchor:
        config["placement_anchor"] = "assembly_center"
    task = task_definition("orbits")(config, seed=7)
    spec = task.declare(tmp_path, .9196429)
    points = np.vstack([
        trimesh.load(tmp_path / f"{entity.name}.obj", force="mesh", process=False).vertices
        + entity.position_m for entity in spec.entities
    ])
    np.testing.assert_allclose((points.min(0)+points.max(0))[:2]/2, [-.1356786, -.24], atol=1e-8)
    np.testing.assert_allclose(spec.metadata["assembly_center_xy_m"], [-.1356786, -.24])


def test_fiber_visual_repair_does_not_change_joints_or_collision_primitives(tmp_path):
    from topogym.assets.geometry.fiber_bundling import (
        FiberLayout, AnchoredLayout, generate_assets, write_anchored_bundle,
        write_dynamic_material_visuals)
    layout,_=generate_assets(tmp_path,FiberLayout(fiber_count=4))
    path=tmp_path/"bundle.xml"
    write_anchored_bundle(path,layout,AnchoredLayout())
    before=ET.parse(path)
    joints=[ET.tostring(j) for j in before.findall(".//joint")]
    physics={g.get("name"):dict(g.attrib) for g in before.findall(".//body/geom")
             if g.get("contype","1")!="0" or g.get("conaffinity","1")!="0"}
    rows=write_dynamic_material_visuals(path)
    after=ET.parse(path)
    assert [ET.tostring(j) for j in after.findall(".//joint")]==joints
    for g in after.findall(".//body/geom"):
        if g.get("name") in physics:
            old=physics[g.get("name")]; new=dict(g.attrib)
            old.pop("group",None);new.pop("group",None)
            assert old==new
    assert any(r["geom"].startswith("lead_jacket_") for r in rows)
    assert any(r["geom"].startswith("terminal_") for r in rows)


def test_threading_rotation_moves_whole_reference_without_changing_geometry():
    from scipy.spatial.transform import Rotation
    from topogym.assets.geometry.rope_threading import ThreadingLayout
    source = ThreadingLayout(translation_m=(0,0,0))
    posed = ThreadingLayout(translation_m=(-.1356786,.15,.0015),yaw_deg=90)
    rotation = Rotation.from_euler('z',90,degrees=True)
    np.testing.assert_allclose(posed.centerline(),rotation.apply(source.centerline())+posed.translation_m)
    for before,after in zip(source.rings(),posed.rings()):
        for key in ('normal','basis_u','basis_v'):
            np.testing.assert_allclose(after[key],rotation.apply(before[key]),atol=1e-14)


@pytest.mark.parametrize("name", ["rope_threading", "slotted_post_ring"])
def test_default_soft_scenes_fit_standard_high_camera(name, tmp_path):
    import topogym
    from omegaconf import OmegaConf
    _, spec = declare(name, tmp_path)
    path = Path(topogym.__file__).parent/"config/profiles/camera_configs/aloha_observation.yaml"
    camera = OmegaConf.load(path).cameras.cam_high
    forward = np.asarray(camera.lookat)-camera.pos
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, camera.up); right /= np.linalg.norm(right)
    up = np.cross(right,forward)
    vertical = np.tan(np.radians(camera.fov/2))
    horizontal = vertical*camera.res[0]/camera.res[1]
    for entity in spec.entities:
        asset = Path(entity.asset_path)
        if asset.suffix == ".urdf":
            mesh = ET.parse(asset).find(".//visual/geometry/mesh")
            asset = asset.parent / mesh.get("filename")
        vertices = trimesh.load(asset,force="mesh",process=False).vertices
        relative = vertices+entity.position_m-np.asarray(camera.pos)
        depth = relative@forward
        assert np.all(depth>0)
        assert np.max(abs(relative@right)/(depth*horizontal)) < .98, entity.name
        assert np.max(abs(relative@up)/(depth*vertical)) < .98, entity.name


def test_slotted_translation_keeps_all_parts_and_fem_material_geometry_together(tmp_path):
    task, before = declare("slotted_post_ring", tmp_path / "before")
    target = [-.11, -.09]
    moved = task_definition("slotted_post_ring")({"center_xy_m": target}, seed=7)
    after = moved.declare(tmp_path / "after", .9196429)
    delta = np.r_[np.asarray(target)-task.config["center_xy_m"], 0.]
    assert before.attachments == after.attachments
    for first, second in zip(before.entities, after.entities, strict=True):
        assert first.name == second.name
        np.testing.assert_allclose(np.asarray(second.position_m)-first.position_m, delta)
        assert Path(first.asset_path).read_bytes() == Path(second.asset_path).read_bytes()
        if first.volume_path is not None:
            with np.load(first.volume_path) as a, np.load(second.volume_path) as b:
                for key in ("rest", "spawn", "elements", "material_s_m"):
                    np.testing.assert_array_equal(a[key], b[key])


@pytest.mark.parametrize("interval", [.025, .0125])
def test_pickup_schedule_subdivides_lock_ik_increment(interval):
    import importlib.util
    spec = importlib.util.spec_from_file_location("pickup_consumer",
        Path(__file__).parents[1]/"scene_preset_pickup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The measured Lock path exceeded the old 0.03 rad command bound slightly.
    positions = [[0., 0.], [.030436320457, -.01], [.04, -.015]]
    commands = [{'arm': {'joint_position_rad': q, 'gripper_position_rad': 0.}}
                for q in positions]
    result = module.schedule_joint_commands(commands, interval)
    actual = np.asarray([c['arm']['joint_position_rad'] for c in result])
    np.testing.assert_array_equal(actual[0], positions[0])
    np.testing.assert_array_equal(actual[-1], positions[-1])
    assert np.max(abs(np.diff(actual, axis=0))) <= 1.2*interval+1e-12
    assert all(c['arm']['gripper_position_rad'] == 0. for c in result)
