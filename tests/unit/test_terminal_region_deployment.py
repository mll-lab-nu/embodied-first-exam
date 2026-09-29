"""Real generated assets, synthetic motion; no physical reachability claim."""
from dataclasses import asdict
from pathlib import Path
import numpy as np
import pytest
from topogym.config import SimulatorConfig
from topogym.config.scene import load_scene_config
from topogym.config.registry import task_definition
from topogym.evaluation.task_metrics import body_points
from terminal_fixtures import body, soft, ipc

TASKS=('cast_keyhole','horseshoe_ring','hedgehog_in_cage','interlocked_claws','slotted_post_ring','orbits')


@pytest.mark.parametrize('name',TASKS)
def test_declared_region_covers_all_geometry_is_fixed_and_has_versioned_identity(name,tmp_path):
    cfg=load_scene_config(SimulatorConfig(task_id=name,enable_rgb=False))
    table=cfg.env.world.table; height=table.pos[2]+table.size[2]/2
    task=task_definition(name)(); folder=tmp_path/name
    original=task.declare(folder,height)
    spec=task.finalize_spec(original,asset_dir=folder,scene_config=cfg)
    region=task.goal_region; identity=task.instance_id
    assert spec.entities[-1].name=='goal_region'
    assert spec.entities[-1].fixed and spec.entities[-1].morph_options['collision'] is False
    assert set(task.placement_targets)|set(task.placement_remainder)=={e.name for e in original.entities}
    center=np.array(region.center_xy_m); half=np.array(region.half_size_m)
    assert np.all(center-half >= np.array(table.pos[:2])-np.array(table.size[:2])/2)
    assert np.all(center+half <= np.array(table.pos[:2])+np.array(table.size[:2])/2)
    state=dict(physics_step=0,bodies={},fem={},ipc=ipc(('cord',),tuple(a.name for a in spec.attachments)))
    for entity in spec.entities:
        if entity.name == 'goal_region':
            continue
        state['bodies'][entity.name]=body(entity.position_m,entity.quaternion_wxyz)
        if entity.volume_path:
            with np.load(entity.volume_path) as volume:
                points=body_points(state['bodies'][entity.name],volume['spawn'])
            state['fem'][entity.name]=soft(points)
    assert not task.evaluate_state(state)[0]
    # Translate each full target into the middle of the fixed volume; no center-only stand-in.
    for name in task.placement_targets:
        if name in state['fem']:
            # Coiled synthetic cord; this is not a physics solution.
            state['fem'][name]['position_m'][:]=[*center,height+.02]
        else:
            points=body_points(state['bodies'][name],task.placement_vertices[name])
            target_center=np.r_[center,height+.01+(points[:,2].max()-points[:,2].min())/2]
            state['bodies'][name]['position_m']+=target_center-(points.max(axis=0)+points.min(axis=0))/2
    reached,failure,metrics=task.evaluate_state(state)
    assert reached and failure is None, metrics
    task.initialize(state)
    assert not task.result.task_success
    assert task.result.evaluation_status==('available' if task.goal_complete else 'unavailable')
    saved_region=asdict(region)
    name=task.placement_targets[0]
    if name in state['fem']:
        state['fem'][name]['position_m'][0,0]+=1
    else:
        state['bodies'][name]['position_m'][0]+=1
    assert not task.evaluate_state(state)[0]
    assert asdict(task.goal_region)==saved_region and task.instance_id==identity
    assert spec.metadata['terminal']['goal_region_identity']==task.goal_region_identity
    assert task.terminal_metadata()['reachability_qualified'] == (task.task_id == 'cast_keyhole')
    assert 'green dashed' in task.observe()['instruction']
    assert 'goal_region' not in task.observe()


def test_region_rule_retains_rigid_fall_and_penetration_failures():
    from topogym.tasks.cast_keyhole.common import CastKeyholeTask
    from terminal_fixtures import placement, region
    task=CastKeyholeTask()
    state=placement(task,('keyhole_silver',),('keyhole_gold',))
    task.local_vertices=task.placement_vertices
    task.table_height_m=.75
    task.goal_region=region()
    task._task_link_indices={1,2}
    assert task.evaluate_state(state)[0]
    state['bodies']['keyhole_gold']['position_m'][2]=.5
    assert task.evaluate_state(state)[1]=='A task body fell below the table'
    state['bodies']['keyhole_gold']['position_m'][2]=.75
    state['contacts']=dict(link_a=[1],link_b=[99],penetration=[.002])
    assert task.evaluate_state(state)[1]=='Task contact penetration exceeded 1 mm'
