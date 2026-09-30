import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from topogym.tasks.lock_picking.common import LockPickingTask
from topogym.assets.geometry.lock_picking import LockGeometry
from terminal_fixtures import body


def fixture():
    task = LockPickingTask()
    task.table_height_m = .75
    task.layout = g = LockGeometry(slots=((0.,),(0.,),(0.,)),initial_disc_deg=(0.,0.,0.))
    state = dict(bodies={"lock_key":body((g.disc_x(3)+g.disc_thickness/2+g.tab_thickness/2+.002,g.center_y,g.axis_z))},
                 articulations={f"lock_disc_{i}":dict(joints={"disc_hinge":dict(position=np.array([0.]))}) for i in range(3)})
    return task,state


def test_leading_tab_must_clear_thick_plate_not_just_tip():
    task,state = fixture()
    assert task.evaluate_state(state)[0]
    state["bodies"]["lock_key"]["position_m"][0] = task.layout.disc_x(3)+.001
    assert not task.evaluate_state(state)[0]


def test_finite_rotor_limit_failure_and_continuous_joint_wrap():
    task,state = fixture()
    state["articulations"]["lock_disc_2"]["joints"]["disc_hinge"]["position"][0] = 8*np.pi
    assert task.evaluate_state(state)[0]
    state["articulations"]["lock_disc_0"]["joints"]["disc_hinge"]["position"][0] = np.radians(90)
    assert task.evaluate_state(state)[1] == "rotor_limit_exceeded"


def test_lateral_bypass_and_tilt_never_qualify():
    task,state = fixture()
    state["bodies"]["lock_key"]["position_m"][1] += .05
    assert not task.evaluate_state(state)[0]
    task,state = fixture()
    state["bodies"]["lock_key"]["quaternion_wxyz"] = Rotation.from_euler("y",10,degrees=True).as_quat()[[3,0,1,2]]
    assert not task.evaluate_state(state)[0]


def test_misaligned_tab_in_plate_is_not_insertion():
    task,state = fixture()
    state["bodies"]["lock_key"]["position_m"][0] = task.layout.disc_x(3)
    state["bodies"]["lock_key"]["quaternion_wxyz"] = Rotation.from_euler("x",45,degrees=True).as_quat()[[3,0,1,2]]
    reached,_,metrics = task.evaluate_state(state)
    assert not reached and metrics["clearance_issues"]


def test_key_fully_beyond_system_no_longer_occupies_endpoint_hole():
    task,state = fixture()
    state["bodies"]["lock_key"]["position_m"][0] += 1
    reached,_,metrics = task.evaluate_state(state)
    assert not reached and not metrics["shaft_in_goal"]


@pytest.mark.parametrize("terminal", [{"maximum_tilt_deg":float("nan")}, {"rotor_tolerance_deg":-1}, {"typo":1}])
def test_terminal_parameter_errors_are_rejected(terminal):
    with pytest.raises(ValueError):
        LockPickingTask({"terminal":terminal})


def test_restored_medium_declares_passive_physics_and_two_retreat_slots(tmp_path):
    import xml.etree.ElementTree as ET
    from topogym.tasks.lock_picking.lock_picking_medium import LockPickingMediumTask
    task = LockPickingMediumTask()
    spec = task.declare(tmp_path, .9196429)
    entities = {e.name: e for e in spec.entities}
    assert task.layout.slots == [[-60., -30., 0.], [-60.], [0.]]
    for name in ("lock_disc_0", "lock_disc_1", "lock_disc_2", "lock_key"):
        entity = entities[name]
        assert entity.morph_options["default_armature"] == 0.
        assert entity.material["friction"] == .01
        root = ET.parse(entity.asset_path).getroot()
        assert float(root.find(".//mass").get("value")) == .12
        if name != "lock_key":
            assert float(root.find(".//dynamics").get("damping")) == .03
    assert spec.physics_options["rigid"]["constraint_timeconst"] == .0025
    assert task.instance_id != LockPickingMediumTask({"physics":{"passive_armature":.1}}).instance_id


@pytest.mark.parametrize("physics", [{"passive_armature":-1}, {"disc_mass":0},
                                    {"disc_damping":float("nan")}, {"friction":True}, {"typo":1}])
def test_invalid_mechanism_physics_rejected(physics):
    with pytest.raises(ValueError):
        LockPickingTask({"physics":physics})
