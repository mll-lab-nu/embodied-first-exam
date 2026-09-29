#!/usr/bin/env python3
"""Release-grade passive-hold probe of every tier variation, without RGB or video.

Each variation runs from a frozen source snapshot in its own process: rigid
tasks in a parallel CPU pool, FEM/PBD tasks serially on CUDA behind a free
GPU-memory gate. Checks live in tests/release_scene_audit.py; every variation
gets report.json, a Chinese README.md and per-tick ticks.jsonl.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
from record_initial_scenes import catalog, digest, source_files, write_json  # noqa: E402

GPU_TASKS = {"knot_untying", "rope_threading", "slotted_post_ring", "orbits", "blanket_flatten"}
FEM_TASKS = GPU_TASKS - {"blanket_flatten"}
# Blanket's frozen initial state binds the full scene configuration, cameras included.
RGB_TASKS = {"blanket_flatten"}
INFRASTRUCTURE = ("CUDA_ERROR_OUT_OF_MEMORY", "cudaErrorMemoryAllocation", "cudaErrorInvalidDevice",
                  "out of memory", "GPU memory wait timed out")
TIER = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}


def worker(args):
    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tests"))
    from release_scene_audit import ReleaseSceneAudit
    from topogym.simulator import Env, SimulatorConfig
    from topogym.utils.io import to_jsonable
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    report = dict(variation_id=args.variation, task_id=args.task, backend=args.backend, status="running",
                  started_at_utc=datetime.now(timezone.utc).isoformat(), rgb=args.rgb, video=False, actions="none ({})")
    stages = {}
    try:
        t0 = time.monotonic()
        assist = None
        if args.task == "interlocked_claws":
            from topogym.tasks.interlocked_claws.common import recommended_grasp_assist
            assist = recommended_grasp_assist(args.variation, args.seed)
        report["grasp_assist"] = None if assist is None else to_jsonable(assist)
        config = SimulatorConfig(task_id=args.task, variation_id=args.variation, compute_backend=args.backend,
                                 **({} if assist is None else dict(grasp_assist=assist)),
                                 enable_rgb=args.rgb, enable_privileged=True, work_dir=str(out/"scene"),
                                 physics_dt_s=args.physics_dt, solver_substeps=args.substeps,
                                 control_decimation=args.decimation)
        with Env(config) as env:
            env.reset(seed=args.seed)
            stages["build_and_reset_s"] = time.monotonic()-t0
            meta = to_jsonable(env.episode_metadata)
            control_dt = config.physics_dt_s*config.control_decimation
            steps = round(args.seconds/control_dt)
            if not math.isclose(steps*control_dt, args.seconds, abs_tol=1e-9):
                raise ValueError("seconds must be a whole number of control steps")
            audit = ReleaseSceneAudit(env, out, args.seconds, args.window)
            unsubscribe = env.add_state_sink(audit.sample)
            t1 = time.monotonic()
            stopped = None
            for step in range(steps):
                *_, terminated, truncated, info = env.step({})
                if terminated or truncated:
                    stopped = dict(control_step=step+1, terminated=bool(terminated), truncated=bool(truncated),
                                   reason=info.get("termination_reason"), failure_code=info.get("failure_code"))
                    break
            unsubscribe()
            stages["physics_s"] = time.monotonic()-t1
            result = audit.finish()
            report.update(status="passed" if result["passed"] else "failed", episode=dict(
                instance_id=meta["instance_id"], family_id=meta["family_id"], model_revision=meta["model_revision"],
                difficulty_target=meta["difficulty_target"], seed=meta["seed"], robot_id=meta["robot_id"],
                initial_state=meta.get("initial_state"), asset_sha256=meta["asset_sha256"]),
                timing=dict(physics_dt_s=config.physics_dt_s, solver_substeps=config.solver_substeps,
                            control_decimation=config.control_decimation, control_dt_s=control_dt,
                            seconds=args.seconds, window_s=args.window, control_steps=steps),
                robot_pose="Task 声明的初态（Claws：双手已闭合夹住两件；其余任务：机器人 home 姿态）",
                wall_time=dict(stages, seconds_per_simulated_second=stages["physics_s"]/args.seconds),
                episode_stopped_early=stopped, **result)
    except BaseException as error:
        report.update(status="error", error=f"{type(error).__name__}: {error}", traceback=traceback.format_exc(),
                      wall_time=stages)
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(out/"report.json", json.loads(json.dumps(report, default=lambda x: np.asarray(x).tolist())))
    (out/"README.md").write_text(render_case(report))
    return 0 if report["status"] == "passed" else 1


def fmt(value):
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, dict):
        return "；".join(f"{k}={fmt(v)}" for k, v in value.items())
    if isinstance(value, list) and len(value) > 8:
        return f"[{len(value)} 项]"
    return str(value)


def render_case(r):
    lines = [f"# {r['variation_id']}：静置场景测试回执", ""]
    verdict = {"passed": "**通过**", "failed": "**未通过**", "error": "**运行出错**"}.get(r["status"], r["status"])
    lines += [f"结论：{verdict}。", ""]
    if r["status"] == "error":
        lines += ["运行没有完成，下面是错误信息，不代表场景性质。", "", "```", r.get("error", ""), "```", ""]
        return "\n".join(lines)
    e, t = r["episode"], r["timing"]
    lines += ["## 1. 场景", "",
              f"- 任务 `{r['task_id']}`，档位 {e['difficulty_target']}，家族 `{e['family_id']}`，修订 `{e['model_revision']}`，seed {e['seed']}，机器人 `{e['robot_id']}`",
              f"- instance_id `{e['instance_id']}`",
              f"- 任务刚体：{', '.join(r['task_bodies']) or '无'}；软体：{', '.join(f'{k}（{v}）' for k, v in r['soft_bodies'].items()) or '无'}",
              "", "## 2. 怎么跑", "",
              f"- 后端 {r['backend']}，{'RGB 开启仅为匹配冻结初态身份（不取帧、不录视频）' if r['rgb'] else '无 RGB'}、无视频；物理 tick {t['physics_dt_s']*1000:g} ms、{t['solver_substeps']} 个求解子步（积分子步 {t['physics_dt_s']/t['solver_substeps']*1000:.3g} ms），控制周期 {t['control_dt_s']*1000:g} ms；检查点与采样按物理 tick",
              f"- 从 reset 起不施加任何动作（每步 `{{}}`），共 {t['seconds']:g} s（{t['control_steps']} 个控制步）；末窗为最后 {t['window_s']:g} s",
              f"- 机器人：{r['robot_pose']}",
              f"- 辅助抓持：{'无（纯摩擦）' if not r.get('grasp_assist') else 'contact_weld_v1，initial_intent=close（出生时已闭合的双手在双指接触后即焊接）；目标 ' + fmt({t['entity']: t['center_m'] for t in r['grasp_assist']['targets']})}",
              f"- 每个物理 tick 采样一次，共 {r['observed_ticks']} 个；逐 tick 指标见 `ticks.jsonl`",
              f"- 耗时：建场与 reset {r['wall_time'].get('build_and_reset_s', 0):.0f} s，物理 {r['wall_time'].get('physics_s', 0):.0f} s（每模拟秒 {r['wall_time'].get('seconds_per_simulated_second', 0):.0f} s）",
              "", "## 3. 每条检查", "",
              "| 编号 | 检查 | 含义 | 怎么算 | 实测 | 门槛 | 门槛来源 | 结果 |", "|---|---|---|---|---|---|---|---|"]
    for c in r["checks"]:
        lines.append(f"| {c['code']} | {c['name']} | {c['meaning']} | {c['method']} | {fmt(c['measured'])} | "
                     f"{fmt(c['threshold'])} | {c['threshold_source']} | {'通过' if c['passed'] else '**未通过**'} |")
    spawn = r["spawn_motion"]
    if r.get("episode_stopped_early"):
        lines += ["", f"**Episode 提前结束**：{fmt(r['episode_stopped_early'])}；此后不再推进物理，G0 因此不通过。"]
    lines += ["", "## 4. 出生后运动（解释用，不是门槛）", "",
              f"- 前 0.5 s 软体顶点最大位移：{fmt(spawn['first_0_5_s_soft_displacement_max_m'])} m；任务刚体最大位移：{fmt(spawn['first_0_5_s_rigid_displacement_max_m'])} m",
              "- 每 0.1 s 的位移与速度见 `report.json` 的 `motion_profile_every_0_1_s`",
              "", "## 5. 结论与未覆盖范围", "",
              "- " + ("全部检查通过：在无动作静置下，场景保持完整、留在桌面、末窗无明显运动，任务关系未变。" if r["status"] == "passed"
                      else "未通过的检查：" + "、".join(f"{c['code']} {c['name']}" for c in r["checks"] if not c["passed"]) + "。"),
              f"- 未覆盖：{r['scope']}。", ""]
    return "\n".join(lines)


def run_case(item, args, snapshot, env, output):
    case = output/item["variation_id"]
    command = [sys.executable, str(snapshot/"scripts/probe_release_scenes.py"), "--worker",
               "--task", item["task_id"], "--variation", item["variation_id"], "--backend", item["backend"],
               "--seconds", str(item["seconds"]), "--window", str(args.window), "--seed", str(args.seed),
               "--physics-dt", str(item["physics_dt"]), "--substeps", str(item["substeps"]),
               "--decimation", str(item["decimation"]), *(["--rgb"] if item["rgb"] else []), "--output", str(case)]
    item["command"] = command
    log_path = output/f"{item['variation_id']}.{item['attempts']}.log"
    with log_path.open("x") as log:
        process = subprocess.Popen(command, cwd=snapshot, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            code = -1
    text = log_path.read_text(errors="replace")
    report = json.loads((case/"report.json").read_text()) if (case/"report.json").exists() else {}
    item.update(exit_code=code, log=str(log_path.relative_to(output)))
    if report.get("status") in {"passed", "failed"}:
        item.update(status=report["status"], report=str((case/"README.md").relative_to(output)),
                    failed_checks=[c["code"] for c in report["checks"] if not c["passed"]],
                    tightest=tightest(report), wall_s=report["wall_time"])
    elif any(key in text or key in report.get("error", "") for key in INFRASTRUCTURE):
        item.update(status="infrastructure_blocked", error=last_line(report.get("error") or text))
    else:
        item.update(status="error" if code != -1 else "timeout",
                    error=last_line(report.get("error") or text) if code != -1 else f"timeout after {args.timeout:g}s")
    return case


def last_line(text):
    lines = [x for x in str(text).strip().splitlines() if x.strip()]
    return lines[-1][:300] if lines else ""


def tightest(report):
    failing = [c for c in report["checks"] if not c["passed"]]
    pick = failing[0] if failing else next((c for c in report["checks"] if c["code"] in {"G5", "G3b", "G3a"}), None)
    return None if pick is None else f"{pick['code']} {pick['name']}：{fmt(pick['measured'])}（门槛 {fmt(pick['threshold'])}）"


def gpu_free_mib():
    probe = subprocess.run(["nvidia-smi", "--id=0", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True)
    return int(probe.stdout.strip()) if probe.returncode == 0 else 0


def render_summary(summary):
    rows = summary["results"]
    count = {s: sum(r["status"] == s for r in rows) for s in ("passed", "failed", "infrastructure_blocked", "error", "timeout", "pending", "running")}
    lines = ["# 发布前 39 档静置场景测试（无视频）", "",
             f"开始 {summary['started_at_utc']}；源码快照 `source_snapshot/`（哈希见 `source_hashes.json`）。",
             "每档从 reset 起不施加动作静置，逐物理 tick 检查 G0–G5；检查的含义、算法、门槛与来源写在每档回执里。",
             "发布门槛按用户 09-29 的要求忽略小幅摆动和粒子级噪声（软体用 p95 而非最大值）。", "",
             "计数：" + "，".join(f"{k} {v}" for k, v in count.items() if v), "",
             "| 任务 | 档位 | 变体 | 后端 / tick | 时长 | 结果 | 未通过的检查 | 最紧的一项 / 错误 | 回执 |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        status = {"passed": "通过", "failed": "**未通过**", "infrastructure_blocked": "基础设施受阻",
                  "error": "**运行出错**", "timeout": "**超时**"}.get(r["status"], r["status"])
        link = f"[README]({r['report']})" if r.get("report") else (f"[log]({r['log']})" if r.get("log") else "")
        lines.append(f"| {r['task_id']} | {TIER.get(r['difficulty'], r['difficulty'])} | `{r['variation_id']}` | {r.get('backend', '')} / {r.get('physics_dt', .0025)*1000:g} ms×{r.get('substeps', 4)} | "
                     f"{r.get('seconds', '')} s | {status} | {', '.join(r.get('failed_checks', [])) or ''} | "
                     f"{r.get('tightest') or r.get('error') or ''} | {link} |")
    return "\n".join(lines)+"\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variations", nargs="+")
    parser.add_argument("--rigid-seconds", type=float, default=3.)
    parser.add_argument("--claws-seconds", type=float, default=5.)
    parser.add_argument("--soft-seconds", type=float, default=3.)
    parser.add_argument("--fem-seconds", type=float, default=2.)
    parser.add_argument("--fem-timing", type=float, nargs=3, default=(.025, 40, 1), metavar=("DT", "SUBSTEPS", "DECIMATION"),
                        help="FEM tasks: same 0.625 ms integration substep as the default, checkpoints/samples at 40 Hz")
    parser.add_argument("--window", type=float, default=1.)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--cpu-workers", type=int, default=8)
    parser.add_argument("--gpu-min-free-mib", type=int, default=10240)
    parser.add_argument("--gpu-wait", type=float, default=3600, help="Max seconds to wait for GPU memory per case")
    parser.add_argument("--gpu-gap", type=float, default=0., help="Idle seconds after each GPU case, leaving the card to other sessions")
    parser.add_argument("--timeout", type=float, default=14400)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--task", help=argparse.SUPPRESS)
    parser.add_argument("--variation", help=argparse.SUPPRESS)
    parser.add_argument("--backend", choices=("cpu", "cuda"), help=argparse.SUPPRESS)
    parser.add_argument("--seconds", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--physics-dt", type=float, default=.0025, help=argparse.SUPPRESS)
    parser.add_argument("--substeps", type=int, default=4, help=argparse.SUPPRESS)
    parser.add_argument("--decimation", type=int, default=10, help=argparse.SUPPRESS)
    parser.add_argument("--rgb", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output/"source_snapshot"
    hashes = {}
    for path in source_files(ROOT):
        target = snapshot/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        hashes[str(path.relative_to(ROOT))] = digest(target)
    write_json(output/"source_hashes.json", hashes)
    rows = [r for r in catalog(snapshot) if r["pool"] == "tier" and r["status"] == "integrated"]
    if args.variations:
        rows = [r for r in rows if r["variation_id"] in args.variations]
    items = []
    for r in rows:
        gpu, fem = r["task_id"] in GPU_TASKS, r["task_id"] in FEM_TASKS
        seconds = (args.fem_seconds if fem else args.soft_seconds if gpu
                   else args.claws_seconds if r["task_id"] == "interlocked_claws" else args.rigid_seconds)
        dt, substeps, decimation = args.fem_timing if fem else (.0025, 4, 10)
        items.append(dict(task_id=r["task_id"], difficulty=r["difficulty"], variation_id=r["variation_id"],
                          backend="cuda" if gpu else "cpu", seconds=seconds, physics_dt=dt, substeps=int(substeps),
                          decimation=int(decimation), rgb=r["task_id"] in RGB_TASKS, status="pending", attempts=0))
    items.sort(key=lambda i: (i["task_id"] in FEM_TASKS, i["task_id"]))
    summary = dict(started_at_utc=datetime.now(timezone.utc).isoformat(), results=items,
                   settings={k: v for k, v in vars(args).items() if k not in {"worker", "task", "variation", "backend", "seconds"}})
    lock = threading.Lock()

    def publish():
        with lock:
            write_json(output/"summary.json", json.loads(json.dumps(summary, default=str)))
            (output/"README.md").write_text(render_summary(summary))

    publish()
    if args.dry_run:
        return 0
    env = dict(os.environ, PYTHONPATH=str(snapshot)+os.pathsep+str(snapshot/"tests"),
               TOPOGYM_ASSET_ROOT=str(ROOT/"assets"), OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
               MKL_NUM_THREADS="1", PYOPENGL_PLATFORM="egl")
    gpu_queue = [i for i in items if i["backend"] == "cuda"]

    def cpu_job(item):
        item.update(status="running", attempts=item["attempts"]+1)
        publish()
        run_case(item, args, snapshot, env, output)
        if item["status"] == "error" and "cuda" in (item.get("error") or "").lower():
            # CPU backend unsupported for this Task: move it to the CUDA queue.
            shutil.move(str(output/item["variation_id"]), str(output/f"{item['variation_id']}.cpu_attempt"))
            item.update(backend="cuda", status="pending", cpu_fallback_reason=item["error"])
            with lock:
                gpu_queue.append(item)
        publish()
        print(item["variation_id"], item["status"], flush=True)

    def gpu_loop(cpu_done):
        while True:
            with lock:
                item = next((i for i in gpu_queue if i["status"] == "pending"), None)
            if item is None:
                if cpu_done.is_set():
                    return
                time.sleep(5)
                continue
            deadline = time.monotonic()+args.gpu_wait
            while (free := gpu_free_mib()) < args.gpu_min_free_mib and time.monotonic() < deadline:
                item["gpu_wait"] = dict(free_mib=free, required_mib=args.gpu_min_free_mib)
                publish()
                time.sleep(15)
            if gpu_free_mib() < args.gpu_min_free_mib:
                item.update(status="infrastructure_blocked", error="GPU memory wait timed out; no simulator started")
                publish()
                continue
            item.update(status="running", attempts=item["attempts"]+1)
            publish()
            case = run_case(item, args, snapshot, env, output)
            if item["status"] == "infrastructure_blocked" and item["attempts"] < 2:
                if case.exists():
                    shutil.move(str(case), str(output/f"{item['variation_id']}.attempt{item['attempts']}"))
                item["status"] = "pending"
                time.sleep(60)
            publish()
            print(item["variation_id"], item["status"], flush=True)
            time.sleep(args.gpu_gap)

    cpu_done = threading.Event()
    gpu_thread = threading.Thread(target=gpu_loop, args=(cpu_done,))
    gpu_thread.start()
    with ThreadPoolExecutor(max_workers=args.cpu_workers) as pool:
        list(pool.map(cpu_job, [i for i in items if i["backend"] == "cpu"]))
    cpu_done.set()
    gpu_thread.join()
    current = {str(p.relative_to(ROOT)): digest(p) for p in source_files(ROOT)}
    summary.update(finished_at_utc=datetime.now(timezone.utc).isoformat(),
                   source_changed_during_run=[n for n, h in hashes.items() if current.get(n) != h])
    publish()
    return int(any(i["status"] != "passed" for i in items))


if __name__ == "__main__":
    raise SystemExit(main())
