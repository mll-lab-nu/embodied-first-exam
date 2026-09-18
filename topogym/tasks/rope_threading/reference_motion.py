"""Verified public motion reference, kept separate from newly simulated evidence."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation


def load_motion(folder):
    folder = Path(folder)
    manifest = json.loads((folder/"manifest.json").read_text())
    geometry = json.loads((folder/"geometry.json").read_text())
    tip_geom = next(g for g in geometry["geoms"] if g["name"] == "v4_rope_79")
    axis = Rotation.from_quat(tip_geom["quaternion_wxyz"], scalar_first=True).apply([0, 0, tip_geom["size"][1]])
    local_tip = np.asarray(tip_geom["position"])-axis
    pieces, stages = [], []
    previous_time = -np.inf
    for phase in manifest["phases"]:
        spec = phase["binary"]
        data = (folder/Path(spec["url"]).name).read_bytes()
        if len(data) != spec["bytes"] or hashlib.sha256(data).hexdigest() != spec["sha256"]:
            raise ValueError(f'Invalid reference phase {phase["index"]}')

        def array(item):
            result = np.frombuffer(data, dtype=item["dtype"], offset=item["byte_offset"], count=item["count"])
            if hashlib.sha256(result.tobytes()).hexdigest() != item["sha256"]:
                raise ValueError("Reference array hash mismatch")
            return result.reshape(item["shape"])

        times = array(phase["arrays"]["actual_time_s"])
        selected = times > previous_time+1e-8
        poses = array(phase["arrays"]["body_poses"])
        tip = poses[:, 100, :3]+Rotation.from_quat(poses[:, 100, 3:], scalar_first=True).apply(local_tip)
        nodes = np.concatenate((poses[:, 21:, :3], tip[:, None, :]), axis=1)
        pieces.append(dict(time=times[selected].copy(), phase=np.full(selected.sum(), phase["index"]),
            qpos=array(phase["telemetry"]["arrays"]["qpos"])[selected].copy(),
            ctrl=array(phase["telemetry"]["arrays"]["ctrl"])[selected].copy(),
            equality=array(phase["arrays"]["equality_active"])[selected].copy(),
            hands=poses[selected][:, [7, 17]].copy(), rope_nodes=nodes[selected].copy(),
            crossings=array(phase["arrays"]["inside_crossings"])[selected].copy()))
        stages.append(dict(index=phase["index"], start_s=phase["start_s"], end_s=phase["end_s"],
                           label=phase["label_en"], binary_sha256=spec["sha256"]))
        previous_time = float(times[-1])
    motion = {name: np.concatenate([piece[name] for piece in pieces]) for name in pieces[0]}
    motion["stages"] = stages
    return motion


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(".external/rope-threading-reference"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    motion = load_motion(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    events = []
    for i in range(1, len(motion["time"])):
        if np.any(motion["equality"][i] != motion["equality"][i-1]):
            events.append(dict(time_s=float(motion["time"][i]), phase=int(motion["phase"][i]),
                               equality_active=motion["equality"][i].tolist()))
    np.savez_compressed(args.output/"reference_motion.npz", **{k: v for k, v in motion.items() if k != "stages"})
    summary = dict(scope="downloaded_reference_only; not a newly executed physical rollout",
        reference_url="https://qinengwang-aiden.github.io/demos/constraint_demos/?demo=threading",
        unique_frames=len(motion["time"]), duration_s=float(motion["time"][-1]),
        stages=motion["stages"], equality_changes=events,
        equality_note="Columns 0/1 are original gripper coupling constraints; columns 2..5 are assisted grasps.",
        grasp_material_nodes=[dict(side="right", node=80, acquire_phase=2, release_phase=24),
            dict(side="left", node=0, acquire_phase=6, release_phase=16),
            dict(side="left", node=77, acquire_phase=20, release_phase=34),
            dict(side="right", node=80, acquire_phase=33, release_phase=42),
            dict(side="left", node=75, acquire_phase=41, release_phase=48),
            dict(side="right", node=80, acquire_phase=46, release_phase=50)])
    (args.output/"reference_summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(f'{summary["unique_frames"]} reference frames, {summary["duration_s"]:.4f} s, {len(events)} equality changes')


if __name__ == "__main__":
    main()
