"""Development coding-agent reference: proportional native mobile-base velocity control."""
from pathlib import Path
import json
import numpy as np
from casa_traj import Session, state_sha


def solve():
    session = Session()
    try:
        for index in range(1000):
            obs = session.observe()
            delta = obs["target_pos"][:2] - obs["base_pos"][:2]
            yaw = obs["base_yaw"]
            rotation = np.array([[np.cos(yaw), np.sin(yaw)], [-np.sin(yaw), np.cos(yaw)]])
            local_error = rotation @ delta
            yaw_error = np.arctan2(np.sin(obs["target_yaw"] - yaw), np.cos(obs["target_yaw"] - yaw))
            action = np.clip(np.r_[local_error * 2.0, yaw_error * 2.0], -0.8, 0.8)
            session.step(action)
            if index % 25 == 0:
                print(index, obs["base_pos"], obs["target_pos"], flush=True)
            if np.linalg.norm(delta) < 0.14 and abs(yaw_error) < 0.12:
                break
        for _ in range(20):
            session.step([0, 0, 0])
        assert session.observe()["success"], session.observe()
        session.save()
        Path('/app/output/agent_run.json').write_text(json.dumps(dict(
            success=int(session.observe()['success']), n_actions=len(session.actions),
            state_sha=state_sha(session.env), provenance='development coding-agent run')) + '\n')
        print(session.observe())
    finally:
        session.close()


if __name__ == "__main__":
    solve()
