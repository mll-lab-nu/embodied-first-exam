"""Shared read-only-history rendering for complete rigid articulation records.

Only a disposable owner Env is mutated. No physics is integrated and no new
task success is asserted. Every selected frame checks all restored link poses.
"""
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.recording.session import RecordingSession
from topogym.recording.segment import save_rgb
from topogym.recording.encoding import probe
from topogym.utils.arrays import to_numpy
from topogym.utils.io import write_json_atomic


def record_rigid_history(env, states, output, *, metadata, fps=30., pose_tolerance_m=1e-6):
    """Restore recorded joint coordinates; write the standard rig through RecordingSession.

    `states` yields complete Env tick_record dictionaries in birth-to-end order.
    Particle/FEM scenes and incomplete joint coordinate records are rejected.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(status="running", physics_integrated=False, source_rows=0, rendered_states=0,
                  maximum_link_position_error_m=0., maximum_link_rotation_error_rad=0.)
    identity = previous = last = final_frame = None
    next_time = 0.
    last_rendered_id = None

    def render(row, recording):
        nonlocal final_frame, last_rendered_id
        world = row["world"]
        if world["particles"] or world["fem"]:
            raise ValueError("Rigid replay cannot restore deformable state")
        for name, articulation in world["articulations"].items():
            entity = env._world.entities[name]
            if not entity.n_qs:
                continue
            coordinates = np.empty(entity.n_qs)
            covered = np.zeros(entity.n_qs, dtype=bool)
            for joint in entity.joints:
                indices = list(joint.qs_idx_local)
                if not indices:
                    continue
                value = np.asarray(articulation["joints"][joint.name]["position"], dtype=float)
                if value.shape != (len(indices),):
                    raise ValueError("Incomplete joint coordinates: " + name + "/" + joint.name)
                coordinates[indices] = value
                covered[indices] = True
            if not covered.all() or not np.isfinite(coordinates).all():
                raise ValueError("Incomplete articulation coordinates: " + name)
            entity.set_qpos(coordinates, zero_velocity=True)
        # Read native FK after restoration; neither the task nor history is updated.
        for name, articulation in world["articulations"].items():
            for link in env._world.entities[name].links:
                expected = articulation["links"][link.name]
                position = to_numpy(link.get_pos()).reshape(3)
                quaternion = to_numpy(link.get_quat()).reshape(4)
                error = float(np.linalg.norm(position - expected["position_m"]))
                rotation = float((Rotation.from_quat(quaternion[[1, 2, 3, 0]])
                    * Rotation.from_quat(np.asarray(expected["quaternion_wxyz"])[[1, 2, 3, 0]]).inv()).magnitude())
                report["maximum_link_position_error_m"] = max(report["maximum_link_position_error_m"], error)
                report["maximum_link_rotation_error_rad"] = max(report["maximum_link_rotation_error_rad"], rotation)
                if error > pose_tolerance_m or rotation > 1e-5:
                    raise ValueError(f"Restored link differs: {name}/{link.name}: {error} m, {rotation} rad")
        # Native FK setters do not advance scene.t. Refresh the visual geometry
        # explicitly before Nyx reads its shared render buffers at the same tick.
        env._world.scene.visualizer.update_visual_states(force_render=True)
        env._sensors.invalidate()
        sampled = env.sensor_frame()
        state = row["state"]
        final_frame = replace(sampled, episode_id=state["episode_id"], branch_id=state["branch_id"],
            state_id=state["state_id"], physics_step=state["physics_step"], sim_time_s=state["sim_time_s"])
        recording.append(final_frame)
        last_rendered_id = state["state_id"]
        report["rendered_states"] += 1
        if report["rendered_states"] == 1:
            report["initial_frames"] = save_rgb(output, "initial", final_frame)
        if report["rendered_states"] % 100 == 0:
            report["source_sim_time_s"] = state["sim_time_s"]
            write_json_atomic(output / "render_report.json", report)

    try:
        with RecordingSession(output / "recording", fps=fps, metadata=dict(metadata,
                mode="saved_rigid_state_rerender", physics_integrated=False,
                interpolated_states=False, reconstruction="all recorded joints, including passive gripper joints")) as recording:
            for row in states:
                state = row["state"]
                if identity is None:
                    identity = state["episode_id"]
                    if state["physics_step"] != 0 or state["branch_id"] != 0:
                        raise ValueError("Source must begin at episode birth")
                elif (state["episode_id"] != identity or state["branch_id"] != 0
                      or state["physics_step"] != previous["physics_step"] + 1
                      or state["parent_state_id"] != previous["state_id"]):
                    raise ValueError("Source is not one continuous episode")
                previous, last = state, row
                report["source_rows"] += 1
                if state["sim_time_s"] + 1e-10 >= next_time:
                    render(row, recording)
                    next_time = (int(np.floor(state["sim_time_s"] * fps + 1e-8)) + 1) / fps
            if last is None:
                raise ValueError("Empty source history")
            if last_rendered_id != last["state"]["state_id"]:
                render(last, recording)
            recording.append_final(final_frame)
            report["final_frames"] = save_rgb(output, "final", final_frame)
            report["source_sim_time_s"] = last["state"]["sim_time_s"]
            report["source_task_success"] = last["task"]["result"]["task_success"]
            recording.finish(dict(source_task_success=report["source_task_success"], physics_integrated=False))
        report["videos"] = {p.stem: dict(path=str(p.relative_to(output)), **probe(p))
                            for p in sorted((output / "recording/videos").glob("*.mp4"))}
        report["status"] = "passed"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        write_json_atomic(output / "render_report.json", report)
    return report
