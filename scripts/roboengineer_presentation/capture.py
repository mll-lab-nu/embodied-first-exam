"""Export verified MuJoCo motion and visual geometry for offline Blender rendering.

This runs only outside the benchmark. It never changes simulation or agent video.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/control_transfer/components"))
sys.path.insert(0, str(ROOT / "scripts/control_transfer"))
os.environ["MUJOCO_GL"] = "osmesa"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
import mujoco  # noqa: E402 — GL environment must precede import
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(name, model, frames, record, source, destination, extra=None):
    extra = dict(extra or {})
    ground_z = extra.pop("ground_z", 0.0)
    assert np.allclose(np.diff([t for t, _ in frames]), 1 / 25, rtol=0, atol=1e-8), (
        "Nonuniform replay timestamps"
    )
    out = destination / name
    out.mkdir(parents=True, exist_ok=False)
    data = mujoco.MjData(model)
    data.qpos[:] = frames[0][1]
    mujoco.mj_forward(model, data)
    geoms, arrays = [], {}
    for g in range(model.ngeom):
        if model.geom_group[g] == 3 or model.geom_rgba[g, 3] < 0.01:
            continue
        kind = int(model.geom_type[g])
        if kind == int(mujoco.mjtGeom.mjGEOM_PLANE):
            continue  # Replaced by a coplanar studio floor in Blender.
        body = int(model.geom_bodyid[g])
        # Existing landing presentation walls are replaced by the common studio.
        if name == "neural-landing" and body == 0:
            continue
        mat = int(model.geom_matid[g])
        mesh = (
            int(model.geom_dataid[g]) if kind == int(mujoco.mjtGeom.mjGEOM_MESH) else -1
        )
        rgba = model.mat_rgba[mat].copy() if mat >= 0 else model.geom_rgba[g].copy()
        if np.any(model.geom_rgba[g] != np.array([0.5, 0.5, 0.5, 1], dtype=np.float32)):
            rgba = model.geom_rgba[g].copy()
        q = np.zeros(4)
        mujoco.mju_mat2Quat(q, data.geom_xmat[g])
        geo = dict(
            id=g,
            name=mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g) or f"geom_{g}",
            body=body,
            kind=kind,
            size=model.geom_size[g].tolist(),
            rgba=rgba.tolist(),
            material=mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MATERIAL, mat)
            if mat >= 0
            else "",
            mesh=mesh,
            position=data.geom_xpos[g].tolist(),
            quaternion=q.tolist(),
        )
        if mesh >= 0:
            va, vn = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
            fa, fn = model.mesh_faceadr[mesh], model.mesh_facenum[mesh]
            arrays[f"vertices_{mesh}"] = model.mesh_vert[va : va + vn]
            arrays[f"faces_{mesh}"] = model.mesh_face[fa : fa + fn]
            ta, tn = model.mesh_texcoordadr[mesh], model.mesh_texcoordnum[mesh]
            if ta >= 0 and tn:
                arrays[f"uv_{mesh}"] = model.mesh_texcoord[ta : ta + tn]
                arrays[f"faceuv_{mesh}"] = model.mesh_facetexcoord[fa : fa + fn]
            if mat >= 0:
                role = int(mujoco.mjtTextureRole.mjTEXROLE_RGB)
                tex = int(model.mat_texid[mat, role])
                if tex >= 0:
                    adr = model.tex_adr[tex]
                    w, h, c = (
                        int(model.tex_width[tex]),
                        int(model.tex_height[tex]),
                        int(model.tex_nchannel[tex]),
                    )
                    texture = model.tex_data[adr : adr + w * h * c].reshape(h, w, c)
                    image = f"texture-{tex}.png"
                    Image.fromarray(texture).save(out / image)
                    geo["texture"] = image
        geoms.append(geo)
    animated = [g["id"] for g in geoms if g["body"] > 0]
    motion = np.zeros((len(frames), len(animated), 7), dtype=np.float64)
    poses = np.zeros((len(frames), model.nq))
    times = []
    for n, (t, pose) in enumerate(frames):
        data.qpos[:] = pose
        data.time = t
        mujoco.mj_forward(model, data)
        times.append(t)
        poses[n] = pose
        for j, g in enumerate(animated):
            motion[n, j, :3] = data.geom_xpos[g]
            mujoco.mju_mat2Quat(motion[n, j, 3:], data.geom_xmat[g])
    np.savez_compressed(out / "geometry.npz", **arrays)
    np.savez_compressed(
        out / "motion.npz", time=times, qpos=poses, geom_ids=animated, transforms=motion
    )
    manifest = dict(
        schema="roboengineer-blender-replay/1",
        name=name,
        fps=25,
        frames=len(frames),
        duration_s=len(frames) / 25,
        geoms=geoms,
        metrics=record["metrics"],
        source_record=str(source),
        source_record_sha256=sha(source),
        original_state_sha256=record.get("state_sha256"),
        qpos_sha256=hashlib.sha256(poses.tobytes()).hexdigest(),
        ground_z=ground_z,
        robot_motion="Exact saved states at 25 Hz; no motion retargeting or physics in Blender",
        presentation_only=True,
        agent_feedback=False,
        **(extra or {}),
    )
    (out / "scene.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(name, len(frames), "frames", len(geoms), "geoms", flush=True)


class Capture:
    def __enter__(self):
        self.original = mujoco.mj_step
        self.frames = []
        self.count = 0
        self.model = None
        self.last_time = -1.0

        def step(model, data, *args, **kwargs):
            self.model = model
            if data.time < self.last_time:
                self.frames = []
                self.count = 0  # Exclude the vehicle reset/settling pre-roll.
            self.last_time = float(data.time)
            if self.count % 20 == 0:
                self.frames.append((float(data.time), data.qpos.copy()))
            self.count += 1
            return self.original(model, data, *args, **kwargs)

        mujoco.mj_step = step
        return self

    def __exit__(self, *args):
        mujoco.mj_step = self.original


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--landing-runs", type=Path, required=True)
    p.add_argument("--assets", type=Path, required=True)
    p.add_argument("--go2-assets", type=Path, required=True)
    p.add_argument("--skydio-assets", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--only", choices=["neural-fly", "neural-landing", "anycar", "g1", "go2"]
    )
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    os.environ["CONTROL_ASSETS"] = str(a.assets)
    os.environ["GO2_ASSET_DIR"] = str(a.go2_assets)

    def selected(n):
        return a.only is None or a.only == n

    if selected("neural-fly"):
        from scripts.control_transfer.neuralfly_visual import render_model
        from scripts.control_transfer.control_public.fly import target

        source = (
            a.evidence / "neuralfly/integration-vector-wind-v1/i00/case-04/record.json"
        )
        record = json.loads(source.read_text())
        state = np.load(source.with_name("trajectory.npz"))["state"]
        model = render_model(a.skydio_assets)
        command = record["scenario"]["trajectory"]
        curve = [
            target(t, **command)[0].tolist()
            for t in np.linspace(0, 2 * np.pi / command["rate"], 240)
        ]
        extra = dict(
            title="Neural Fly",
            subtitle="General figure-eight tracking",
            status="Reference case: success",
            note="Synthetic vector-wind dynamics; Skydio appearance only",
            reference_curve=curve,
            command=command,
            wind_world=np.load(source.with_name("wind.npz"))["velocity_world"][
                ::2
            ].tolist(),
        )
        export(
            "neural-fly",
            model,
            [(r[0], r[1:8]) for r in state[::2]],
            record,
            source,
            a.out,
            extra,
        )
        # MuJoCo's compiled RGB texture drops alpha from the original PNG.
        # Preserve the original, already hash-verified RGBA asset for Blender.
        folder = a.out / "neural-fly"
        visual = json.loads((folder / "scene.json").read_text())
        texture_names = {g["texture"] for g in visual["geoms"] if "texture" in g}
        assert len(texture_names) == 1
        shutil.copyfile(
            a.skydio_assets / "assets/X2_lowpoly_texture_SpinningProps_1024.png",
            folder / texture_names.pop(),
        )
        visual["appearance_note"] = (
            "Original Skydio RGBA texture; translucent rotor material in Blender"
        )
        (folder / "scene.json").write_text(json.dumps(visual, indent=2) + "\n")
    if selected("neural-landing"):
        from scripts.quadrotor_landing.trusted.rendering import scene_xml
        from scripts.quadrotor_landing.public.model import CT
        from scripts.roboengineer_presentation.rotors import landing_rotors

        root = a.landing_runs / "aws-harbor-20261013"
        item = json.loads((root / "final-evaluation-10/manifest.json").read_text())[
            "episodes"
        ][0]
        source = (root / item["source_video"]).with_name("record.json")
        record = json.loads(source.read_text())
        assert sha(source) == item["record_sha256"]
        model = mujoco.MjModel.from_xml_string(scene_xml(record["pad_position"]))
        frames = [
            (r["t"], np.r_[r["position"], r["quaternion"]])
            for r in record["trajectory"][::4]
        ]
        export(
            "neural-landing",
            model,
            frames,
            record,
            source,
            a.out,
            dict(
                title="Neural Landing",
                subtitle="Random-pad precision landing",
                status="Native Harbor reference: success",
                note="Partial Intel Aero calibration; learned residual dynamics",
                pad=record["pad_position"],
                rotor_animation={
                    "revision": "force-driven-rotors/1",
                    "source": "Archived per-motor forces; RPM = sqrt(force / nominal CT)",
                    "thrust_coefficient_N_per_RPM2": CT,
                    "phase": "Integrated at 100 Hz; initial blade phase is cosmetic",
                    "blur": "Cosmetic high-speed disk; 48-sample low-speed blur, 1/50 s exposure",
                    "measured_RPM": False,
                },
            ),
        )
        np.savez_compressed(
            a.out / "neural-landing" / "rotors.npz",
            **landing_rotors(record["trajectory"], [t for t, _ in frames], CT),
        )
    if selected("anycar"):
        from scripts.control_transfer.trusted import anycar
        from scripts.control_transfer.specs import spec
        from scripts.control_transfer.control_public.anycar import reference

        case = spec("anycar-circuit-compact-v3-silverstone-8", 0)["bank"]["held_out"][0]
        source = a.evidence / "anycar/integration-dashed-cones-v1/video/record.json"
        old = json.loads(source.read_text())
        with Capture() as capture:
            record = anycar.rollout(
                a.evidence / "anycar/compact-30s-v1/policy.json",
                case,
                a.out / "anycar-replay",
                False,
            )
        for key in ("state_sha256", "metrics", "feedback"):
            assert record[key] == old[key], key
        command = record["dynamics"]["command"]
        curve = [
            reference(t, command)[:2].tolist() + [0.012]
            for t in np.linspace(0, 28, 400)
        ]
        export(
            "anycar",
            capture.model,
            capture.frames,
            record,
            source,
            a.out,
            dict(
                title="AnyCar",
                subtitle="Multi-surface racing control",
                status="Reference case: full lap completed",
                note="Compact Silverstone-inspired layout; F1TENTH-style appearance",
                reference_curve=curve,
            ),
        )
    if selected("g1"):
        from sim2realbench.g1 import deploy

        source = a.evidence / "g1/schema-v2-trained-bank/i01-case03-steps/record.json"
        old = json.loads(source.read_text())
        with Capture() as capture:
            record = deploy.rollout(
                a.evidence / "g1/training-02/policy.npz",
                out=a.out / "g1-replay",
                render=False,
                plant_seed=old["plant_seed"],
                episode_seed=old["episode_seed"],
                terrain="steps",
                duration=20.0,
                speed=old["command_speed_m_s"],
            )
        for key in ("state_sha256", "metrics", "feedback"):
            assert record[key] == old[key], key
        export(
            "g1",
            capture.model,
            capture.frames,
            record,
            source,
            a.out,
            dict(
                title="Unitree G1",
                subtitle="Blind walking over terrain",
                status="Trained reference: this case succeeds",
                note="Both held-out plant banks remain partially solved",
            ),
        )
    if selected("go2"):
        from scripts.control_transfer.components.quadrupedbench import simulation

        for task, label in [
            ("attitude", "Attitude tracking"),
            ("weave", "Weave-pole navigation"),
            ("forward-jump", "Forward jump"),
            ("yaw-jump", "Yaw jump"),
        ]:
            source = (
                a.evidence / f"robodog/requested-runtime-cpu/{task}/case-00/record.json"
            )
            old = json.loads(source.read_text())
            policy = json.loads(
                source.parent.parent.joinpath("policy.json").read_text()
            )
            with Capture() as capture:
                record = simulation.rollout(
                    policy, old["case"], a.out / f"go2-{task}-replay", False
                )
            for key in ("state_sha256", "metrics", "feedback"):
                assert record[key] == old[key], key
            export(
                "go2-" + task,
                capture.model,
                capture.frames,
                record,
                source,
                a.out,
                dict(
                    title="Unitree Go2",
                    subtitle=label,
                    status="Reference case: success"
                    if record["metrics"]["success"]
                    else "Development reference: target not solved",
                    note="Exact frozen-controller replay; no motion correction",
                    command_spec=old["command_spec"],
                ),
            )


if __name__ == "__main__":
    main()
