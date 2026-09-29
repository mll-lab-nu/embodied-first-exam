"""Publish standalone native Harbor tasks from this TopoGym checkout."""
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tarfile
import tempfile

from .catalog import instances
from .evidence import digest, write_json

LIGHT_IMAGE = "python:3.11.15-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3"

CLIENT_GUIDE = '''# Robot service
Run Python in this container; import `Robot` from `topogym_client`.
`r = Robot()` waits for the simulator. `r.spec()` describes the robot and cameras.
`obs = r.get_obs(depth="last")` reads RGB, calibrated depth and measured joints.
`obs.group("joint_pos")`, `obs.group("tcp_pose")`, `obs.last`, `obs.last_depth`,
`obs.frames`, `obs.video`, `obs.frame_step`, `obs.frame_time_s`, `obs.extrinsic_cv`
contain the returned observations. `obs.save("/app/output/observation")` saves them.
`r.submit("joint_position", actions, dt=1/r.spec()["control_hz"], video="both")`
takes a float32 T by action-dimension array. Read its layout and limits in spec.
`ee_pose` accepts world xyz/wxyz and the native gripper coordinate for each arm.
Rows may be at most 0.5 seconds apart and a chunk at most 10 seconds.
`get_obs(seconds=1)` watches while holding the last command. This advances physics.
`r.fk(q, links=...)`, `r.ik(targets, seed=...)` only query the robot model.
Depth modes: none, last, frames; legacy include_depth=True remains accepted.
Video modes: mp4, frames, both, none. Unknown camera names are skipped.
Every returned frame has matching proprioception, step/time and camera pose.
RGB uses Nyx. Depth is geometric z-depth at the same calibrated camera rig;
it may differ at transparent surfaces. Invalid depth is zero. No depth noise.
Do not retry an action after a connection loss: it may already have executed.
One trial is one episode; there is no reset or privileged scene API.
Wall clock is the budget. Actions, physics steps and simulated time are costs.
Success or a task failure ends the episode. Observations/kinematics still work.
The service records your executed actions; no submission file is needed.
'''

UNLIMITED_GUIDE = '''# Frozen-instance Session
Use `from topogym.benchmark.session import Session` and
`with Session("/app/instance.json") as s:`. `s.spec` describes actions/cameras.
`s.get_obs(...)` and `s.submit(type, actions, dt=..., ...)` match the Robot API.
`s.state()` returns privileged state. `s.kinematics({...})` queries the robot.
`s.reset()` rebuilds the SAME frozen instance and starts a new candidate trajectory.
`s.save("/app/output/trajectory.npz")` publishes the current candidate.
You may inspect simulator source and create your own controller. Record every
physical action through this Session. The verifier replays the saved joint targets
in two fresh processes. Editing task code, changing the seed, teleporting objects,
or writing a success flag cannot alter the verifier's simulator or frozen inputs.
The wall-clock budget includes your experiments and resets. No fixed step budget.
'''


def runtime_bundle(project, destination):
    """Copy our runtime only; never import or package another repository."""
    project = Path(project)
    excluded = {"agents","planning","data","__pycache__","deferred","legacy","redundants","rollout_simulation"}
    manifest = {}
    with tarfile.open(destination,"w:gz",compresslevel=6) as archive:
        for path in sorted((project/"topogym").rglob("*")):
            rel = path.relative_to(project)
            if not path.is_file() or set(rel.parts)&excluded or path.suffix in {".pyc",".md"}:
                continue
            if path.is_symlink():
                raise ValueError(f"Runtime source may not be a symlink: {rel}")
            data = path.read_bytes()
            if rel.as_posix() == "topogym/assets/geometry/cast_coil.py":
                # Authoring synthesis embeds a reference motion. Runtime tasks
                # build frozen geometry from templates and never call it.
                source = data.decode()
                tree = ast.parse(source)
                for node in tree.body:
                    if isinstance(node,ast.FunctionDef) and node.name == "synthesize":
                        lines = source.splitlines(keepends=True)
                        data = ("".join(lines[:node.lineno-1])+"".join(lines[node.end_lineno:])).encode()
            if rel.as_posix() == "topogym/simulator/__init__.py":
                data = b'from .config import SimulatorConfig\nfrom .api import env_list, make\nfrom .history import StateRef\ndef __getattr__(name):\n    if name == "Env":\n        from .env import Env\n        return Env\n    raise AttributeError(name)\n'
            info = tarfile.TarInfo(rel.as_posix())
            info.size,info.mode,info.mtime = len(data),0o644,0
            archive.addfile(info,io.BytesIO(data))
            manifest[rel.as_posix()] = hashlib.sha256(data).hexdigest()
    return manifest


def _runtime_docker(image, *, instance="instance.json", command=None):
    result = f'''FROM {image}
ADD runtime.tar.gz /opt/task/
COPY {instance} /app/instance.json
WORKDIR /app
ENV PYTHONPATH=/opt/task PYTHONUNBUFFERED=1
RUN mkdir -p /app/output /data /logs/verifier
'''
    if command:
        result += "CMD "+json.dumps(command)+"\n"
    return result


def _gpu():
    return dict(runtime="nvidia",shm_size="2gb",environment={"NVIDIA_DRIVER_CAPABILITIES":"all"},
        deploy=dict(resources=dict(reservations=dict(devices=[dict(driver="nvidia",count=1,capabilities=["gpu"])]))))


def export(project, output, *, task=None, mode="both", all_variants=False, seeds=(0,), image="topogym-simulator:20260929", instance_file=None):
    import toml
    import yaml
    from harbor.models.dataset.manifest import DatasetManifest
    from harbor.models.task.config import TaskConfig
    from harbor.publisher.packager import Packager
    project,output = Path(project).resolve(),Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Export destination must be new: {output}")
    if not re.fullmatch(r"[a-zA-Z0-9._/:@-]+",image) or ":" not in image or image.endswith(":latest"):
        raise ValueError("Use a tagged or digest-pinned simulator image")
    if instance_file is None:
        selected,excluded = instances(task=task,all_variants=all_variants,seeds=seeds)
    else:
        if task is not None or all_variants or tuple(seeds)!=(0,):
            raise ValueError("Instance files specify their own task, variation and seed")
        from topogym.simulator.config import SimulatorConfig
        document=yaml.safe_load(Path(instance_file).read_text())
        selected=document if isinstance(document,list) else [document]
        excluded=[]
        for item in selected:
            if not isinstance(item,dict) or set(item)-{"name","instruction","simulator","wall_clock_s","replay_timeout_s","startup_timeout_s","fixture"}:
                raise ValueError("Invalid instance file fields")
            if not isinstance(item.get("instruction"),str) or not item["instruction"].strip():
                raise ValueError("A public task instruction is required")
            config=SimulatorConfig(**item["simulator"])
            if config.seed is None or config.max_physics_steps is not None or config.control_mode!="JOINT_ABS" or config.history_storage!="disk":
                raise ValueError("Use a frozen seed, JOINT_ABS, history_storage=disk and max_physics_steps=null")
            if config.asset_root is not None or config.work_dir is not None:
                raise ValueError("Portable tasks cannot embed host asset_root/work_dir paths")
            item.setdefault("wall_clock_s",5400)
            if not isinstance(item["wall_clock_s"],(int,float)) or not 0<item["wall_clock_s"]<float("inf"):
                raise ValueError("wall_clock_s must be finite and positive")
    modes = ("limited","unlimited") if mode == "both" else (mode,)
    if not set(modes) <= {"limited","unlimited"}:
        raise ValueError("Invalid mode")
    output.parent.mkdir(parents=True,exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".harbor-export-",dir=output.parent))
    try:
        runtime = staging/"runtime.tar.gz"
        source_manifest = runtime_bundle(project,runtime)
        coverage,dataset = [],[]
        for selected_instance in selected:
            for chosen in modes:
                instance = dict(selected_instance,mode=chosen,source_sha256=digest(source_manifest),runtime_image=image)
                name = instance["name"]+"-"+chosen
                if not re.fullmatch(r"[a-zA-Z0-9_-]+",name):
                    raise ValueError("Unsafe generated task name")
                directory = staging/name
                environment,tests,solution = [directory/p for p in ("environment","tests","solution")]
                for folder in (environment,tests,solution):
                    folder.mkdir(parents=True)
                write_json(directory/"source-manifest.json",source_manifest)
                # Harbor packages tests/ but not arbitrary files at the task root.
                write_json(tests/"source-manifest.json",source_manifest)
                write_json(tests/"instance.json",instance)
                shutil.copyfile(runtime,tests/"runtime.tar.gz")
                guide = CLIENT_GUIDE if chosen == "limited" else UNLIMITED_GUIDE
                (directory/"instruction.md").write_text(instance["instruction"]+"\n\n"+guide)
                (directory/"README.md").write_text(f"# {name}\n\nNative Harbor trajectory task. Protocol rcb-limited/2.2.\n"+
                    "Generated from an independent TopoGym runtime snapshot. See source-manifest.json.\n"+
                    "Exported is not a claim of physics, replay or oracle qualification.\n")
                (solution/"solve.sh").write_text("#!/bin/sh\n# This task has no qualified oracle yet. Fail explicitly.\necho 'Oracle is not qualified for this instance' >&2\nexit 2\n")
                spec = dict(schema_version="1.4",task=dict(name="topogym/"+name,description=instance["instruction"],authors=[dict(name="TopoGym")]),
                    metadata=dict(simulator="topogym",family=instance["simulator"]["task_id"],mode=chosen,protocol="rcb-limited/2.2",
                        task_type="trajectory",tier="perception" if chosen == "limited" else "privileged",oracle_qualified=False),
                    agent=dict(timeout_sec=instance["wall_clock_s"]),environment=dict(cpus=4,memory_mb=16384,build_timeout_sec=1800,workdir="/app"),
                    verifier=dict(environment_mode="separate",network_mode="no-network",timeout_sec=7500),artifacts=[dict(source="/app/output/")])
                if chosen == "limited":
                    shutil.copyfile(project/"topogym/benchmark/client.py",environment/"topogym_client.py")
                    shutil.copyfile(project/"topogym/benchmark/wire.py",environment/"topogym_wire.py")
                    (environment/"API.md").write_text(CLIENT_GUIDE)
                    (environment/"Dockerfile").write_text(f'''FROM {LIGHT_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends bash curl git ca-certificates ripgrep ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy==2.3.5 pillow==11.3.0
WORKDIR /app
COPY topogym_client.py topogym_wire.py API.md /app/
RUN mkdir -p /app/output
ENV PYTHONPATH=/app
CMD ["sleep", "infinity"]
''')
                    sim = environment/"sim"
                    sim.mkdir()
                    shutil.copyfile(runtime,sim/"runtime.tar.gz")
                    write_json(sim/"instance.json",instance)
                    (sim/"Dockerfile").write_text(_runtime_docker(image,command=["python","-m","topogym.benchmark","serve","/app/instance.json","/data","--stay"]))
                    compose = dict(services=dict(main=dict(depends_on=["sim"]),sim=dict(build=dict(context="./sim"),**_gpu())))
                    spec["artifacts"].append(dict(source="/data",service="sim",exclude=["*/topogym-history-*","*.tmp"]))
                    spec["verifier"]["collect"] = [dict(service="sim",command="python -m topogym.benchmark collect /data --timeout 7400",timeout_sec=7450)]
                    (tests/"Dockerfile").write_text(f'''FROM {LIGHT_IMAGE}
RUN pip install --no-cache-dir numpy==2.3.5
ADD runtime.tar.gz /opt/task/
COPY instance.json /tests/instance.json
COPY --chmod=755 test.sh /tests/test.sh
ENV PYTHONPATH=/opt/task
WORKDIR /tests
''')
                    verifier_command = "python -m topogym.benchmark grade /tests/instance.json /data /logs/verifier"
                else:
                    shutil.copyfile(runtime,environment/"runtime.tar.gz")
                    write_json(environment/"instance.json",instance)
                    (environment/"Dockerfile").write_text(_runtime_docker(image,command=["sleep","infinity"]))
                    (environment/"API.md").write_text(UNLIMITED_GUIDE)
                    compose = dict(services=dict(main=_gpu()))
                    (tests/"Dockerfile").write_text(_runtime_docker(image)+
                        "COPY instance.json /tests/instance.json\nCOPY --chmod=755 test.sh /tests/test.sh\n")
                    (tests/"docker-compose.yaml").write_text(yaml.safe_dump(dict(services=dict(main=_gpu())),sort_keys=False))
                    verifier_command = "python -m topogym.benchmark verify /tests/instance.json /app/output/trajectory.npz /trusted-evidence /logs/verifier"
                (environment/"docker-compose.yaml").write_text(yaml.safe_dump(compose,sort_keys=False))
                (tests/"test.sh").write_text("#!/bin/sh\nset -eu\n"+verifier_command+"\n")
                (tests/"test.sh").chmod(0o755)
                (solution/"solve.sh").chmod(0o755)
                TaskConfig.model_validate(spec)
                (directory/"task.toml").write_text(toml.dumps(spec))
                content_hash,_ = Packager.compute_content_hash(directory)
                dataset.append(dict(name=spec["task"]["name"],digest="sha256:"+content_hash))
                coverage.append(dict(task=instance["simulator"]["task_id"],variation=instance["simulator"]["variation_id"],seed=instance["simulator"]["seed"],mode=chosen,
                    path=name,exported=True,protocol_passed=False,replay_passed=False,oracle_passed=False,scoring_eligible=False))
        runtime.unlink()
        manifest = DatasetManifest.model_validate(dict(
            dataset=dict(name="topogym/development",version="20260929",
                description="Development tasks; export does not imply protocol, replay or oracle qualification.",
                authors=[dict(name="TopoGym")]),tasks=dataset))
        (staging/"dataset.toml").write_text(manifest.to_toml())
        write_json(staging/"coverage.json",dict(instances=coverage,excluded=excluded))
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return output
