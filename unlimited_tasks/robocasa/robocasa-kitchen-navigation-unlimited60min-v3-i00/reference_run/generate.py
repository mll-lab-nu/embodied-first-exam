"""Generate native base actions from the frozen scene, then save for open-loop replay."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, '/app')
from casa_traj import Session


def main():
    s = Session()
    try:
        obs = s.observe()
        target = obs['target_pos'][:2].copy()
        yaw_goal = obs['target_yaw']
        waypoints = [np.array([obs['base_pos'][0], -1.25]),
                     np.array([target[0], -1.25]),
                     target + np.array([0., -0.08])]
        for stage, waypoint in enumerate(waypoints):
            for i in range(350):
                obs = s.observe()
                error = waypoint - obs['base_pos'][:2]
                yaw = obs['base_yaw']
                yaw_error = np.arctan2(np.sin(yaw_goal-yaw), np.cos(yaw_goal-yaw))
                if np.linalg.norm(error) < 0.035 and abs(yaw_error) < 0.03:
                    break
                velocity = 2.5 * error
                # Compensate native static friction while approaching waypoints.
                velocity = np.where(np.abs(error) > 0.018,
                                    np.sign(error) * np.maximum(np.abs(velocity), 0.30), 0.)
                velocity *= min(1., 0.5 / max(np.linalg.norm(velocity), 1e-12))
                forward = np.array([np.cos(yaw), np.sin(yaw)])
                left = np.array([-np.sin(yaw), np.cos(yaw)])
                action = np.clip([velocity @ forward, velocity @ left, 1.8*yaw_error], -1., 1.)
                s.step(action)
                if i % 40 == 0:
                    print(stage, i, s.observe(), flush=True)
            else:
                raise RuntimeError(f'Failed to reach waypoint {stage}')
        for _ in range(20):
            s.step([0., 0., 0.])
        print('FINAL', s.observe(), flush=True)
        assert s.observe()['success']
        s.save('/app/output/trajectory.npz')
    finally:
        s.close()

if __name__ == '__main__':
    main()
