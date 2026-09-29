"""Substep orchestration tests, not Genesis runtime qualification."""
from types import SimpleNamespace as NS
import numpy as np
import pytest
from topogym.world.physics.rigid_contacts import RigidContactCollector, resolve_roles, resolve_robot_parts
from topogym.tasks.base import EntitySpec


class Collider:
    def __init__(self):
        self._contact_data_cache = {}
        self.current = -1

    def get_contacts(self):
        if not self._contact_data_cache:
            # A touch exists only in the first substep, with zero measured force.
            depths = [.0, -.001] if self.current == 0 else []
            n = len(depths)
            self._contact_data_cache.update(geom_a=np.full(n, 1), geom_b=np.full(n, 2),
                penetration=np.array(depths), force=np.zeros((n, 3)))
        return self._contact_data_cache


def collector():
    collider = Collider()
    def substep(f):
        collider.current = f
    solver = NS(collider=collider, substep=substep, is_active=True, detect_collision=lambda: None)
    scene = NS(sim=NS(rigid_solver=solver, substeps=4, coupler=NS()))
    return RigidContactCollector(scene, {1:'wand_metal',2:'wire_metal'}, geometry_complete=True), solver, substep


def test_transient_zero_force_touch_is_not_lost_to_final_substep_or_query_cache():
    monitor, solver, original = collector()
    monitor.begin(1)
    for i in range(4):
        solver.substep(i)
    monitor.end()
    first = monitor.read()
    assert first['substeps_complete'] and first['sampled_substeps'] == 4
    assert len(first['events']) == 1
    assert first['events'][0]['substep'] == 0 and first['events'][0]['force_n'] == 0
    assert first['events'][0]['touching']
    first['events'].clear()
    assert len(monitor.read()['events']) == 1
    checkpoint = monitor.read()
    monitor.begin(2)
    solver.substep(1)
    monitor.end()
    assert not monitor.read()['substeps_complete']
    assert monitor.read()['events'] == []
    monitor.restore(checkpoint)
    assert monitor.read() == checkpoint
    checkpoint['events'].clear()
    assert monitor.read()['events']
    monitor.close()
    assert solver.substep is original


def test_role_resolution_uses_geometry_not_import_order_and_detects_missing_shape(tmp_path):
    path=tmp_path/'roles.urdf'
    path.write_text('''<robot><link name="wire">
      <collision name="metal"><origin xyz="1 0 0"/><geometry><sphere radius=".1"/></geometry></collision>
      <collision name="wood"><geometry><box size="1 2 3"/></geometry></collision>
    </link></robot>''')
    spec = EntitySpec('wire','urdf',path,contact_roles={'metal':'wire_metal','wood':'wood_stop'})
    def geom(idx, kind, pos, data):
        return NS(idx=idx,type=NS(name=kind),init_pos=pos,init_quat=[1,0,0,0],data=data)
    box=geom(12,'BOX',[0,0,0],[1,2,3]); sphere=geom(4,'SPHERE',[1,0,0],[.1])
    link=NS(name='wire',geoms=[box,sphere])
    roles,complete=resolve_roles(NS(links=[link]),spec)
    assert complete and roles=={12:'wood_stop',4:'wire_metal'}
    link.geoms=[box]
    assert not resolve_roles(NS(links=[link]),spec)[1]
    link.geoms=[box,geom(7,'SPHERE',[2,0,0],[.1])]
    roles,complete=resolve_roles(NS(links=[link]),spec)
    assert not complete and roles[7]=='unknown'


def test_world_maps_roles_before_build_reanchors_free_body_geoms(tmp_path,monkeypatch):
    from topogym.world.genesis_world import GenesisWorld
    path=tmp_path/'tool.urdf'
    path.write_text('<robot><link name="wand"><collision name="metal"><geometry><sphere radius=".1"/></geometry></collision></link></robot>')
    geom=NS(idx=5,type=NS(name='SPHERE'),init_pos=np.zeros(3),init_quat=[1,0,0,0],data=[.1])
    entity=NS(links=[NS(name='wand',geoms=[geom])])
    monitor,solver,original=collector(); monitor.close()
    def build(**kwargs):
        geom.init_pos=np.array([.3,.2,0.])  # Model Genesis' COM frame change.
    scene=NS(dt=.0025,sim=NS(rigid_solver=solver,substeps=4,coupler=NS()),build=build)
    world=GenesisWorld(scene,entities={'wand':entity})
    world._contact_specs=[EntitySpec('wand','urdf',path,contact_roles={'metal':'wand_metal'})]
    monkeypatch.setattr(world,'_check_checkpoint_support',lambda:None)
    world.build()
    assert world._contact_collector.geometry_complete
    assert world._contact_collector.roles=={5:'wand_metal'}
    world._contact_collector.close()


def test_mjcf_roles_survive_cached_duplicate_names_and_match_authored_geometry(tmp_path):
    from scipy.spatial.transform import Rotation
    path = tmp_path / "bundle.xml"
    path.write_text('''<mujoco><worldbody><body name="trunk">
      <geom name="jacket" type="capsule" fromto="0 0 0 .1 0 0" size=".01"/>
      <geom name="visual" contype="0" conaffinity="0"/>
      <body name="fiber"><geom name="strand_0" type="capsule" fromto=".003 0 0 .02 0 0" size=".001"/>
        <geom name="strand_1" type="capsule" fromto="0 .01 0 .02 .01 0" size=".001"/></body>
    </body></worldbody></mujoco>''')
    spec = EntitySpec("bundle", "mjcf", path,
        contact_roles={"jacket":"fiber_sheath", "strand_0":"fiber_strand", "strand_1":"fiber_strand"})
    q = Rotation.from_euler("y",90,degrees=True).as_quat()[[3,0,1,2]]
    a,b,jacket = [NS(idx=i,metadata={"name":"cached_wrong_name"},type=NS(name="CAPSULE"),
                    init_pos=p,init_quat=q,data=np.r_[size,[0.]*5])
                 for i,p,size in [(19,[.0115,0,0],[.001,.017]),(2,[.01,.01,0],[.001,.02]),
                                   (7,[.05,0,0],[.01,.1])]]
    trunk, fiber = NS(name="trunk", geoms=[jacket]), NS(name="fiber", geoms=[b,a])
    entity = NS(links=[fiber,trunk])
    expected = {19:"fiber_strand", 2:"fiber_strand", 7:"fiber_sheath"}
    assert resolve_roles(entity,spec) == (expected,True)
    fiber.geoms = [a]
    assert resolve_roles(entity,spec)[1] is False  # Missing capsule cannot be excused.
    fiber.geoms = [a,b]
    a.metadata = {}
    assert resolve_roles(entity,spec) == (expected,True)  # Native names are not trusted.
    a.data[0] = .1
    assert resolve_roles(entity,spec)[0][19] == "unknown"
    assert resolve_roles(entity,spec)[1] is False
    a.data[0] = .001
    fiber.name = "wrong_body"
    assert resolve_roles(entity,spec)[1] is False
    fiber.name = "fiber"
    jacket.init_pos = [.5,0,0]
    assert resolve_roles(entity,spec)[1] is False


@pytest.mark.parametrize("shape,size,data", [("sphere",".01",[.01]),("box",".01 .02 .03",[.02,.04,.06]),
                                              ("cylinder",".01 .02",[.01,.04])])
def test_mjcf_primitive_dimensions_and_missing_declared_geometry(tmp_path,shape,size,data):
    path=tmp_path/'shape.xml'
    path.write_text(f'<mujoco><worldbody><body name="part"><geom name="surface" type="{shape}" size="{size}" pos=".1 .2 .3"/></body></worldbody></mujoco>')
    spec=EntitySpec('part','mjcf',path,contact_roles={'surface':'fiber_sheath'})
    geom=NS(idx=1,type=NS(name=shape.upper()),init_pos=[.1,.2,.3],init_quat=[1,0,0,0],data=data)
    entity=NS(links=[NS(name='part',geoms=[geom])])
    assert resolve_roles(entity,spec)==({1:'fiber_sheath'},True)
    entity.links[0].geoms=[]
    assert resolve_roles(entity,spec)[1] is False


def robot_fixture():
    from topogym.robot.description import GraspDescription
    # The housing and linkage are descendants of the declared tool root;
    # a separate arm link must not acquire the gripper label.
    robot = NS(links=[NS(name=name,idx=i,parent_idx=parent,
                        geoms=[NS(idx=i+100)] if i != 3 else [])
        for name,i,parent in [("arm",2,-1),("tool",3,2),("housing",8,3),
                              ("linkage",4,8),("left",5,4),("right",6,8)]])
    description = NS(groups=(NS(grasp=GraspDescription(("left","right"),0.,1.,"tool")),))
    return robot, description


def test_robot_parts_cover_housing_linkages_and_pads_without_relabeling_arm():
    robot, description = robot_fixture()
    parts, complete = resolve_robot_parts(robot,description)
    assert complete
    assert parts == {102:"arm",108:"gripper",104:"gripper",105:"gripper",106:"gripper"}
    robot.links = [link for link in robot.links if link.name != "left"]
    assert not resolve_robot_parts(robot,description)[1]
    assert resolve_robot_parts(robot,None) == ({},False)
    robot.links = [link for link in robot.links if link.name != "tool"]
    assert not resolve_robot_parts(robot,description)[1]


def test_collector_preserves_robot_role_and_adds_part_and_restorable_coverage():
    monitor, solver, _ = collector()
    monitor.roles = {1:"robot",2:"fiber_strand"}
    monitor.robot_parts = {1:"gripper"}
    monitor.robot_geometry_complete = True
    monitor.begin(1)
    for i in range(4):
        solver.substep(i)
    monitor.end()
    result = monitor.read()
    assert result["robot_geometry_complete"] and result["substeps_complete"]
    assert result["events"][0]["role_a"] == "robot"
    assert result["events"][0]["robot_part_a"] == "gripper"
    monitor.begin(2)
    monitor.restore(result)
    assert monitor.read() == result
    monitor.close()


@pytest.mark.parametrize("robot_name", ["panda_robotiq","aloha"])
def test_declared_gripper_subtree_contains_all_native_pad_links(robot_name):
    import xml.etree.ElementTree as ET
    from topogym.config.scene import load_scene_config
    from topogym.config import SimulatorConfig
    from topogym.assets.robot import robot_asset
    from topogym.robot.description import describe_robot
    cfg = load_scene_config(SimulatorConfig(task_id="fiber_bundling",robot_id=robot_name))
    description = describe_robot(cfg.robot_control)
    root = ET.parse(robot_asset(cfg.robot_control)).getroot()
    for group in description.groups:
        subtree = root.find(f".//body[@name='{group.grasp.contact_root_link}']")
        assert subtree is not None
        names = {body.get("name") for body in subtree.iter("body")}
        assert set(group.grasp.finger_links) <= names
        if robot_name == "panda_robotiq":
            assert {"r85_base", "r85_left_driver", "r85_right_coupler"} <= names
