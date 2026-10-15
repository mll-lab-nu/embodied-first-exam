# RoboSafeBench tasks: how they are made

The tasks are RoboSafeBench's own families. Nothing about a family is written here: the scene, the request, the rules,
the operator's answers, the verdict and the scripted reference all live in RoboSafeBench, in the image
`eai-robosafe` (`images/robosafe/`). This directory freezes instances of them and renders the task directories.

## Steps

1. **Pin RoboSafeBench.** Set the commit and version in `images/robosafe/source.env`, bump `images/robosafe/VERSION`,
   prepare the build context and build the image (`images/robosafe/BUILD_ONLY` says how). A new commit is a new image
   tag: never rebuild a tag that trials have used.
2. **Freeze the instances** (needs the simulator: the image, or a venv with its pins and RoboSafeBench on the path):
   `python scripts/robosafe/make_instances.py` writes `families.json` (the selection: tracks AB, C, D, E, F on the
   UR5e, every member, seed 0), `instances/<slug>-<NN>.json` (the key, the task text, the start state's hash, the
   control API's description) and `oracles/<slug>-<NN>.json` (the reference as rows, with its outcome, and the outcome
   of doing nothing and of exiting `done` at once). It fails a family whose reference does not pass, or where a
   trivial strategy passes. Run it with the same RoboSafeBench commit as the image: the service refuses to start when
   the image does not rebuild the frozen start (`state_sha`).
3. **Render**: `python3 scripts/robosafe/gen_tasks.py render` (standard library only; every task's DIGEST is written
   with it), then `check` must pass.
4. **Evidence** (CONTRIBUTING.md): `python scripts/robosafe/tests/test_service.py <slug>-<NN> ...` in the simulator's
   environment, then Harbor's oracle (reward 1) and nop (reward 0) on every task, and the two replays' hashes from
   `verifier/verdict.json` (`replays.state_sha`).

## Rules that keep a task honest

- **Names.** A task is `cell-<slug>-i<NN>-standard`; the slug is `<track><nn>`, neutral, and NN runs over the
  family's members in a hashed order. Nothing the agent's container holds names the RoboSafeBench family, the member
  or the hazard: `environment/Dockerfile` copies the client only; `environment/sim/` (with `instance.json`) is mounted
  into the sim sidecar alone.
- **The task text** is RoboSafeBench's brief under the condition `sim` (`prompts.task_brief`), with its closing
  sentence pointing to the exits instead of the `end` tool; `make_instances.py` refuses a brief whose closing sentence
  changed. No safety policy is added.
- **The interface** is RoboSafeBench's control API, relayed unchanged (`shared/standard/rcb_rsb.py` documents what
  the adapter needs from it). A type or layout name must not say what is on the table (no `object`, `label`, `mask`,
  `name`); results the API returns must not name the scene's things beyond what the agent's own reference allows.
- **Shared files.** `shared/standard/rcb_service.py`, `rcb1.py` and `rcb_client.py` are byte-identical to the other
  `eai-standard/2.1` benchmarks'; additions go into `server.py`, never into them.
- **No twin.** No task has a privileged twin: the standard tasks, and the realtime set's `-standard-realtime` tasks
  (`gen_realtime.py`; docs/benchmarks/robosafe.md, "Owner review" and "Standard-realtime tasks"); the generator keeps
  one instance file per task so that a privileged twin could be added.

## The development stand-in

`dev/rcb_rsb_dev.py` gives an episode RoboSafeBench's skill tools as one-row command types. It exists to test the
plumbing (notes, exits, finalize, grader, Harbor) and is copied only into development renders
(`make_instances.py --dev`, `gen_tasks.py render --dev --out <scratch>`; `gen_tasks.py` refuses `--dev` into
`tasks/`). The tasks use RoboSafeBench's low-level control API.
