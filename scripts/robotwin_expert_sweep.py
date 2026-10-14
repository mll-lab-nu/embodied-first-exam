"""RoboTwin expert seed sweep (run inside the rcb-robotwin container with the UNSCRUBBED upstream envs/ bind-mounted):
  docker run --rm --gpus all -v $PWD/tasks/robotwin_2_0_stack_blocks_two-privileged:/task -v $PWD/scripts:/scripts \\
    -v $PWD/third_party/RoboTwin/envs:/opt/RoboTwin/envs:ro ghcr.io/mll-lab-nu/eai-robotwin:0.1.2 \\
    bash -c "cd /opt/RoboTwin && python /scripts/robotwin_expert_sweep.py task1,task2 60417,28831 /tmp/results.json"
for each candidate task and seed, build the scene, run the upstream play_once through the
Session hook (so it is recorded), check success, replay once for determinism. Upstream envs/ is bind-mounted."""
import json, sys, time, traceback
sys.path.insert(0, "/task/environment")
from rcb_traj import Session
tasks = sys.argv[1].split(","); seeds = [int(x) for x in sys.argv[2].split(",")]; out = sys.argv[3]
res = json.load(open(out)) if __import__("os").path.exists(out) else {}
for task in tasks:
    res.setdefault(task, {})
    for seed in seeds:
        if str(seed) in res[task]: continue
        t0 = time.time(); r = {"seed": seed}
        try:
            s = Session(task, seed=seed)
            s.record_start(); ex = s.exec_code("env.play_once()\nassert env.plan_success, 'plan failed'"); acts = s.record_stop()
            live = s.status(); r.update(exec=ex, live_success=live["success"], n_actions=int(len(acts)))
            if live["success"]:
                rep = s.replay(acts); r.update(replay_success=rep["success"], deterministic=rep["state_sha"] == live["state_sha"])
            s.close()
        except Exception as e:  # noqa
            r["error"] = repr(e)[:300]
        r["wall_s"] = round(time.time() - t0, 1)
        res[task][str(seed)] = r
        json.dump(res, open(out, "w"), indent=1)
        print(task, seed, {k: v for k, v in r.items() if k != "exec"}, flush=True)
