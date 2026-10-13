#!/usr/bin/env python3
"""The checks check something: mutation self-test of the rules that guard the trust boundary and the resource caps.

A rule that reads compose files or task.toml by pattern can go blind without anyone noticing: the trailing comment that
scripts/rcb_monitor/inject.py writes after `volumes:` once hid every volume of the agent's container from
check-verifier-isolation.sh, and all checks stayed green on a task whose agent container mounted the simulator's trusted
volume (review of 2026-10-10, M5). This script copies a few real tasks into a temporary directory, breaks each copy in one
way a rule exists for, and requires that the rule's check fails with the rule's message -- and that the unbroken copy
passes. A mutation that passes is a blind rule: fix the check, not this list.

    python3 ci_checks/check-ci-selftest.py        # repo-level; run_all.sh calls it once. Standard library only.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISOLATION = ["bash", str(ROOT / "ci_checks/check-verifier-isolation.sh")]
RESOURCES = [sys.executable, str(ROOT / "ci_checks/check-resources.py")]
POINTERS = [sys.executable, str(ROOT / "ci_checks/check-agent-pointers.py")]
IDENTITY = ["bash", str(ROOT / "ci_checks/check-tooling-identity.sh")]   # repo-level: runs on a tasks directory (see main)
CUTOFFS = [sys.executable, str(ROOT / "ci_checks/check-cutoffs.py")]

STD = "behavior-boxing-books-up-for-storage-i00-standard"      # a sim sidecar with a trusted cache volume
PRIV = "behavior-boxing-books-up-for-storage-i00-privileged"   # a verifier compose file with a trusted volume
HEAVY = "labutopia-heat-liquid-i00-standard"                   # an allowlist; a sidecar with a large verifier minimum
RT = "roboolympics-airhockey-match-i00-standard-realtime"      # min_cpus = the sum of its two services' caps
# benchmarks whose generators have no check mode: their shared files are held together by check-tooling-identity.sh
DTB, DTB_P = "dextoolbench_hammer_claw_hammer_swing_down-standard", "dextoolbench_hammer_claw_hammer_swing_down-privileged"
MJ = "mujoco_playground_aloha_hand_over-standard"              # serves DexToolBench's service (server_mj.py)
MWP, MWP_P = "metaworldplus-coffee-button-i00-standard", "metaworldplus-coffee-button-i00-privileged"
TWIN_P = "robotwin_2_0_grab_roller-privileged"


def sub(pattern: str, repl: str, count: int = 1, flags: int = re.M):
    def f(s: str) -> str:
        out, n = re.subn(pattern, repl, s, count=count, flags=flags)
        if n == 0:
            raise AssertionError(f"mutation does not apply: /{pattern}/")
        return out
    return f


def in_service(service: str, lines: str, after: str = ""):
    """Insert `lines` into a compose service: right after its line matching `after` (default: the service line)."""
    def f(s: str) -> str:
        rows = s.splitlines(keepends=True)
        i = next(k for k, r in enumerate(rows) if re.match(rf"^  {service}:\s*(#.*)?$", r))
        j = next((k for k in range(i + 1, len(rows)) if re.match(r"^  \S|^\S", rows[k]) and not rows[k].startswith("  #")), len(rows))
        at = i if not after else next(k for k in range(i, j) if re.match(after, rows[k]))
        rows[at + 1:at + 1] = [x + "\n" for x in lines.split("\n")]
        return "".join(rows)
    return f


def append(text: str):
    return lambda s: s + text


COMPOSE, TOML, TEST_COMPOSE = "environment/docker-compose.yaml", "task.toml", "tests/docker-compose.yaml"
TEST_SH, TEST_DF = "tests/test.sh", "tests/Dockerfile"
VOL = r"^    volumes:.*$"
VAR = "a variable in a volume source must be the whole source"
NO_TRAP = sub(r"^(trap .*EXIT.*\n)", r"\1trap - EXIT\n")       # the resource step's trap dropped again one line later
# (name, task, file, mutation, check, what the check must say)
MUTATIONS = [
    # ---- the agent's container and the trusted volumes (the M5 class: every way of writing the same mount)
    ("the agent container mounts the sim's trusted volume (short form, under the generated `volumes:   # rcb-monitor`)",
     STD, COMPOSE, in_service("main", "      - rcb_behavior_cache_trusted:/cache", VOL), ISOLATION, "mounts trusted volume"),
    ("... long form (type: volume / source:)",
     STD, COMPOSE, in_service("main", "      - type: volume\n        source: rcb_behavior_cache_trusted\n        target: /cache", VOL),
     ISOLATION, "mounts trusted volume"),
    ("... long form, source first",
     STD, COMPOSE, in_service("main", "      - source: rcb_behavior_cache_trusted\n        target: /cache\n        type: volume", VOL),
     ISOLATION, "mounts trusted volume"),
    ("... quoted",
     STD, COMPOSE, in_service("main", '      - "rcb_behavior_cache_trusted:/cache:ro"', VOL), ISOLATION, "mounts trusted volume"),
    ("... with the service line and the volumes line carrying other comments",
     STD, COMPOSE, lambda s: in_service("main", "      - rcb_behavior_cache_trusted:/cache   # cache", r"^    volumes:.*$")(
         sub(r"^  main:\s*$", "  main:   # the agent's container")(s)), ISOLATION, "mounts trusted volume"),
    ("... through volumes_from",
     STD, COMPOSE, in_service("main", "    volumes_from: [sim]"), ISOLATION, "`volumes_from` is not allowed"),
    ("an inline volumes list (which the reader would have to guess at) with the trusted volume",
     STD, COMPOSE, lambda s: sub(r"^      - rcb_limits:/run/rcb-limits:ro.*\n", "")(
         sub(r"^  main:\n((?:    .*\n)*?)    volumes:.*$", r"  main:\n\1    volumes: [rcb_limits:/run/rcb-limits:ro, rcb_behavior_cache_trusted:/cache]")(s)),
     ISOLATION, "mounts trusted volume"),
    ("a volume entry the reader does not understand is a failure, not skipped",
     STD, COMPOSE, in_service("main", "      - *shared_cache", VOL), ISOLATION, "not understood"),
    ("a sidecar mounts a volume that is not *_trusted",
     STD, COMPOSE, in_service("sim", "      - shared_scratch:/scratch", VOL), ISOLATION, "which is not a *_trusted volume"),
    ("the verifier mounts a volume that is not *_trusted",
     PRIV, TEST_COMPOSE, sub(r"rcb_behavior_cache_trusted:/cache", "rcb_behavior_cache:/cache"), ISOLATION,
     "the verifier mounts rcb_behavior_cache"),
    # ---- the agent's container reaches the task's trusted files or the host
    ("the agent container bind-mounts the sidecar's code",
     STD, COMPOSE, in_service("main", "      - ./sim:/sim:ro", VOL), ISOLATION, "bind-mounts ./sim"),
    ("... the verifier's tests", STD, COMPOSE, in_service("main", "      - ../tests:/t:ro", VOL), ISOLATION, "bind-mounts ../tests"),
    ("... the reference solution", STD, COMPOSE, in_service("main", "      - ../solution:/s:ro", VOL), ISOLATION, "bind-mounts ../solution"),
    ("... the monitor's code", STD, COMPOSE, in_service("main", "      - ./rcb_monitor:/m", VOL), ISOLATION, "bind-mounts ./rcb_monitor"),
    ("... the docker socket",
     STD, COMPOSE, in_service("main", "      - /var/run/docker.sock:/var/run/docker.sock", VOL), ISOLATION, "bind-mounts /var/run/docker.sock"),
    ("the agent container is privileged", STD, COMPOSE, in_service("main", "    privileged: true"), ISOLATION, "`privileged` is not allowed"),
    ("the agent container shares the host's PID namespace", STD, COMPOSE, in_service("main", "    pid: host"), ISOLATION, "`pid` is not allowed"),
    ("the agent container mounts the beacon volume writable at another path",
     STD, COMPOSE, in_service("main", "      - rcb_limits:/mnt/beacon", VOL), ISOLATION, "mounts the beacon volume rcb_limits writable"),
    # ---- the sidecar is reachable only on localhost
    ("the sidecar publishes a port", STD, COMPOSE, in_service("sim", '    ports: ["8000:8000"]'), ISOLATION, "`ports` is not allowed"),
    ("the sidecar is on the host's network", STD, COMPOSE, in_service("sim", "    network_mode: host"), ISOLATION, "`network_mode` is not allowed"),
    # ---- the verifier's evidence comes from the sidecar
    ("the evidence is collected from the agent's container",
     STD, TOML, sub(r'\{ source = "(/(?:data|out)/final\.json)", service = "sim" \}', r'"\1"'), ISOLATION,
     "is collected from the agent's container"),
    ("the sidecar's collect hook is gone",
     STD, TOML, sub(r'(?ms)^\[\[verifier\.collect\]\]\nservice = "sim"\n.*?(?=^\[|\Z)', ""), ISOLATION, "no [[verifier.collect]] hook on a sidecar"),
    # ---- the verifier's own sandbox, the allowlist
    ("the verifier shares the agent's container", STD, TOML, sub(r'^environment_mode = "separate"', 'environment_mode = "shared"'),
     ISOLATION, 'environment_mode must be "separate"'),
    ("the allowlist lacks a model API's host",
     HEAVY, TOML, sub(r', "\*\.openai\.azure\.com"', ""), ISOLATION, "allowed_hosts differs from scripts/set_agent_egress.py"),
    ("the allowlist opens another host",
     HEAVY, TOML, sub(r'allowed_hosts = \["chatgpt\.com"', 'allowed_hosts = ["github.com", "chatgpt.com"'), ISOLATION,
     "allowed_hosts differs from scripts/set_agent_egress.py"),
    # ---- review round 3, M4: a service with its own network setting is outside Harbor's egress control (the allowlist)
    ("the agent container on a network of its own (`networks:`): the allowlist no longer applies to it",
     HEAVY, COMPOSE, in_service("main", "    networks: [default]"), ISOLATION, "service main: `networks` is not allowed"),
    ("... `network_mode: bridge`", HEAVY, COMPOSE, in_service("main", "    network_mode: bridge"), ISOLATION, "service main: `network_mode` is not allowed"),
    ("a sidecar on a network of its own", STD, COMPOSE, in_service("sim", "    networks: [default]"), ISOLATION, "service sim: `networks` is not allowed"),
    ("a top-level networks block", STD, COMPOSE, append("networks:\n  default:\n    driver: bridge\n"), ISOLATION, "top-level `networks` is not allowed"),
    ("a task drops its allowlist (PROTOCOL §2.11: one host list, in every task)",
     HEAVY, TOML, sub(r'^network_mode = "allowlist".*\nallowed_hosts = .*\n', ""), ISOLATION, '[agent].network_mode must be "allowlist"'),
    ("... a task of a benchmark that was open until 2026-10-10",
     TWIN_P, TOML, sub(r'^network_mode = "allowlist".*\nallowed_hosts = .*\n', ""), ISOLATION, '[agent].network_mode must be "allowlist"'),
    ("the instruction no longer states the external-material rule",
     STD, "instruction.md", sub(r"(?ms)^## External material\n.*?(?=^## )", ""), RESOURCES, "does not state `## External material`"),
    ("the frozen instance the agent reads names where its scene came from",
     PRIV, "environment/instance.json", sub(r"^\{", '{"source_url": "https://example.org/demos/data/manifest.json", ', count=1, flags=0),
     POINTERS, "key `source_url` locates upstream material"),
    ("... names the recording its reference replays",
     PRIV, "environment/instance.json", sub(r"^\{", '{"source": {"file": "demos/boxing_books_017.hdf5", "demo": 3}, ', count=1, flags=0),
     POINTERS, "file `boxing_books_017.hdf5` locates upstream material"),
    ("a step with a network policy of its own (Harbor would let it override [agent])",
     STD, TOML, append('\n[[steps]]\nname = "s1"\n[steps.agent]\nnetwork_mode = "public"\n'), ISOLATION, "a step sets its own network policy"),
    ("the instruction links the upstream repository",
     STD, "instruction.md", append("\nThe benchmark's code: https://github.com/StanfordVL/BEHAVIOR-1K\n"), POINTERS,
     "URL `https://github.com/StanfordVL/BEHAVIOR-1K` locates upstream material"),
    ("the instruction states the external-material rule in other words",
     STD, "instruction.md", sub(r"This is an honour rule; trials are reviewed\.", "Do as you like."), RESOURCES,
     "does not state `## External material`"),
    # ---- the agent's time cutoff (PROTOCOL §2.12): the table, task.toml, the instruction and the sim service agree
    ("task.toml gives the agent another time than the cutoff table",
     STD, TOML, sub(r"(^\[agent\]\n(?:(?!\[).*\n)*?timeout_sec = )[0-9.]+", r"\g<1>28800.0"), CUTOFFS, "the table says"),
    ("the instruction's cutoff sentence with another number",
     STD, "instruction.md", sub(r"^You have \d+ seconds to complete this task\.", "You have 28800 seconds to complete this task."),
     CUTOFFS, "does not end with the `## Time limit` section"),
    ("the instruction without the cutoff sentence",
     PRIV, "instruction.md", sub(r"^You have \d+ seconds to complete this task\.[^\n]*\n\n", ""), CUTOFFS, "the sentence is missing"),
    ("the cutoff section is not the end of the instruction: something follows it",
     PRIV, "instruction.md", append("\nOne more remark after the time limit.\n"), CUTOFFS, "does not end with the `## Time limit` section"),
    ("the cutoff paragraphs under the title, where they stood until 2026-10-12, instead of at the end",
     PRIV, "instruction.md",
     lambda s: (lambda head, sep, block: head.split("\n", 1)[0] + "\n\n" + block.split("\n", 1)[1] + "\n" + head.split("\n", 1)[1])(*s.partition("\n## Time limit\n"))
     if "\n## Time limit\n" in s else (_ for _ in ()).throw(AssertionError("no `## Time limit` section")),
     CUTOFFS, "does not end with the `## Time limit` section"),
    ("a privileged task with the standard modes' second paragraph",
     PRIV, "instruction.md", sub(r"only what is in `/app/output/` at that moment is\s+graded", "the episode is graded as it stands"),
     CUTOFFS, "does not end with the `## Time limit` section"),
    ("the closing sections in another order (`## Time limit` before `## Resource limits`)",
     STD, "instruction.md",
     lambda s: (lambda a, b, c: a + "\n## Time limit\n" + c.rstrip("\n") + "\n\n## Resource limits\n" + b.rstrip("\n") + "\n")(
         s.split("\n## Resource limits\n")[0], *s.split("\n## Resource limits\n")[1].split("\n## Time limit\n")),
     CUTOFFS, "does not end with the `## Time limit` section"),
    ("... which the resources check refuses too (the limits paragraph is the last thing before `## Time limit`)",
     STD, "instruction.md",
     lambda s: (lambda a, b, c: a + "\n## Time limit\n" + c.rstrip("\n") + "\n\n## Resource limits\n" + b.rstrip("\n") + "\n")(
         s.split("\n## Resource limits\n")[0], *s.split("\n## Resource limits\n")[1].split("\n## Time limit\n")),
     RESOURCES, "does not end (before `## Time limit`) with the `## Resource limits` paragraph"),
    ("the instruction states the limit a second time, in a benchmark's old words",
     STD, "instruction.md", sub(r"^(## External material)$", r"Your wall-clock budget is 4 h (14400 s); there is no step budget.\n\n\1"),
     CUTOFFS, "states the agent's limit a second time"),
    ("... 'You have 60 minutes of wall-clock time'",
     PRIV, "instruction.md", sub(r"^(## External material)$", r"- You have 60 minutes of wall-clock time.\n\n\1"),
     CUTOFFS, "states the agent's limit a second time"),
    ("... in words nobody has used yet: 'You have one hour.'",
     STD, "instruction.md", sub(r"^(## External material)$", r"You have one hour.\n\n\1"), CUTOFFS, "states the agent's limit a second time"),
    ("... 'The limit is 3600 seconds.'",
     PRIV, "instruction.md", sub(r"^(## External material)$", r"The limit is 3600 seconds.\n\n\1"), CUTOFFS, "states the agent's limit a second time"),
    ("... 'Finish within 60 minutes.'",
     STD, "instruction.md", sub(r"^(## External material)$", r"Finish within 60 minutes.\n\n\1"), CUTOFFS, "states the agent's limit a second time"),
    ("the README's `Agent time budget` row with another number than the table's",
     STD, "README.md", sub(r"^(\| Agent time budget \| )\d+ s;", r"\g<1>28800 s;"), CUTOFFS, "README.md's `Agent time budget` row does not say"),
    ("the sim service is told another wall clock than the table's",
     STD, COMPOSE, sub(r'(RCB_WALL_CLOCK_S: ")\d+', r"\g<1>3600"), CUTOFFS, "RCB_WALL_CLOCK_S = 3600, the table says"),
    ("the sim service is not told the wall clock (it would report its code's default)",
     MWP, COMPOSE, sub(r"^ *RCB_WALL_CLOCK_S:.*\n", ""), CUTOFFS, "does not give the sim service RCB_WALL_CLOCK_S"),
    # ---- review round 3, M5: a variable in a volume source, the top level of the file, files by another road
    ("the sim's trusted volume as the default of a variable",
     STD, COMPOSE, in_service("main", "      - ${RCB_CACHE_VOL:-rcb_behavior_cache_trusted}:/cache", VOL), ISOLATION, VAR),
    ("the sidecar's code as the default of a variable", STD, COMPOSE, in_service("main", "      - ${RCB_SIM_DIR:-./sim}:/sim:ro", VOL), ISOLATION, VAR),
    ("... `${X-../tests}`", STD, COMPOSE, in_service("main", "      - ${X-../tests}:/t:ro", VOL), ISOLATION, VAR),
    ("a path after a variable", STD, COMPOSE, in_service("main", "      - ${PWD}/sim:/sim:ro", VOL), ISOLATION, VAR),
    ("a variable that is not the runner's (Harbor's own: the task's environment directory)",
     STD, COMPOSE, in_service("main", "      - ${CONTEXT_DIR}:/ctx:ro", VOL), ISOLATION, VAR),
    ("a variable inside a volume's name", STD, COMPOSE, in_service("main", "      - rcb_${B:-behavior}_cache_trusted_${E:-}x:/cache", VOL), ISOLATION, VAR),
    ("... long form",
     STD, COMPOSE, in_service("main", "      - type: volume\n        source: ${V:-rcb_behavior_cache_trusted}\n        target: /cache", VOL), ISOLATION, VAR),
    ("... inline list",
     STD, COMPOSE, lambda s: sub(r"^      - rcb_limits:/run/rcb-limits:ro.*\n", "")(
         sub(r"^  main:\n((?:    .*\n)*?)    volumes:.*$", r"  main:\n\1    volumes: [rcb_limits:/run/rcb-limits:ro, '${V:-rcb_behavior_cache_trusted}:/cache']")(s)),
     ISOLATION, VAR),
    ("... in the verifier's compose file", PRIV, TEST_COMPOSE, sub(r"^      - \$\{RCB_BEHAVIOR_DATA:\?[^}]*\}", "      - ${RCB_BEHAVIOR_DATA:-../solution}"), ISOLATION, VAR),
    ("two names for one volume (top-level `name:`): the agent's volume is the sim's trusted one",
     STD, COMPOSE, lambda s: in_service("main", "      - agent_scratch:/cache", VOL)(s).replace(
         "  rcb_behavior_cache_trusted:\n", "  rcb_behavior_cache_trusted:\n    name: shared_kit_cache\n  agent_scratch:\n    name: shared_kit_cache\n"),
     ISOLATION, "is not a bare name"),
    ("... `external:`", STD, COMPOSE, lambda s: in_service("main", "      - agent_scratch:/cache", VOL)(s) + "  agent_scratch:\n    external: true\n",
     ISOLATION, "is not a bare name"),
    ("a top-level volume that binds the sidecar's code (driver_opts)",
     STD, COMPOSE, lambda s: in_service("main", "      - agent_view:/sim", VOL)(s) + "  agent_view:\n    driver_opts:\n      type: none\n      o: bind\n      device: ${PWD}/sim\n",
     ISOLATION, "is not a bare name"),
    ("... in the verifier's compose file", PRIV, TEST_COMPOSE, sub(r"^  rcb_behavior_cache_trusted:\n", "  rcb_behavior_cache_trusted:\n    name: rcb_kit_cache\n"),
     ISOLATION, "is not a bare name"),
    ("the reference solution as a secret of the agent container",
     STD, COMPOSE, lambda s: in_service("main", "    secrets: [sol]")(s) + "secrets:\n  sol:\n    file: ../solution/solve.sh\n", ISOLATION, "service main: `secrets` is not allowed"),
    ("the sidecar's code as a config of the agent container",
     STD, COMPOSE, lambda s: in_service("main", "    configs:\n      - source: simcode\n        target: /sim_server.py")(s) + "configs:\n  simcode:\n    file: ./sim/server.py\n",
     ISOLATION, "top-level `configs` is not allowed"),
    ("a task file read through env_file", STD, COMPOSE, in_service("main", "    env_file: ./sim/instance.json"), ISOLATION, "service main: `env_file` is not allowed"),
    ("the agent's image built from the task directory", STD, COMPOSE, in_service("main", "    build:\n      context: .."), ISOLATION, "service main: `build` is not allowed"),
    ("another compose file included", STD, COMPOSE, lambda s: "include:\n  - extra.yaml\n" + s, ISOLATION, "top-level `include` is not allowed"),
    ("a service whose keys are indented deeper than the reader looks",
     STD, COMPOSE, sub(r"(?s)^  main:\n.*?(?=^  sim:)", "  main:\n      networks: [default]\n      depends_on: [sim]\n"), ISOLATION, "at an unexpected indentation"),
    ("the kernel's OOM killer switched off for a container", STD, COMPOSE, in_service("sim", "    oom_kill_disable: true"), ISOLATION, "`oom_kill_disable` is not allowed"),
    # ---- pinned images in every stage and file; the verifier's log directory emptied, not a look-alike of it
    ("a second, unpinned stage in the verifier's Dockerfile", STD, TEST_DF, append("FROM python:latest\nCOPY --from=0 /tests /tests\n"), ISOLATION, "must be a pinned registry image"),
    ("a sidecar image whose tag is a variable", STD, COMPOSE, sub(r"^(    image: ghcr\.io/mll-lab-nu/eai-behavior):\S+", r"\1:${TAG:-latest}"), ISOLATION, "must be pinned"),
    ("tests/test.sh removes only a look-alike of the verifier's logs",
     STD, TEST_SH, sub(r"^rm -rf /logs/verifier/\*", "rm -rf /logs/verifier/*.bak"), ISOLATION, "must empty /logs/verifier"),
    # ---- review round 3, M6: benchmarks without a generator check mode (one task hand-edited, its digest refreshed)
    ("DexToolBench: one task's grader edited", DTB, "tests/grade.py", append("# drift\n"), IDENTITY, "dextoolbench: 2 versions of standard tests/grade.py"),
    ("... its service", DTB, "environment/sim/server_mj.py", append("# drift\n"), IDENTITY, "environment/sim/server_mj.py differs from images/mujoco/limited/server_mj.py"),
    ("... its client", DTB, "environment/rcb_client.py", append("# drift\n"), IDENTITY, "dextoolbench: 2 versions of standard environment/rcb_client.py"),
    ("... its tooling module", DTB_P, "tests/rcb_dtb.py", append("# drift\n"), IDENTITY, "dextoolbench: 2 versions of rcb_dtb.py"),
    ("... tests/test.sh without the resource step", DTB_P, TEST_SH, NO_TRAP, IDENTITY, "dextoolbench: 2 versions of privileged tests/test.sh"),
    ("MuJoCo Playground (ALOHA): the same service edited", MJ, "environment/sim/server_mj.py", append("# drift\n"), IDENTITY, "dextoolbench: 2 versions of standard environment/sim/server_mj.py"),
    ("MetaWorld+: one task's service edited", MWP, "environment/sim/server_mw.py", append("# drift\n"), IDENTITY, "environment/sim/server_mw.py differs from images/metaworld/standard/server_mw.py"),
    ("... its grader", MWP_P, "tests/grade.py", append("# drift\n"), IDENTITY, "metaworldplus: 2 versions of privileged tests/grade.py"),
    ("... its tooling module", MWP, "environment/sim/mw_tool.py", append("# drift\n"), IDENTITY, "metaworldplus: 2 versions of mw_tool.py"),
    ("... tests/test.sh without the resource step", MWP, TEST_SH, NO_TRAP, IDENTITY, "metaworldplus: 2 versions of standard tests/test.sh"),
    ("RoboTwin: a privileged task's tests/test.sh without the resource step", TWIN_P, TEST_SH, NO_TRAP, IDENTITY, "robotwin_2_0: 2 versions of privileged tests/test.sh"),
    ("... its grader", TWIN_P, "tests/grade.py", append("# drift\n"), IDENTITY, "robotwin_2_0: 2 versions of privileged tests/grade.py"),
    # ---- caps and minimums (PROTOCOL §2.10)
    ("a sidecar's memory cap below the verifier phase's declared minimum (the kernel would kill it at a cap the task itself says is too low)",
     HEAVY, None, {TOML: sub(r"^(sim = \{ cpus = [0-9.]+, memory_gb = )[0-9.]+", r"\g<1>24.0"),
                   COMPOSE: sub(r"^    mem_limit: \d+m(   # rcb-monitor)$", r"    mem_limit: 24576m\1")},
     RESOURCES, "verifier_min_memory_gb 27.0 > the memory cap of the sidecar"),
    ("the CPU minimum above the CPU caps of all services together",
     RT, TOML, sub(r"^min_cpus = [0-9.]+", "min_cpus = 7.0"), RESOURCES, "min_cpus 7.0 > the CPU caps of all services together 6"),
    ("a declared cap that docker does not apply",
     STD, COMPOSE, sub(r"^    mem_limit: \d+m(   # rcb-monitor)$", r"    mem_limit: 1024m\1"), RESOURCES, "declare the cap that is applied"),
]


def run(cmd: list[str], task: Path) -> tuple[int, str]:
    r = subprocess.run(cmd + [str(task)], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def cutoff_exceptions(tmp: Path) -> int:
    """The cutoff table's exceptions (PROTOCOL §2.12): task > family > benchmark and mode. Three real tasks under a
    table with a family entry and a task entry: normalize writes each task the right number, check-cutoffs.py accepts
    exactly that (and refuses the same files under the repository's table), an entry that reaches no task fails the
    repository-level rule, and tables that are not usable are refused. Returns the number of failures."""
    import os
    import tomllib
    fam_p, fam_s, other = "behavior-boxing-books-up-for-storage-i00-privileged", STD, "behavior-bringing-water-i00-standard"
    family = tomllib.loads((ROOT / "tasks" / STD / "task.toml").read_text())["metadata"]["family"]
    base = (ROOT / "scripts/task_cutoffs.toml").read_text()
    head = base.rstrip("\n") + "\n"                    # the repository's table with its history; a test's entries follow it
    bench = tomllib.loads(base)["cutoff_sec"]["BEHAVIOR-1K"]["standard"]       # the benchmark's own number, whatever it is today
    fam_std, fam_priv, own = bench // 2, bench // 2 + 900, bench // 2 + 1800  # three numbers that are not the benchmark's
    tables: list[Path] = []

    def table(extra: str) -> Path:
        tables.append(tmp / f"cutoffs-{len(tables)}.toml")
        tables[-1].write_text(head + extra)
        return tables[-1]

    def run_py(args: list[str], cutoffs: Path | None) -> tuple[int, str]:
        env = {k: v for k, v in os.environ.items() if k != "RCB_CUTOFFS_FILE"}     # None: the repository's table
        if cutoffs is not None:
            env["RCB_CUTOFFS_FILE"] = str(cutoffs)
        r = subprocess.run([sys.executable] + args, capture_output=True, text=True, env=env)
        return r.returncode, r.stdout + r.stderr

    bad = 0

    def expect(ok: bool, what: str, out: str = "") -> None:
        nonlocal bad
        if not ok:
            bad += 1
            print(f"FAIL check-ci-selftest [cutoff exceptions: {what}]" + (f":\n{out[-600:]}" if out else ""))

    good = table(f'[family_cutoff_sec."BEHAVIOR-1K"]\n"{family}" = {{ standard = {fam_std}, privileged = {fam_priv} }}\n'
                 f'[task_cutoff_sec]\n"{fam_p}" = {own}\n')
    work = tmp / "exceptions"
    for name in (fam_p, fam_s, other):
        shutil.copytree(ROOT / "tasks" / name, work / name)
    rc, out = run_py([str(ROOT / "scripts/task_conventions.py")] + [str(work / n) for n in (fam_p, fam_s, other)], good)
    expect(rc == 0, "normalize under a table with exceptions", out)
    want = {fam_p: own, fam_s: fam_std, other: bench}   # the task's own; its family's for the mode; the benchmark's
    for name, sec in want.items():
        t = work / name
        got = tomllib.loads((t / "task.toml").read_text())["agent"]["timeout_sec"]
        expect(float(got) == sec, f"{name}: [agent] timeout_sec is {got}, expected {sec}")
        expect(f"\nYou have {sec} seconds to complete this task." in (t / "instruction.md").read_text(), f"{name}: the instruction does not say {sec} seconds")
        rc, out = run_py([CUTOFFS[1], str(t)], good)
        expect(rc == 0, f"{name}: check-cutoffs.py under the table with exceptions", out)
        rc, out = run_py([CUTOFFS[1], str(t)], None)
        expect((rc != 0 and "the table says" in out) if sec != bench else rc == 0, f"{name}: check-cutoffs.py under the repository's table", out)
    expect(f'RCB_WALL_CLOCK_S: "{fam_std}"' in (work / fam_s / "environment/docker-compose.yaml").read_text(), f"{fam_s}: the sim service's wall clock is not the family's {fam_std}")
    # an entry that reaches no task; tables that are not usable
    for what, extra, say in [
        ("a family that no task has", '[family_cutoff_sec."BEHAVIOR-1K"]\n"no_such_family" = { standard = 7200 }\n', "has no task of family 'no_such_family'"),
        ("a family entry for a mode the family has no task in", f'[family_cutoff_sec."BEHAVIOR-1K"]\n"{family}" = {{ standard-realtime = 7200 }}\n', f"has no task of family '{family}' in standard-realtime mode"),
        ("a task entry that is no task directory", '[task_cutoff_sec]\n"behavior-no-such-task-i00-standard" = 7200\n', "which is not a task directory"),
        ("a family entry of an unknown benchmark", '[family_cutoff_sec."Behaviour"]\n"x" = { standard = 7200 }\n', "unknown benchmark 'Behaviour'"),
        ("a family entry with an unknown mode", f'[family_cutoff_sec."BEHAVIOR-1K"]\n"{family}" = {{ limited = 7200 }}\n', "unknown mode 'limited'"),
        ("a task entry above the cap", f'[task_cutoff_sec]\n"{fam_s}" = 20000\n', "is above the 14400 s cap"),
        ("a task entry that is not a whole number of seconds", f'[task_cutoff_sec]\n"{fam_s}" = 3600.5\n', "is not a whole positive number of seconds"),
        ("a task entry whose name is not a task directory name", '[task_cutoff_sec]\n"boxing_books" = 3600\n', "is not a task directory name"),
        ("a misspelled table (it would be an exception that silently does nothing)", f'[task_cutoffs_sec]\n"{fam_s}" = 7200\n', "unknown table [task_cutoffs_sec]"),
        ("an exception added without its [[history]] entry", f'[task_cutoff_sec]\n"{fam_s}" = 7200\n',
         f"task {fam_s} is 7200, its last recorded value is none: add a [[history]] entry"),
        ("a [[history]] entry without who decided and why",
         f'[task_cutoff_sec]\n"{fam_s}" = 7200\n[[history]]\ndate = "2026-10-20"\ntask = "{fam_s}"\nfrom_sec = 0\nto_sec = 7200\n', "`decided_by` is required"),
        ("a [[history]] entry whose from_sec is not the recorded value",
         f'[task_cutoff_sec]\n"{fam_s}" = 7200\n[[history]]\ndate = "2026-10-20"\ntask = "{fam_s}"\nfrom_sec = 3600\nto_sec = 7200\ndecided_by = "owner"\nnote = "x"\n',
         "from_sec = 3600, but the value recorded before this entry is 0"),
    ]:
        rc, out = run_py([CUTOFFS[1]], table(extra))
        expect(rc != 0 and say in out, f"{what}: check-cutoffs.py must fail with `{say}`", out)
    # a number of a benchmark's row changed: refused without its [[history]] entry, accepted with it
    changed = head.replace('"KinDER"            = { privileged =  3600, standard =  3600 }', '"KinDER"            = { privileged =  3600, standard =  3000 }')
    expect(changed != head, "the KinDER row of the table is not where this test expects it (update the test)")
    say = "KinDER, standard is 3000, its last recorded value is 3600: add a [[history]] entry"
    tables.append(tmp / "cutoffs-changed.toml"); tables[-1].write_text(changed)
    rc, out = run_py([CUTOFFS[1]], tables[-1])
    expect(rc != 0 and say in out, "a changed number without its [[history]] entry must fail", out)
    tables.append(tmp / "cutoffs-recorded.toml")
    tables[-1].write_text(changed + '[[history]]\ndate = "2026-10-20"\nbenchmark = "KinDER"\nmodes = ["standard"]\nfrom_sec = 3600\nto_sec = 3000\ndecided_by = "owner"\nnote = "a test"\n')
    rc, out = run_py([CUTOFFS[1]], tables[-1])
    expect("[[history]]" not in out, "a changed number with its [[history]] entry: the history rule must be satisfied", out)
    if not bad:
        print("check-ci-selftest: the cutoff table's exceptions (task > family > benchmark and mode): 3 tasks written and "
              "checked under a table with a family and a task entry, 12 unusable tables refused, a changed number refused "
              "without its [[history]] entry and accepted with it")
    return bad


def main() -> int:
    bad = 0
    with tempfile.TemporaryDirectory(prefix="rcb-ci-selftest-") as tmp:
        clean = {}
        for name in sorted({m[1] for m in MUTATIONS}):
            src = ROOT / "tasks" / name
            if not (src / "task.toml").is_file():
                print(f"FAIL check-ci-selftest: the task {name} this self-test mutates is gone (pick another one in MUTATIONS)")
                return 1
            clean[name] = Path(tmp) / "clean" / name
            shutil.copytree(src, clean[name])
            for cmd in (ISOLATION, RESOURCES, POINTERS, CUTOFFS):
                rc, out = run(cmd, clean[name])
                if rc != 0:
                    print(f"FAIL check-ci-selftest: the unmutated {name} does not pass {Path(cmd[-1]).name}:\n{out[-800:]}")
                    bad += 1
        for k, (what, name, rel, mutate, cmd, expect) in enumerate(MUTATIONS):
            t = Path(tmp) / f"m{k}" / name                      # the directory keeps the task's name (its mode is in it)
            shutil.copytree(clean[name], t)
            try:
                for r, f in (mutate.items() if isinstance(mutate, dict) else [(rel, mutate)]):
                    (t / r).write_text(f((t / r).read_text()))
            except (AssertionError, StopIteration, OSError) as e:
                print(f"FAIL check-ci-selftest [{what}]: the mutation no longer applies to {name} ({e}): update MUTATIONS")
                bad += 1
                continue
            if cmd is IDENTITY:        # a repo-level rule: the broken copy among every other task (links to the real ones)
                for other in (ROOT / "tasks").iterdir():
                    if other.name != name and (other / "task.toml").is_file():
                        (t.parent / other.name).symlink_to(other)
                rc, out = run(cmd, t.parent)
            else:
                rc, out = run(cmd, t)
            if rc == 0 or expect not in out:
                bad += 1
                print(f"FAIL check-ci-selftest [{what}]: {Path(cmd[-1]).name} "
                      + ("PASSED the broken task: the rule is blind" if rc == 0 else f"failed, but not with `{expect}`:\n{out[-600:]}"))
        bad += cutoff_exceptions(Path(tmp))
    if not bad:
        print(f"check-ci-selftest: {len(MUTATIONS)} mutations of real tasks, each caught by its rule")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
