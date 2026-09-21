"""Separate measured task completion from controller and robot qualification."""
import argparse
import json
from pathlib import Path

import mujoco
import numpy as np

from .fixture import cord_disk_crossings
from .physics import node_positions


def review(run):
    run=Path(run)
    report=json.loads((run/'report.json').read_text())
    model=mujoco.MjModel.from_binary_path(str(run/'model/scene.mjb'))
    data=mujoco.MjData(model)
    trace=np.load(run/'states.npz')
    final=np.load(run/'final_state.npz')
    layout=json.loads((run/'model/model_spec.json').read_text())['layout']
    rigid_ids=[model.body(n).id for n in ('target_ring','bead_left','bead_right','disc_left','disc_right')]
    maximum_tail_speed=0.
    for i in np.flatnonzero(trace['time_s']>=final['time_s']-2):
        data.qpos[:]=trace['qpos'][i];data.qvel[:]=trace['qvel'][i]
        mujoco.mj_forward(model,data)
        for body in rigid_ids:
            velocity=np.zeros(6)
            mujoco.mj_objectVelocity(model,data,mujoco.mjtObj.mjOBJ_BODY,body,velocity,0)
            maximum_tail_speed=max(maximum_tail_speed,float(np.linalg.norm(velocity[3:])))
    data.qpos[:]=final['qpos'];data.qvel[:]=final['qvel'];mujoco.mj_forward(model,data)
    body=model.body('target_ring').id
    points=node_positions(model,data)
    local=(points-data.xpos[body])@data.xmat[body].reshape(3,3)
    node_clearance=np.hypot(np.linalg.norm(local[:,:2],axis=1)-layout['ring_major_radius_m'],local[:,2])-layout['ring_tube_radius_m']-layout['rope_radius_m']
    # Distance to the torus surface is 1-Lipschitz. Every segment point is at
    # most half a segment length from one endpoint, giving a conservative bound
    # for the entire capsule chain, rather than only testing its nodes.
    ring_segments=sum(model.geom(i).name.startswith('ring_collision_') for i in range(model.ngeom))
    ring_chord_error=layout['ring_major_radius_m']*(1-np.cos(np.pi/ring_segments))
    segment_clearance_bound=float(node_clearance.min()-.5*np.linalg.norm(np.diff(points,axis=0),axis=1).max()-ring_chord_error)
    original=report['checks']
    physics={k:original[k] for k in ('no_warnings','contact_depth','limited_stretch','terminal_attachment')}
    physics['finite_recording']=bool(np.isfinite(trace['qpos']).all() and np.isfinite(trace['qvel']).all())
    goal={k:original[k] for k in ('ring_away_from_post','ring_on_table','cord_clear_of_ring_disk','no_active_external_hold')}
    goal['last_two_seconds_rigid_speed']=maximum_tail_speed<.002
    goal['cord_surface_separated']=segment_clearance_bound>.01
    result=dict(scope='recorded_fixture_review; does not replace original acceptance report',
                original_all_checks_passed=report['passed'],
                every_step_physics_checks=physics,physics_passed=all(physics.values()),
                measured_goal_checks=goal,measured_goal_passed=all(goal.values()),
                controller_tracking_passed=original['tracking'],
                full_robot_demo=False,robot_execution=report['robot_execution'],
                final_cord_disk_crossings=cord_disk_crossings(model,data),
                final_minimum_ring_to_cord_node_clearance_m=float(node_clearance.min()),
                final_ring_to_cord_segment_clearance_lower_bound_m=segment_clearance_bound,
                maximum_last_two_seconds_rigid_speed_m_s=maximum_tail_speed,
                tail_speed_audit='20 Hz recorded samples; contact/stretch/attachments audited every integration step')
    (run/'completion_review.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True,type=Path)
    review(parser.parse_args().run)
