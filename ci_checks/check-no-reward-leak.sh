#!/usr/bin/env bash
# The scoring formula must not reach the agent. It is deleted from the base image
# (images/humanoidbench/scrub_oracles.py) and shipped only in tests/, which Harbor copies in after the
# agent has finished -- so this check is what stops it from creeping back through a task directory.
#
# Four things are verified:
#   1. tests/ HAS the formula for this family, and only this family -- otherwise the verifier cannot score
#   2. environment/ does NOT have it, in any form
#   3. instruction.md describes the scoring in words and quotes no tolerance parameters. That line is
#      documented in scripts/<sim>/subset.toml under "HOW TO WRITE scoring_note": order-of-magnitude
#      targets are fine, `bounds=(0.68, 0.72)` is the answer key.
#   4. the agent phase cannot reach the network by default. Checks 1-3 only control what WE ship; upstream
#      is a public pinned commit, so under Harbor's default `public` policy the agent can curl the whole
#      answer key back. Measured before this was set: an agent-phase curl of raw.githubusercontent.com
#      pulled basic_locomotion_envs.py and found 5 `def get_reward`.
# Limited mode (docs/LIMITED_MODE_1_1.md) moves the formula from tests/ to environment/sim/: the sim sidecar
# judges the episode and the verifier only reads its log. The agent image is then environment/ minus sim/,
# and environment/Dockerfile must not COPY sim/ in (the sidecar gets it through a compose volume instead).
t="$1"; python3 - "$t" <<'PY'
import json, pathlib, re, sys

task = pathlib.Path(sys.argv[1])
toml = (task / "task.toml").read_text()
KEY = lambda k: (re.search(rf'^{k} *= *"([^"]*)"', toml, re.M) or [None, None])[1]
if KEY("simulator") != "humanoidbench":
    sys.exit(0)
rc = 0
limited = KEY("mode") == "limited"
home = task / ("environment/sim" if limited else "tests")          # where the formula has to be
agent_side = [f for f in sorted((task / "environment").rglob("*"))
              if not (limited and task / "environment" / "sim" in f.parents)]

# 1. the scoring half must carry exactly this family's formula
spec_path = home / "rewards.json"
if not spec_path.is_file():
    print(f"FAIL {task}: {spec_path.relative_to(task)} is missing -- nothing could score"); sys.exit(1)
spec = json.loads(spec_path.read_text())
if not spec.get("methods"):
    print(f"FAIL {task}: {spec_path.relative_to(task)} carries no reward method"); rc = 1
if not (home / "rcb_rewards.py").is_file():
    print(f"FAIL {task}: {home.relative_to(task)}/rcb_rewards.py is missing -- nothing would restore the formula"); rc = 1

# 2. the agent's half must not, whether as the file itself or as pasted source
for f in agent_side:
    if f.name in ("rewards.json", "rcb_rewards.py"):
        print(f"FAIL {task}: {f.relative_to(task)} would ship the scoring formula to the agent"); rc = 1
if limited:  # ... and the sidecar's directory must not be copied into the agent's image
    for i, line in enumerate((task / "environment" / "Dockerfile").read_text().splitlines(), 1):
        m = re.match(r"\s*(?:COPY|ADD)\s+(?!--from)(.+)", line, re.I)
        srcs = [s for s in m.group(1).split()[:-1] if not s.startswith("--")] if m else []
        if any(s.strip("./") in ("", "*") or s.lstrip("./").startswith("sim") for s in srcs):
            print(f"FAIL {task}: environment/Dockerfile:{i} copies the sidecar's files into the agent image"); rc = 1

# 3. tolerance parameters are the answer key; describing the scoring in prose is not
FORMULA = re.compile(r"\b(?:bounds|margin|value_at_margin)\s*=|\brewards\.tolerance\s*\(|\bdef\s+get_reward")
for rel in ["instruction.md", *(str(f.relative_to(task)) for f in agent_side
                               if f.is_file() and f.suffix in (".py", ".md", ".txt", ".yaml", ""))]:
    f = task / rel
    if not f.is_file():
        continue
    for i, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
        if FORMULA.search(line):
            print(f"FAIL {task}: {rel}:{i} quotes the reward formula -> {line.strip()[:80]}"); rc = 1

# 4. and the agent must not be able to fetch upstream's copy instead
agent = re.search(r"^\[agent\](.*?)(?=^\[|\Z)", toml, re.M | re.S)
mode = re.search(r'^network_mode *= *"([^"]*)"', agent.group(1), re.M) if agent else None
if not mode or mode.group(1) not in ("allowlist", "no-network"):
    print(f"FAIL {task}: [agent] network_mode is {mode.group(1) if mode else 'unset (defaults to public)'}"
          f" -- the agent could curl upstream's get_reward() back"); rc = 1
sys.exit(rc)
PY
