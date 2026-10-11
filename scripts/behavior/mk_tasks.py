#!/usr/bin/env python3
"""Generate the BEHAVIOR-1K tasks: tasks/behavior-<family>-i00-privileged/ and tasks/behavior-<family>-i00-standard/
(eai-standard/2.2) for every family of families.json with "include": true (docs/benchmarks/behavior.md).

usage: python3 scripts/behavior/mk_tasks.py [family ...]            # default: every included family
       python3 scripts/behavior/mk_tasks.py --check [family ...]    # generate into a temporary tree, diff against tasks/

Sources (everything a rerun needs; a rerun reproduces the committed tasks, `git status` stays clean):
- the template twins tasks/behavior-picking-up-trash-i00-{privileged,standard}/, maintained by hand (Dockerfiles,
  compose files, tooling, sidecar adapter, graders, instructions): every other family is a copy with its own texts,
  instance and solution; the template twins themselves only get their copies, oracle lines and README refreshed;
- scripts/eai_standard/ (the eai-standard/2.2 layer, PROTOCOL D9): rcb_limited.py, rcb1.py, run.sh into
  environment/sim/, rcb_client.py, rcb1.py and the client's pip pins client-requirements.txt into environment/ of every
  standard task, byte-identical; the agent's and the verifier's FROM is client.env's CLIENT_IMAGE;
- scripts/behavior/families.json: per family the goal texts (privileged: goal, success conditions, difficulty, objects,
  note; standard: the goal in words, the closing paragraph), the scene, the oracle level with its evidence, and either the
  cited positive (trial, batch, version, results-site log, Hugging Face replay) or, for the supplementary families without
  one, the 2026 challenge's official human demonstrations (`demo`: video, its duration, episodes, mean duration); `added`
  (optional) is the date of the pull request that added a supplementary family after the first 50 (default 2026-10-04): the
  evidence and the README of those families cite that pull request's human review, REVIEW_PR below unless the family has its
  own `review_pr`: a pull request number, or a batch name that REVIEW_PRS below resolves (the third batch: THIRD_BATCH_PR);
- scripts/behavior/bddl/<family>.bddl: the task's BDDL problem (its :goal block is quoted in the privileged instruction;
  goal.py words the predicates it uses), as in the image's /behavior-src/bddl3/bddl/activity_definitions/<family>/problem0.bddl;
- scripts/behavior/instances/<family>.json: the frozen instance (2026 challenge public_test instance 301 and its state
  hash), copied unchanged into environment/, tests/ and the standard sidecar;
- scripts/behavior/solutions/<family>/{privileged,standard}/: a reference solution where one was written (the template's
  is in its own solution/); families without one declare oracle = "none" and get no solution/ (PROTOCOL §2.7).
The oracle level of every task (template twins included) comes from families.json: "full" only when a recorded oracle run
scored 1 on a byte-identical grader, frozen instance and oracle code, with every tooling change since off the oracle and
replay path; "partial" with the per-mode "oracle_evidence" otherwise; "none" with the cited positive, or with the official
human demonstrations where no positive exists yet (those tasks are reported separately, PROTOCOL §7 open item 4).
Every task's README is written here in the protocol's layout (title, key table, Task, Difficulty, Reference solution,
Verification, Details) and every task ends with scripts/task_conventions.py's normalize(), as every generator's does.
Agent results are not in the repository (PROTOCOL D3): the positives are cited by trial id and links. Families with
"include": false stay in families.json (their inputs are kept) but are not generated.

A new family: its BDDL problem into bddl/, an entry in families.json, then freeze its instance in the GPU container
(dataset mounted read-only), e.g.
  docker run --rm --gpus all --shm-size 8g -v $RCB_BEHAVIOR_DATA:/data:ro \
    -v $PWD/tasks/behavior-picking-up-trash-i00-privileged:/t:ro -v $PWD/scripts/behavior/instances:/o \
    ghcr.io/mll-lab-nu/eai-behavior:0.1.1 bash -c \
    "cd /tmp && python /t/environment/rcb_behavior.py make-instance --task <family> --instance-id 301 \
     --robot-config /t/environment/r1pro_primitives_eval.yaml --out /o/<family>.json"
(the family must be registered in the tooling's TASKS, environment/rcb_behavior.py of the template, which every task
copies), then run this script, `harbor run -a nop` on both twins (and `-a oracle` with a reference solution), and
`cd tasks && harbor add --scan .`."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True                      # no __pycache__ next to the sources
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(ROOT / "scripts"))
import goal as G  # noqa: E402
from task_conventions import normalize  # noqa: E402

TEMPLATE = "picking_up_trash"
LAYER = {"environment/sim/rcb_limited.py": "rcb_limited.py", "environment/sim/rcb1.py": "rcb1.py", "environment/sim/run.sh": "run.sh",
         "environment/rcb_client.py": "rcb_client.py", "environment/rcb1.py": "rcb1.py",
         "environment/client-requirements.txt": "client-requirements.txt"}           # the client's pip pins (client.env)
TOOLING = ("rcb_behavior.py", "r1pro_primitives_eval.yaml")     # the privileged environment/ copies are the source
IMAGE = "ghcr.io/mll-lab-nu/eai-behavior:0.1.1"
# the pull request whose human review covers the families with an `added` date (PROTOCOL §2.7), unless a family names its own
# `review_pr` in families.json: a pull request number, or a batch name resolved by REVIEW_PRS. REVIEW_PR is the second batch's
# (the 16 families of 2026-10-07); THIRD_BATCH_PR is the pull request of the 23 families that completed the challenge's 100
# (`"review_pr": "third_batch"`): "TBD" until it exists, then set it here (the one place), rerun this script and
# `cd tasks && harbor add --scan .` (the README and task.toml of those 46 directories change, hence their digests).
REVIEW_PR = "71"
THIRD_BATCH_PR = "75"
REVIEW_PRS = {"third_batch": THIRD_BATCH_PR}
NO_ORACLE = ("No oracle: the family is reviewed by a maintainer (PROTOCOL §2.7) in the pull request that adds it, on a positive "
             "example and a `nop` run per mode.")
PARTIAL = ("Oracle `partial`: the reference solution scored 1 on earlier versions of this task (`task.toml` `oracle_evidence`) "
           "and was not re-run on this one; the family is reviewed by a maintainer (PROTOCOL §2.7) in the pull request that "
           "adds it.")
NO_POSITIVE = ("No oracle and no verified positive example: the family is reviewed by a maintainer (PROTOCOL §2.7) in the pull "
               "request that adds it, on the official human demonstrations and a `nop` run per mode; until a positive example "
               "scores 1, its results are reported separately from the tasks with a verified solution (PROTOCOL §7, open item 4).")
NO_POSITIVE_PR = ("No oracle; human review in PR #{pr} (PROTOCOL §2.7), on the official human demonstrations and a `nop` run per "
                  "mode; until a positive example scores 1, its results are reported separately from the tasks with a verified "
                  "solution (PROTOCOL §7, open item 4).")
REVIEW = {"full": "", "partial": PARTIAL, "none": NO_ORACLE, "none_demo": NO_POSITIVE, "none_demo_pr": NO_POSITIVE_PR}
EVIDENCE = ("No reference solution: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance. Solvable: "
            "model trial {trial} ({batch}, {where}) graded success=1, deterministic=1 by the separate verifier on a pre-v1.0 "
            "version of this task (dev/qineng {ran_at}; grader verdict and frozen instance unchanged since); agent log {log}, "
            "verifier replay {replay}; not re-run on this version (static validation only). Human review per family "
            "(protocol §2.7).")
EVIDENCE_DEMO = ("No reference solution and no verified positive example yet: BEHAVIOR-1K ships no expert or planner that replays "
                 "on this frozen instance, and no model trial has solved this task. Solvable by a human with this robot: the 2026 "
                 "BEHAVIOR Challenge publishes {episodes} teleoperated demonstrations of this activity on the R1Pro in this scene "
                 "model ({mean_s} s on average); demonstration video ({duration_s} s): {video} (challenge task list {page}). "
                 "Supplementary task (added {added}); human review {review} (protocol §2.7).")
VERIFY_PRIVILEGED = (
    "Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff the BDDL goal\n"
    "holds after every replay, the final-state hashes agree and the rebuilt frozen instance matches the recorded one\n"
    "(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process reproduces the live run bit for bit (the replay\n"
    "starts from the loaded state, no reset); an in-process reset is only approximate, hence two fresh processes. A file the\n"
    "grader cannot read or with the wrong shape is `bad_trajectory`; a replay that dies or runs out of time, and a frozen\n"
    "instance that does not rebuild in the verifier (`instance_ok` 0), are `grader_error` + `infra_error` (no verdict on the agent).")
VERIFY_STANDARD = (
    "`success` = live success ∧ replay success ∧ deterministic (two fresh-process replays agree), computed in the sidecar;\n"
    "`live_matches_replay` is reported separately, and so are the crash-recovery fields (`sim_startups`, `resumes`,\n"
    "`resume_state_mismatch`, `infra_error`); `/logs/verifier/replay.mp4`. `infra_error` = 1 (no verdict on the agent) also\n"
    "when `final.json` is missing, unreadable or not finalized, or a replay did not run to its result (`replay_error`).")
SIDECAR = (
    "The agent gets only the `eai-standard/2.2` client (docs/STANDARD_MODE.md); the simulator runs in the `sim` sidecar\n"
    "(`environment/docker-compose.yaml`: GPU on the sidecar, the licensed dataset mounted read-only at `/data`, the service's own\n"
    "record in `/out`), which owns the scene and records the episode as a (T, 25) trajectory. The collect hook\n"
    "(`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the trajectory in two fresh processes\n"
    "(Isaac: only the first replay in a process is bit-exact, and two simulators do not fit in one container) and writes\n"
    "`final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts.")
# The README Change Log (PROTOCOL §2.8: published tasks fixed in place), per mode, oldest first.
FALL = ("OmniGibson's own Falling rule (the base tilted more than 41.4° from upright, or more than 3 cm below the floor) "
        "has held for 10 s of simulated time")                 # the tooling's FALL_* (docs/benchmarks/behavior.md, Falls)
REPLAY_LIMIT = "min(4 h, max(3600 s, 1200 s + steps / 2))"      # tests/grade.py replay_timeout(), per fresh-process replay
MEASURED = ("measured on an 8-vCPU L40S host (job #3137): the Isaac start took 626 s and a 10,475-step replay ran slower than "
            "3.5 control steps/s")
CHANGES = {
    "privileged": [
        f"2026-10-08: verifier time limits only. `tests/grade.py` gives each of the two fresh-process replays {REPLAY_LIMIT} "
        f"instead of a flat 3600 s, and `[verifier] timeout_sec` is 30600 s (was 5400 s), {MEASURED}, so long trajectories "
        "hit the old limit as a grader error. The scene, frozen instance and pass rule are unchanged, so the task keeps its "
        "name; a trial graded before this date with `grader_error` = 1 can be regraded.",
        f"2026-10-09: a fall ends the episode as a failure (owner decision): once {FALL}, the tooling Session's episode ends "
        "(`status()['fallen']`; `s.reset()` starts again), and the verifier's replays end at the same control step (`reward.json` "
        "`fallen`). The scene, frozen instance and BDDL goal are unchanged, so the task keeps its name; a trajectory in which "
        "the robot falls over and stays down for 10 s scores 0, and results recorded before this change are reported "
        "separately.",
        "2026-10-10: whose failure a 0 is (review of board 0067; the pass rule is unchanged). `tests/grade.py`: a file the "
        "agent wrote that cannot be graded (not an npz, object arrays, no `task` or `actions` entry) is `bad_trajectory` "
        "(was `grader_error`); a frozen scene that does not rebuild to the recorded one in the verifier (`instance_ok` 0) "
        "sets `infra_error` and `grader_error` (was a plain 0), and a replay that died or ran out of time sets `infra_error` "
        "next to `grader_error`; every `reward.json` carries `deterministic` and `infra_error`. The tooling's "
        "`replay` CLI skips an extra npz entry it cannot read and never lets its video recorder's start or stop decide a "
        "replay. The instruction states the runaway guard (200,000 control steps), the trajectory format and the grader's "
        "replay time limit. A trajectory that passed before still passes, so the task keeps its name.",
        "2026-10-10 (2): the GPU-memory limit of the agent phase is 24 GiB (was 16 GiB). This is a change of the limit "
        "(`[metadata.resources.limits]`, the `## Resource limits` paragraph of `instruction.md`), not of the minimum the task "
        "declares: the reference solution alone holds 15.1 GiB for most of the episode on a 48 GB card with "
        "`RCB_TEXTURE_BUDGET=0.1` (three oracle runs, two tasks, two L40S hosts, the task's own monitor), which left 5 % under "
        "the old limit; the new one is max(1.5 x peak, peak + 4) rounded up, as for the other Isaac Sim benchmarks. Limits are "
        "still only recorded (enforcement is off), so no result changes; the scene, the pass rule and the verifier are "
        "unchanged, and the task keeps its name."],
    "standard": [
        "2026-10-08: collect-hook time limit only. `[[verifier.collect]] timeout_sec` is 37800 s (was 21600 s): the episode end "
        f"(up to 2 h through a resume) plus two replays of up to 4 h each (the privileged grader's cap of {REPLAY_LIMIT}) "
        f"plus 30 min; {MEASURED}. The replays still have no limit of their own. The scene, frozen instance and pass rule are "
        "unchanged, so the task keeps its name.",
        f"2026-10-09: a fall ends the episode as a failure (owner decision): once {FALL}, the service ends the episode with "
        "reason \"failure: the robot fell over\"; `/spec` `episode` states the end conditions and `reward.json` adds "
        "`task_failure`. The scene, frozen instance and BDDL goal are unchanged, so the task keeps its name; results recorded "
        "before this change are reported separately.",
        "2026-10-10: infrastructure failures are no longer booked as the agent's 0, and malformed requests no longer end the "
        "episode (review of board 0067; the pass rule is unchanged). `tests/grade.py`: a missing, unreadable or unfinalized "
        "`final.json` and a fresh-process replay that died, printed no result or ran out of time give `infra_error` = 1 "
        "(`replay_error`), and a reward is always written. `environment/sim/finalize.sh`: each replay's exit code is "
        "recorded and each replay may run until the hook's own deadline (it was killed with the hook before). "
        "`environment/sim/server.py`: every field of `/submit` and `/observe` is checked before anything is executed (a null "
        "or wrong-type `dt`, `seconds`, `video_fps`, `cameras` or `note`, `video_fps` outside 1-30, a zero quaternion: 400, "
        "they ended the episode as a simulator error before); a `dt` that is not a whole number of control periods is a 400 "
        "(it was rounded: 0.25 s ran as 0.267 s); a resume whose replayed episode ends before the logged one no longer "
        "crashes every restart; `/spec` states the runaway guard (`max_control_steps` 200,000, in the instruction too). A "
        "trial that passed before still passes, so the task keeps its name; a trial scored 0 before this date whose "
        "`final.json` was unfinalized or missing was an infrastructure failure.",
        "2026-10-10 (review round 2, board 0067): the client only. `Robot()` waits up to 3600 s for the service (was 600 s) "
        "and prints its progress once a minute: Isaac Sim took 620-715 s to start on the 8-vCPU evaluation hosts (more than "
        "600 s in 38 of 60 archived trials), so the first `Robot()` raised \"sim service unavailable\" and a script that did "
        "not retry ended with 0 control steps. `cameras=\"name\"` (a string) is one camera, no longer its characters. The "
        "service, the collect hook, the grader, the scene and the pass rule are unchanged; a trial scored 0 with 0 control "
        "steps before this date may have been this wait.",
        "2026-10-10 (review round 3, board 0067): the shared service layer and the client only "
        "(`environment/sim/rcb_limited.py`, `environment/rcb_client.py`). A camera named more than once in "
        "`cameras` is rendered and returned once (N copies of one name made the service build N x N images within "
        "the frame budget, which could exhaust its memory). A service that has given up on the episode (it could "
        "not start it, or could not resume it after its crashes) answers every request with 409 and the reason, "
        "and `Robot()` / `wait_ready()` raise `EpisodeOver` at once; before, nothing answered and they waited out "
        "their timeout (up to an hour). The adapter, the collect hook, the grader, the scene and the pass rule are "
        "unchanged."],
}


def change_log(mode: str) -> str:
    return "\n### Change Log\n" + "".join(f"- {c}\n" for c in CHANGES[mode])


def base(fam: str) -> str:
    return f"behavior-{fam.replace('_', '-')}-i00"


def priv(fam: str) -> str:
    return base(fam) + "-privileged"


def std(fam: str) -> str:
    return base(fam) + "-standard"


TP, TS = priv(TEMPLATE), std(TEMPLATE)


def sub(path: Path, pairs) -> None:
    """Exact replacements; a missing anchor means the template drifted from this generator."""
    s = path.read_text()
    for a, b in pairs:
        assert a in s, (str(path), a[:70])
        s = s.replace(a, b)
    path.write_text(s)


def resub(path: Path, pattern: str, repl: str) -> None:
    s = path.read_text()
    s2, n = re.subn(pattern, lambda _: repl, s, count=1, flags=re.S)
    assert n == 1, (str(path), pattern[:70])
    path.write_text(s2)


def goal_block(bddl: str) -> str:
    """The BDDL :goal s-expression without the file's outer indentation (as quoted in the privileged instruction)."""
    block = "\n".join(line.rstrip() for line in G.goal_block(bddl).splitlines())
    return re.sub(r"\n\s{4}", "\n", "    " + block).strip()


def evidence(fam: str, e: dict, mode: str) -> str:
    if "positive" not in e:                       # no positive yet: the official human demonstrations (both modes)
        added = e.get("added")                  # a family added after the first 50 cites the pull request of its review
        return EVIDENCE_DEMO.format(**e["demo"], added=added or "2026-10-04", review=f"in PR #{review_pr(e)}" if added else "per family")
    p = e["positive"]
    where = "privileged" if mode == "privileged" else f"the privileged twin {priv(fam)} on the same frozen instance and BDDL goal"
    return EVIDENCE.format(trial=p["trial"], batch=p["batch"], where=where, ran_at=p["ran_at"], log=p["log"], replay=p["replay"])


ORACLE_BLOCK = r'oracle = "[a-z]+"[^\n]*\n(?:oracle_evidence = "[^\n]*"\n)?'


def oracle_lines(fam: str, e: dict, mode: str) -> str:
    """task.toml's oracle lines: the level, and for partial / none the evidence (PROTOCOL §2.7)."""
    level = e["oracle"]
    if level == "full":
        return 'oracle = "full"\n'
    text = e["oracle_evidence"][mode] if level == "partial" else evidence(fam, e, mode)
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'oracle = "{level}"\noracle_evidence = "{text}"\n'


def client_image() -> str:
    """CLIENT_IMAGE of scripts/eai_standard/client.env (PROTOCOL §2.4: one digest-pinned client base for every standard task)."""
    for line in (ROOT / "scripts/eai_standard/client.env").read_text().splitlines():
        if line.startswith("CLIENT_IMAGE="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("scripts/eai_standard/client.env has no CLIENT_IMAGE")


def copy_tree(src: Path, dst: Path, ignore: tuple) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "results", *ignore))


# ---------------------------------------------------------------- READMEs (the protocol's layout; normalize() adds the key table)
def details(rows: list[tuple[str, str]], sections: list[tuple[str, str]] = ()) -> str:
    out = "## Details\n| | |\n|---|---|\n" + "".join(f"| {k} | {v} |\n" for k, v in rows)
    return out + "".join(f"\n### {t}\n{b}\n" for t, b in sections)


def review_pr(e: dict) -> str:
    """The pull request whose human review a family added after the first 50 cites: its own `review_pr` (a number, or a batch
    name from REVIEW_PRS), else REVIEW_PR."""
    v = e.get("review_pr")
    return str(REVIEW_PRS.get(v, v) if v else REVIEW_PR)


def review_key(e: dict) -> str:
    if e["oracle"] == "none" and "positive" not in e:
        return "none_demo_pr" if e.get("added") else "none_demo"
    return e["oracle"]


def readme(name: str, task: str, difficulty: str, reference: str, verification: str, level: str, more: str, pr: str = "") -> str:
    review = f"\n\n{REVIEW[level].replace('{pr}', pr)}" if REVIEW[level] else ""
    return (f"# {name}\n\n## Task\n{task.strip()}\n\n## Difficulty\n{difficulty.strip()}\n\n## Reference solution\n{reference.strip()}\n\n"
            f"## Verification\n{verification.strip()}{review}\n\n{more}")


def readme_privileged(fam: str, e: dict) -> str:
    r = e.get("readme", {})
    success = "".join(f"- {c}\n" for c in e.get("success", []))
    task = r.get("task") or (e["goal"] + (f"\n\n**Success**, all at the same time (the episode ends by itself the moment they "
                                          f"hold):\n{success}" if success else ""))
    if r.get("reference"):
        ref = r["reference"]
    elif e["oracle"] in ("full", "partial"):
        ref = (f"`solution/oracle_{fam}.py` (the challenge ships teleop demos, not scripts; written for this instance). It runs on "
               f"the task-level primitives of the tooling it was written with, frozen in `solution/rcb_behavior_ref.py` (the "
               f"agent's tooling has only thin ones); `solution/solve.sh` records the trajectory with that copy.")
    elif "positive" not in e:
        d = e["demo"]
        ref = (f"None (`oracle = \"none\"`): no reference solution was written (the challenge ships teleop demos, not scripts), "
               f"and no positive example has been graded by this verifier yet. Evidence that the task is solvable: the 2026 "
               f"BEHAVIOR Challenge's {d['episodes']} human teleoperation demonstrations of this activity on the R1Pro "
               f"({d['mean_s']} s on average; video {d['video']}); `task.toml` `oracle_evidence`.")
    else:
        p = e["positive"]
        ref = (f"None (`oracle = \"none\"`): no reference solution was written (the challenge ships teleop demos, not scripts). "
               f"Evidence that the task is solvable: model trial `{p['trial']}` ({p['batch']}), graded 1 by the separate verifier; "
               f"its agent log is on the results site ({p['log']}) and the verifier's replay on Hugging Face ({p['replay']}); "
               f"`task.toml` `oracle_evidence` has the version it ran on.")
    rows = [("Instance", f"2026 BEHAVIOR Challenge public_test instance {e['instance_id']} (scene `{e.get('scene', 'house_double_floor_lower')}`), "
                         f"state hash in `environment/instance.json`"),
            ("Image", f"`{IMAGE}` = `stanfordvl/behavior:3.9.2` + ffmpeg; BUILD_ONLY, built on every host (`images/behavior/`)"),
            ("Dataset", "the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition), never baked in"),
            ("GPU", "an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`, `count: 1`)"),
            ("Budget", "14400 s: every Python process pays ~3 min of Isaac Sim + scene load; ~7-11 control steps/s "
                       "(docs/benchmarks/behavior.md)"),
            ("Verifier time", f"each replay {REPLAY_LIMIT}; `[verifier] timeout_sec` 30600 s (two capped replays + 30 min)")]
    return readme(priv(fam), task, r.get("difficulty") or e["difficulty"], ref, VERIFY_PRIVILEGED, review_key(e),
                  details(rows) + change_log("privileged"), review_pr(e))


def readme_standard(fam: str, e: dict, text: str) -> str:
    task = (f"Standard-mode twin of `{priv(fam)}` on the same frozen instance (2026 BEHAVIOR Challenge public_test instance "
            f"{e['instance_id']}): {text}")
    difficulty = (f"Same scene, frozen instance and success rule as `{priv(fam)}` (see its Difficulty). In standard mode the agent has "
                  "no reset, no privileged state and no planning primitives: it sees the robot's cameras (RGB, depth on request) and "
                  "its proprioception only, acts through the client, and gets one episode.")
    if e["oracle"] in ("full", "partial"):
        ref = ("`solution/`: streams the privileged oracle's joint targets (one row per control step, `hold`) as `joint_position` "
               "chunks through the client; it uses no privileged information at run time, and after a service crash it waits for "
               "the resumed episode and continues from the control step it reached (`on_service_error`).")
    elif "positive" not in e:
        ref = ("None (`oracle = \"none\"`): no reference solution was written, and no positive example has been graded by this "
               "verifier yet. Evidence that the task is solvable: the 2026 BEHAVIOR Challenge's human teleoperation "
               "demonstrations of this activity on the R1Pro (`task.toml` `oracle_evidence`).")
    else:
        ref = (f"None (`oracle = \"none\"`): no reference solution was written. Evidence that the task is solvable: the privileged "
               f"twin's model trial `{e['positive']['trial']}` on the same frozen instance and BDDL goal (`task.toml` `oracle_evidence`).")
    rows = [("Protocol", "`eai-standard/2.2`: RGB-D + proprioception through the client; no reset, no object poses, no success predicate"),
            ("Action space", "`submit` chunks of `joint_position` (25, streamed at the 30 Hz control rate with the agent's `dt`; base "
                             "entries are per-step targets) or of `ee_pose` (16, both end effectors, cuRobo IK per row); `observe` "
                             "frames or a watch window; binary RCB1 responses"),
            ("Crash recovery", "`restart: on-failure:6`; the service journals every control step (`journal.f64`) and resumes the same "
                               "episode after a crash (resume class `approx`, docs/STANDARD_MODE.md §13.1); startup watchdog "
                               "`RCB_STARTUP_TIMEOUT_S` = 1800 s"),
            ("Dataset", "the licensed BEHAVIOR dataset, mounted read-only into the sidecar from `$RCB_BEHAVIOR_DATA` (a precondition)"),
            ("Budget", "14400 s of agent wall clock, as the privileged twin (docs/benchmarks/behavior.md)"),
            ("Collect hook time", "37800 s: the episode end (up to 2 h through a resume) + two replays of up to 4 h + 30 min")]
    return readme(std(fam), task, difficulty, ref, VERIFY_STANDARD, review_key(e),
                  details(rows, [("Sidecar and grading", SIDECAR)]) + change_log("standard"), review_pr(e))


def standard_description(fam: str, seed: int, text: str) -> str:
    return (f'description = "STANDARD MODE (robot as a service, eai-standard/2.2): BEHAVIOR-1K v3.9.2 {fam} on the same frozen '
            f'instance as the privileged task (2026 challenge public_test instance {seed}). {text} The agent only gets a client: '
            f'get_obs (RGB-D + proprioception), submit (joint_position or ee_pose chunks). No reset, no privileged state; the sim '
            f'service records the episode as a trajectory, resumes it after a crash, and the episode is graded on two fresh '
            f'replays."\n')


def instance_text(fam: str) -> str:
    return json.loads((HERE / "instances" / f"{fam}.json").read_text()).get("text", "")


# ---------------------------------------------------------------- tasks
def refresh_templates(src: Path, out: Path, F: dict) -> None:
    """The template twins: copied as they are, then their shared copies, oracle lines and READMEs refreshed."""
    for t in (TP, TS):
        if out != src:
            copy_tree(src / t, out / t, ())
    p, s = out / TP, out / TS
    inst = (HERE / "instances" / f"{TEMPLATE}.json").read_text()
    for f in (p / "environment/instance.json", p / "tests/instance.json", s / "environment/sim/instance.json"):
        f.write_text(inst)
    for name in TOOLING:
        for d in (p / "tests", s / "environment/sim"):
            shutil.copy(p / "environment" / name, d / name)
    for rel, name in LAYER.items():
        shutil.copy(ROOT / "scripts/eai_standard" / name, s / rel)
    image = client_image()                       # the shared client base of the agent container and the verifier
    for rel in ("environment/Dockerfile", "tests/Dockerfile"):
        resub(s / rel, r"(?m)^FROM \S+$", f"FROM {image}")
    e = F[TEMPLATE]
    resub(p / "task.toml", ORACLE_BLOCK, oracle_lines(TEMPLATE, e, "privileged"))
    resub(s / "task.toml", ORACLE_BLOCK, oracle_lines(TEMPLATE, e, "standard"))
    (p / "README.md").write_text(readme_privileged(TEMPLATE, e))
    (s / "README.md").write_text(readme_standard(TEMPLATE, e, instance_text(TEMPLATE)))


def make_privileged(fam: str, e: dict, src: Path, out: Path) -> None:
    dst = out / priv(fam); oracle = e["oracle"] in ("full", "partial")          # a reference solution exists
    copy_tree(src / TP, dst, ("instance.json", "oracle_*.py") if oracle else ("instance.json", "solution"))
    inst = (HERE / "instances" / f"{fam}.json").read_text()
    assert json.loads(inst)["task"] == fam and int(json.loads(inst)["instance_id"]) == e["instance_id"], fam
    for d in ("environment", "tests"):
        (dst / d / "instance.json").write_text(inst)
    if oracle:
        for f in sorted((HERE / "solutions" / fam / "privileged").iterdir()):
            shutil.copy(f, dst / "solution" / f.name)
        sub(dst / "solution/solve.sh", [(TEMPLATE, fam)])
    sub(dst / "tests/test.sh", [(f"--family {TEMPLATE}", f"--family {fam}")])
    tt = dst / "task.toml"
    sub(tt, [
        (f'name = "robot-coding-bench/{TP}"', f'name = "robot-coding-bench/{priv(fam)}"'),
        ("picking_up_trash (R1Pro mobile manipulator, OmniGibson / Isaac Sim): produce one replayable trajectory. Put the three "
         "cans of soda from the living room inside the trash can in the kitchen. Frozen scene instance (challenge public_test instance 301).",
         f"{fam} (R1Pro mobile manipulator, OmniGibson / Isaac Sim): produce one replayable trajectory. {e['goal']} Frozen scene "
         f"instance (challenge public_test instance {e['instance_id']})."),
        (f'"trajectory", "{TEMPLATE}"]', f'"trajectory", "{fam}"]'),
        (f'family = "{TEMPLATE}"', f'family = "{fam}"'),
        ("instance_seed = 301               # scene = environment/instance.json (2026 challenge public_test instance 301",
         f"instance_seed = {e['instance_id']}               # scene = environment/instance.json (2026 challenge public_test instance {e['instance_id']}"),
    ])
    resub(tt, ORACLE_BLOCK, oracle_lines(fam, e, "privileged"))
    bddl = (HERE / "bddl" / f"{fam}.bddl").read_text()
    objs = e.get("objects") or G.task_objects(bddl)
    success = "".join(f"- {c}\n" for c in e.get("success", []))
    success = f"**Success**, all at the same time (the episode ends by itself the moment they hold):\n{success}\n" if success else ""
    meaning = G.meanings(bddl)
    meaning = f"What the goal's predicates mean (OmniGibson's object states):\n{meaning}\n" if meaning else ""
    note = f"{e['note'].strip()}\n" if e.get("note", "").strip() else ""
    ins = dst / "instruction.md"
    sub(ins, [(f"# BEHAVIOR-1K · {TEMPLATE} — frozen instance", f"# BEHAVIOR-1K · {fam} — frozen instance")])
    resub(ins, r"\*\*Task:\*\* .*?\n\n", f"**Task:** {e['goal']}\n\n{success}")
    resub(ins, r"The scene is `.*?`; the task objects are BDDL objects .*?```lisp\n.*?```\n",
          f"The scene is `{e['scene']}`; the task objects are BDDL objects (`s.objects()`: {', '.join(f'`{o}`' for o in objs)}; see\n"
          f"`/behavior-src/bddl3/bddl/activity_definitions/{fam}/problem0.bddl`). The success predicate is the task's BDDL\n"
          f"goal in that file, evaluated by OmniGibson's object states; the episode ends by itself the moment it holds:\n"
          f"```lisp\n{goal_block(bddl)}\n```\n" + meaning + note)
    sub(ins, [(f'Session("{TEMPLATE}"', f'Session("{fam}"'), (f"--task {TEMPLATE}", f"--task {fam}")])
    (dst / "README.md").write_text(readme_privileged(fam, e))


def make_standard(fam: str, e: dict, src: Path, out: Path) -> None:
    dst = out / std(fam); oracle = e["oracle"] in ("full", "partial")
    copy_tree(src / TS, dst, ("oracle_qpos.npy", "oracle_meta.json") if oracle else ("solution",))
    p = out / priv(fam)
    shutil.copy(p / "environment/instance.json", dst / "environment/sim/instance.json")
    for name in TOOLING:
        shutil.copy(p / "environment" / name, dst / "environment/sim" / name)
    if oracle:
        for f in sorted((HERE / "solutions" / fam / "standard").iterdir()):
            shutil.copy(f, dst / "solution" / f.name)
    seed = e["instance_id"]; text = instance_text(fam)
    sub(dst / "environment/docker-compose.yaml", [(f"RCB_TASK: {TEMPLATE}", f"RCB_TASK: {fam}")])
    tt = dst / "task.toml"
    sub(tt, [(f'name = "robot-coding-bench/{TS}"', f'name = "robot-coding-bench/{std(fam)}"'),
             (f'"trajectory", "{TEMPLATE}"]', f'"trajectory", "{fam}"]'), (f'family = "{TEMPLATE}"', f'family = "{fam}"'),
             ("instance_seed = 301\n", f"instance_seed = {seed}\n")])
    resub(tt, r'description = "[^\n]*"\n', standard_description(fam, seed, text))
    resub(tt, ORACLE_BLOCK, oracle_lines(fam, e, "standard"))
    ins = dst / "instruction.md"
    sub(ins, [(f"# BEHAVIOR-1K · {TEMPLATE} — STANDARD MODE", f"# BEHAVIOR-1K · {fam} — STANDARD MODE")])
    resub(ins, r"\*\*Task:\*\* .*?\n\n", f"**Task:** {e['std_goal']}\n\n")
    resub(ins, r"This is a long task: .*\Z", e["std_closing"].rstrip() + "\n")
    (dst / "README.md").write_text(readme_standard(fam, e, text))


def check_template(src: Path) -> None:
    """The template twins agree with what this generator derives (the description formula, the goal block)."""
    assert standard_description(TEMPLATE, 301, instance_text(TEMPLATE)) in (src / TS / "task.toml").read_text(), \
        "template standard description drifted"
    gb = goal_block((HERE / "bddl" / f"{TEMPLATE}.bddl").read_text())
    assert f"```lisp\n{gb}\n```\n" in (src / TP / "instruction.md").read_text(), "template goal block differs from its BDDL"


def generate(families: list[str], F: dict, src: Path, out: Path) -> list[Path]:
    check_template(src)
    refresh_templates(src, out, F)
    dirs = [out / TP, out / TS]
    for fam in families:
        if F[fam].get("template"):
            continue
        make_privileged(fam, F[fam], src, out)
        make_standard(fam, F[fam], src, out)
        dirs += [out / priv(fam), out / std(fam)]
        print("generated", priv(fam), "and", std(fam), f"(oracle {F[fam]['oracle']})")
    for d in dirs:                                   # the protocol's conventions, last (PROTOCOL §2.1)
        normalize(d)
    return dirs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("families", nargs="*"); ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    F = json.loads((HERE / "families.json").read_text())
    fams = a.families or [f for f, e in F.items() if e.get("include")]
    bad = [f for f in fams if f not in F or not F[f].get("include")]
    if bad:
        print(f"not an included family of families.json: {bad}", file=sys.stderr); return 2
    src = ROOT / "tasks"
    if not a.check:
        generate(fams, F, src, src); return 0
    with tempfile.TemporaryDirectory(prefix="rcb_behavior_check_") as tmp:
        dirs = generate(fams, F, src, Path(tmp))
        diff = [d.name for d in dirs if subprocess.run(["diff", "-r", "-q", "-x", "__pycache__", str(src / d.name), str(d)],
                                                       capture_output=True).returncode]
    print("--check:", "no diff" if not diff else f"{len(diff)} task dirs differ from a regeneration: {diff}")
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
