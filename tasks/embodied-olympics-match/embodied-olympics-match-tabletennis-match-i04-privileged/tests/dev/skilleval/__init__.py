"""skilleval/: the shared library of the two modes (docs/framework_zh.md §6.3, §9 robot and mode rules; skilleval/README.md).

High = Agent as Athlete (the platform provides the sport's skill API); Low = Agent as Robotics Engineer (the agent
implements the SAME skill API from the robot model, the joint interface with the real limits and a disclosed toolkit).
A sport declares both in sport.toml [modes.high] / [modes.low]; this library gives every sport the same pieces:

  declare.py   the [modes.high] / [modes.low] schema and its cross-checks (stdlib; tools/check stage 1, CI)
  toolkit.py   the toolkit manifest (seat/toolkit.toml) schema and its sha256 checker (stdlib; CLI)
  contract.py  SkillContract: request fields and ranges, tolerances, per-request success, aggregate metrics (stdlib)
  cases.py     hidden / public API-test requests: split by hash, the public practice view (stdlib)
  host.py      the child process that hosts a deliverable skill (stdlib; run with python -I -c)
  sandbox.py   SkillProcess: the parent side (clean env, no privileges, resource and time limits); InProcessSkill
  skillhost.py the skill's host during a match: private copy, identity, sandboxed process; in process or over a Unix
               socket from the seat's skill container (stdlib; the container runs it as a script)
  inloop.py    the skill in the loop: InLoopLayer (skill calls lowered by the player's own skill, compute counted),
               layer_from_env (sport.toml [modes.low.inloop])
  layer.py     SkillLayer: a high level whose commands a skill implementation lowers (turn-based competition tests)
  evaluate.py  the post-match evaluator (API test on hidden requests + competition test through the sport's hooks)

Not a part of the framework (like bodies/): the core never imports it; sports and tools do. No sport is named here
(ci_checks/check-skilleval.py)."""

VERSION = "1.2.0"   # 1.2.0: the skill in the loop in the generated tasks (skillhost.py, layer_from_env, wall timing)
