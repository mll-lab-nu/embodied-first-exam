#!/usr/bin/env python3
"""The checks check something: mutation self-test of the rules that guard the trust boundary and the resource caps.

A rule that reads compose files or task.toml by pattern can go blind without anyone noticing (a trailing comment after
`volumes:` can hide every volume of the agent's container from a check that reads the block by pattern). This script copies a few real tasks into a temporary directory, breaks each copy in one
way a rule exists for, and requires that the rule's check fails with the rule's message -- and that the unbroken copy
passes. A mutation that passes is a blind rule: fix the check, not this list.

    python3 ci_checks/check-ci-selftest.py [--tier invariants|advisory|all]    # default: all. Standard library only.

Two tiers. `--tier invariants` (the required CI job `invariants`, ci_checks/run_invariants.sh): the
mutations of the rules that enforce docs/protocol/README.md Appendix H; each must FAIL its check. `--tier advisory` (the job
`advisories`): the mutations of the advisory rules; each must still be reported (a finding, not blocking).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402  (task_dir / iter_tasks: the task tree)
ISOLATION = ["bash", str(ROOT / "ci_checks/check-verifier-isolation.sh")]
RESOURCES = [sys.executable, str(ROOT / "ci_checks/check-resources.py")]
POINTERS = [sys.executable, str(ROOT / "ci_checks/check-agent-pointers.py")]
IDENTITY = ["bash", str(ROOT / "ci_checks/check-tooling-identity.sh")]   # repo-level: runs on a tasks directory (see main)
CUTOFFS = [sys.executable, str(ROOT / "ci_checks/check-cutoffs.py")]
SEEDS = [sys.executable, str(ROOT / "ci_checks/check-seeds.py")]
REALTIME = [sys.executable, str(ROOT / "ci_checks/check-realtime.py")]
VIDEO = [sys.executable, str(ROOT / "ci_checks/check-video.py")]
TWINS = [sys.executable, str(ROOT / "ci_checks/check-twins.py")]              # repo-level-ish: reads the twin next to it
INSTANCE = ["bash", str(ROOT / "ci_checks/check-instance-copies.sh")]
STDIMG = ["bash", str(ROOT / "ci_checks/check-standard-agent-image.sh")]
MONITOR = [sys.executable, str(ROOT / "ci_checks/check-monitor.py"), "--tier", "invariants"]
DIGESTS = ["bash", str(ROOT / "ci_checks/check-dataset-manifest.sh")]
DOCKERFILE = ["bash", str(ROOT / "ci_checks/check-dockerfile.sh")]
FIELDS = ["bash", str(ROOT / "ci_checks/check-task-fields.sh")]
INSTRUCTION = ["bash", str(ROOT / "ci_checks/check-instruction.sh")]
RP_LEAK = ["bash", str(ROOT / "ci_checks/benchmarks/robopaint/invariant-leak.sh")]
EOM_MI = [sys.executable, str(ROOT / "ci_checks/benchmarks/embodied-olympics-match/invariant-match-instance.py")]
ARC_BIND = [sys.executable, str(ROOT / "ci_checks/benchmarks/roboarc/invariant-runtime-binding.py")]
# the checks that enforce Appendix H (run_invariants.sh); every other check here is advisory
INVARIANT_CMDS = (ISOLATION, POINTERS, TWINS, INSTANCE, STDIMG, MONITOR, DIGESTS, RP_LEAK, EOM_MI, ARC_BIND)
WITH_NEIGHBOURS = (IDENTITY, TWINS, EOM_MI)   # run on the broken copy among (links to) every other task

STD = "behavior-boxing-books-up-for-storage-i00-standard"      # a sim sidecar with a trusted cache volume
PRIV = "behavior-boxing-books-up-for-storage-i00-privileged"   # a verifier compose file with a trusted volume
HEAVY = "maniguard-cabinet-pickup-i19-standard"                # an allowlist; a sidecar that holds the GPU
MG_P = "maniguard-cabinet-pickup-i19-privileged"               # its frozen instance is a directory (tests/instance/)
ARC_P = "roboarc-blanket-flatten-01-i01-privileged"            # an instance lock, runtime_binding.json, in tests/ and environment/
EOM_P = "embodied-olympics-match-soccer-match-i00-privileged"  # a match's settings (tests/match_instance.json), its twin's in compose
RT = "humanoidbench-loco-walk-i00-realtime"           # a realtime task: main and sim capped
# benchmarks whose generators have no check mode: their shared files are held together by check-tooling-identity.sh
DTB, DTB_P = "dextoolbench_hammer_claw_hammer_swing_down-standard", "dextoolbench_hammer_claw_hammer_swing_down-privileged"
MJ = "mujoco_playground_aloha_hand_over-standard"              # serves DexToolBench's service (server_mj.py)
MWP, MWP_P = "metaworldplus-coffee-button-i00-standard", "metaworldplus-coffee-button-i00-privileged"
TWIN_P = "robotwin_2_0_grab_roller-privileged"
OPEN = "embodied-olympics-fun-sprint-i00-standard"                      # declares open egress, `[agent] network_mode = "public"` (Appendix H.6)
FUN_P = "embodied-olympics-fun-sprint-i00-privileged"                   # its tooling and grader from a files-only image (COPY --from)
RP = "robopaint-acrylic-applesoranges-i00-privileged"           # a benchmark with its own leak hook (ci_checks/benchmarks/*/invariant-*)


def check_name(cmd: list[str]) -> str:
    """The check a command runs (its script's name; MONITOR's last word is its tier)."""
    return next(Path(c).name for c in cmd if c.endswith((".py", ".sh")))


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


def seeds_block(allowed: str):
    """A `[metadata.seeds]` table with `allowed = [<allowed>]`, where `{d}` is the task's default seed (instance_seed)."""
    def f(s: str) -> str:
        m = re.search(r"(?m)^instance_seed = (-?\d+)", s)
        if not m:
            raise AssertionError("mutation does not apply: no instance_seed")
        return s + "\n[metadata.seeds]\nallowed = [" + allowed.format(d=m.group(1)) + "]\n"
    return f


def sidecar_drift(name: str, file: str, text: str = "# drift\n") -> dict:
    """A drifted copy of a file the task's sidecar takes from a files-only image (environment/sim/Dockerfile), put back
    into environment/sim/: the copies of a shared file must still be one version."""
    import files_image
    src = files_image.copied(tc.task_dir(name) / "environment/sim/Dockerfile")["/srv/" + file]
    return {"+environment/sim/" + file: lambda _: src.read_text() + text}


def npz_text(member: str, text: str) -> bytes:
    """A numpy archive (no numpy needed) whose one member is a 0-d unicode array holding `text`, as np.savez writes it."""
    import io, zipfile
    head = "{'descr': '<U%d', 'fortran_order': False, 'shape': (), }" % len(text)
    head += " " * (-(10 + len(head) + 1) % 64) + "\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(member, b"\x93NUMPY\x01\x00" + len(head).to_bytes(2, "little") + head.encode("latin-1")
                   + text.encode("utf-32-le"))
    return buf.getvalue()


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
    ("a task drops its allowlist (PROTOCOL Appendix H.6: one host list, in every task)",
     HEAVY, TOML, sub(r'^network_mode = "allowlist".*\nallowed_hosts = .*\n', ""), ISOLATION, '[agent].network_mode must be "allowlist"'),
    ("... a privileged twin task drops its allowlist",
     TWIN_P, TOML, sub(r'^network_mode = "allowlist".*\nallowed_hosts = .*\n', ""), ISOLATION, '[agent].network_mode must be "allowlist"'),
    ("a task that declares open egress but keeps a host list in [agent]",
     OPEN, TOML, sub(r'^(network_mode = "public".*\n)', r'\1allowed_hosts = ["pypi.org"]\n'), ISOLATION, "with allowed_hosts"),
    ("a task without an allowlist that does not declare open egress (the default is the allowlist)",
     OPEN, TOML, sub(r'^network_mode = "public".*\n', ""), ISOLATION, '[agent].network_mode must be "allowlist"'),
    ("a copy of the egress in [metadata] (it is [agent] network_mode's alone)",
     OPEN, TOML, sub(r'^(\[metadata\]\n)', r'\1network = "open"\n'), ISOLATION, "[metadata] network = 'open'"),
    # ---- Appendix H.6, the verifier has no network: without [verifier] network_mode Harbor leaves the
    # separate verifier on its environment's baseline, public
    ("a privileged verifier with the network (no [verifier] network_mode)",
     PRIV, TOML, sub(r'^(\[verifier\]\n(?:(?!\[).*\n)*?)network_mode = "no-network".*\n', r"\1"), ISOLATION,
     '[verifier].network_mode must be "no-network"'),
    ("... a standard task's verifier", STD, TOML, sub(r'^(\[verifier\]\n(?:(?!\[).*\n)*?)network_mode = "no-network".*\n', r"\1"),
     ISOLATION, '[verifier].network_mode must be "no-network"'),
    ("... a verifier on the public network", PRIV, TOML, sub(r'^(\[verifier\]\n(?:(?!\[).*\n)*?)network_mode = "no-network"', r'\1network_mode = "public"'),
     ISOLATION, "[verifier].network_mode must be \"no-network\" (PROTOCOL Appendix H.6: the verifier has no network; scripts/task_conventions.py normalize writes it), not 'public'"),
    ("... a verifier environment whose baseline is public", PRIV, TOML, sub(r"^\[verifier\.environment\]\n", '[verifier.environment]\nnetwork_mode = "public"\n'),
     ISOLATION, "[verifier.environment] sets network_mode = 'public'"),
    ("a verifier service on a network of its own (Harbor's deny-all skips it)",
     PRIV, TEST_COMPOSE, in_service("main", "    networks: [default]"), ISOLATION, "service main: `networks` is not allowed"),
    ("... `network_mode: host` in the verifier's compose file",
     PRIV, TEST_COMPOSE, in_service("main", "    network_mode: host"), ISOLATION, "service main: `network_mode: host` is not allowed"),
    ("the instruction no longer states the external-material rule",
     STD, "instruction.md", sub(r"(?ms)^## External material\n.*?(?=^## )", ""), RESOURCES, "does not state `## External material`"),
    ("the frozen instance the agent reads names where its scene came from",
     PRIV, "environment/instance.json", sub(r"^\{", '{"source_url": "https://example.org/demos/data/manifest.json", ', count=1, flags=0),
     POINTERS, "key `source_url` locates upstream material"),
    ("... names the recording its reference replays",
     PRIV, "environment/instance.json", sub(r"^\{", '{"source": {"file": "demos/boxing_books_017.hdf5", "demo": 3}, ', count=1, flags=0),
     POINTERS, "file `boxing_books_017.hdf5` locates upstream material"),
    ("... names the demonstration its scene was restored from (the reference replays that demonstration's actions)",
     PRIV, "environment/instance.json", sub(r"^\{", '{"demo": "boxing_books_demo_17", ', count=1, flags=0),
     POINTERS, "id `demo` locates upstream material"),
    ("... in a string member of a numpy archive the agent reads (DexJoCo's instance.npz `meta`)",
     PRIV, "+environment/extra.npz", lambda s: npz_text("meta.npy", '{"source": "x", "demo": "water_plant_demo_10_2026"}'),
     POINTERS, "environment/extra.npz[meta.npy]:1: id `demo`"),
    ("a step with a network policy of its own (Harbor would let it override [agent])",
     STD, TOML, append('\n[[steps]]\nname = "s1"\n[steps.agent]\nnetwork_mode = "public"\n'), ISOLATION, "a step sets its own network policy"),
    ("the instruction links the upstream repository",
     STD, "instruction.md", append("\nThe benchmark's code: https://github.com/StanfordVL/BEHAVIOR-1K\n"), POINTERS,
     "URL `https://github.com/StanfordVL/BEHAVIOR-1K` locates upstream material"),
    ("environment/Dockerfile copies itself into the image, with an upstream URL in it",
     STD, "environment/Dockerfile", append("# https://github.com/StanfordVL/BEHAVIOR-1K\nCOPY . /opt/ctx/\n"), POINTERS,
     "environment/Dockerfile:"),
    # ---- PROTOCOL §5: a standard-mode success condition in terms the agent can observe (advisory)
    ("the standard instruction states a condition in the checker's terms (an object-local axis, a predicate, an indexed label)",
     STD, "instruction.md", append("\nAlso required: mug_0 local +y within 45 deg of world +x (is_axis_aligned).\n"), INSTRUCTION,
     "an object-local axis 'local y'"),
    ("the instruction states the external-material rule in other words",
     STD, "instruction.md", sub(r"This is an honour rule; trials are reviewed\.", "Do as you like."), RESOURCES,
     "does not state `## External material`"),
    # ---- the agent's time cutoff (PROTOCOL §2): the task's own number; task.toml, the instruction and the sim service agree
    ("task.toml's cutoff changed without normalizing (the instruction still states the old number)",
     STD, TOML, sub(r"(^\[agent\]\n(?:(?!\[).*\n)*?timeout_sec = )[0-9.]+", r"\g<1>1234.0"), CUTOFFS,
     "does not end with the `## Time limit` section rendered for its 1234 s"),
    ("a cutoff above the 14400 s cap",
     STD, TOML, sub(r"(^\[agent\]\n(?:(?!\[).*\n)*?timeout_sec = )[0-9.]+", r"\g<1>28800.0"), CUTOFFS, "is above the 14400 s cap"),
    ("a cutoff that is not a whole number of seconds",
     PRIV, TOML, sub(r"(^\[agent\]\n(?:(?!\[).*\n)*?timeout_sec = )[0-9.]+", r"\g<1>3600.5"), CUTOFFS,
     "is not a whole positive number of seconds"),
    ("a task.toml without the agent's cutoff",
     PRIV, TOML, sub(r"(^\[agent\]\n(?:(?!\[).*\n)*?)timeout_sec = [0-9.]+[^\n]*\n", r"\g<1>"), CUTOFFS,
     "has no `[agent] timeout_sec`"),
    ("the instruction's cutoff sentence with another number",
     STD, "instruction.md", sub(r"^You have \d+ seconds to complete this task\.", "You have 28800 seconds to complete this task."),
     CUTOFFS, "does not end with the `## Time limit` section"),
    ("the instruction without the cutoff sentence",
     PRIV, "instruction.md", sub(r"^You have \d+ seconds to complete this task\.[^\n]*\n\n", ""), CUTOFFS, "the sentence is missing"),
    ("the cutoff section is not the end of the instruction: something follows it",
     PRIV, "instruction.md", append("\nOne more remark after the time limit.\n"), CUTOFFS, "does not end with the `## Time limit` section"),
    ("the cutoff paragraphs under the title instead of at the end",
     PRIV, "instruction.md",
     lambda s: (lambda head, sep, block: head.split("\n", 1)[0] + "\n\n" + block.split("\n", 1)[1] + "\n" + head.split("\n", 1)[1])(*s.partition("\n## Time limit\n"))
     if "\n## Time limit\n" in s else (_ for _ in ()).throw(AssertionError("no `## Time limit` section")),
     CUTOFFS, "does not end with the `## Time limit` section"),
    ("a privileged task with the standard modes' second paragraph",
     PRIV, "instruction.md", sub(r"only what is in `/app/output/` at that moment is\s+graded", "the episode is graded as it stands"),
     CUTOFFS, "does not end with the `## Time limit` section"),
    ("the closing sections in another order (`## Time limit` before `## Resources`)",
     STD, "instruction.md",
     lambda s: (lambda a, b, c: a + "\n## Time limit\n" + c.rstrip("\n") + "\n\n## Resources\n" + b.rstrip("\n") + "\n")(
         s.split("\n## Resources\n")[0], *s.split("\n## Resources\n")[1].split("\n## Time limit\n")),
     CUTOFFS, "does not end with the `## Time limit` section"),
    ("... which the resources check refuses too (the limits paragraph is the last thing before `## Time limit`)",
     STD, "instruction.md",
     lambda s: (lambda a, b, c: a + "\n## Time limit\n" + c.rstrip("\n") + "\n\n## Resources\n" + b.rstrip("\n") + "\n")(
         s.split("\n## Resources\n")[0], *s.split("\n## Resources\n")[1].split("\n## Time limit\n")),
     RESOURCES, "does not end (before `## Time limit`) with the `## Resources` paragraph"),
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
    ("the README's `Agent time budget` row with another number than the task's cutoff",
     STD, "README.md", sub(r"^(\| Agent time budget \| )\d+ s;", r"\g<1>28800 s;"), CUTOFFS, "README.md's `Agent time budget` row does not say"),
    ("the sim service is told another wall clock than the task's cutoff",
     STD, COMPOSE, sub(r'(RCB_WALL_CLOCK_S: ")\d+', r"\g<1>3600"), CUTOFFS, "RCB_WALL_CLOCK_S = 3600, the task's cutoff is"),
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
    ("a build cache read from a host directory", STD, COMPOSE, in_service("main", "    build:\n      cache_from: [\"type=local,src=/\"]"), ISOLATION, "is not a registry image reference"),
    ("a sidecar built from a context outside the task", STD, COMPOSE, sub(r"^      context: \./sim$", "      context: ../.."), ISOLATION, "must be a relative path inside environment/"),
    ("a sidecar build with a secret", STD, COMPOSE, in_service("sim", "      secrets: [tok]", after=r"^      context: "), ISOLATION, "service sim: `build` is not allowed beyond"),
    ("another compose file included", STD, COMPOSE, lambda s: "include:\n  - extra.yaml\n" + s, ISOLATION, "top-level `include` is not allowed"),
    ("a service whose keys are indented deeper than the reader looks",
     STD, COMPOSE, sub(r"(?s)^  main:\n.*?(?=^  sim:)", "  main:\n      networks: [default]\n      depends_on: [sim]\n"), ISOLATION, "at an unexpected indentation"),
    ("the kernel's OOM killer switched off for a container", STD, COMPOSE, in_service("sim", "    oom_kill_disable: true"), ISOLATION, "`oom_kill_disable` is not allowed"),
    # ---- pinned images in every stage and file; the verifier's log directory emptied, not a look-alike of it
    ("a second, unpinned stage in the verifier's Dockerfile", STD, TEST_DF, append("FROM python:latest\nCOPY --from=0 /tests /tests\n"), DOCKERFILE, "must be a pinned registry image"),
    ("a sidecar image whose tag is a variable", STD, COMPOSE, sub(r"^(    image: ghcr\.io/mll-lab-nu/efe:monitor)-\S+", r"\1-${TAG:-latest}"), DOCKERFILE, "must be pinned"),
    ("tests/test.sh removes only a look-alike of the verifier's logs",
     STD, TEST_SH, sub(r"^rm -rf /logs/verifier/\*", "rm -rf /logs/verifier/*.bak"), ISOLATION, "must empty /logs/verifier"),
    # ---- review round 3, M6: benchmarks without a generator check mode (one task hand-edited, its digest refreshed)
    ("DexToolBench: one task's grader is another file of the files image", DTB, TEST_DF,
     sub(r" /standard/tests/grade\.py /tests/grade\.py$", " /privileged/tests/grade.py /tests/grade.py"), IDENTITY,
     "dextoolbench: 2 versions of standard tests/grade.py"),
    ("... its service", DTB, None, sidecar_drift(DTB, "server_mj.py"), IDENTITY, "environment/sim/server_mj.py differs from images/mujoco/limited/server_mj.py"),
    ("... its client (from the standard client image, another digest)", DTB, "environment/Dockerfile",
     sub(r"(efe:standard-files-\S+@sha256:)[0-9a-f]{64}( /rcb1\.py )", r"\g<1>" + "0" * 64 + r"\2"), IDENTITY, "not the pinned"),
    ("... its tooling module (from the files image, another digest)", DTB_P, TEST_DF,
     sub(r"(efe:dextoolbench-files-\S+@sha256:)[0-9a-f]{64}( /privileged/environment/rcb_dtb\.py )", r"\g<1>" + "0" * 64 + r"\2"), IDENTITY,
     "not the pinned"),
    ("... tests/test.sh without the resource step", DTB_P, TEST_SH, NO_TRAP, IDENTITY, "dextoolbench: 2 versions of privileged tests/test.sh"),
    ("MuJoCo Playground (ALOHA): the same service edited", MJ, None, sidecar_drift(MJ, "server_mj.py"), IDENTITY, "dextoolbench: 2 versions of standard environment/sim/server_mj.py"),
    ("MetaWorld+: one task's service edited", MWP, None, sidecar_drift(MWP, "server_mw.py"), IDENTITY, "environment/sim/server_mw.py differs from images/metaworld/standard/server_mw.py"),
    ("... its grader (from the files image, another digest)", MWP_P, TEST_DF,
     sub(r"(efe:metaworldplus-files-\S+@sha256:)[0-9a-f]{64}( /privileged/environment/mw_tool\.py )", r"\g<1>" + "0" * 64 + r"\2"), IDENTITY,
     "not the pinned"),
    ("... its tooling module", MWP, None, sidecar_drift(MWP, "mw_tool.py"), IDENTITY, "metaworldplus: 2 versions of mw_tool.py"),
    ("... tests/test.sh without the resource step", MWP, TEST_SH, NO_TRAP, IDENTITY, "metaworldplus: 2 versions of standard tests/test.sh"),
    ("RoboTwin: a privileged task's tests/test.sh without the resource step", TWIN_P, TEST_SH, NO_TRAP, IDENTITY, "robotwin_2_0: 2 versions of privileged tests/test.sh"),
    ("... its grader", TWIN_P, "tests/grade.py", append("# drift\n"), IDENTITY, "robotwin_2_0: 2 versions of privileged tests/grade.py"),
    # ---- files from a files-only image (images/<name>/FILES.json) count as copies of their benchmark's shared files
    ("Embodied Olympics - Fun: a verifier takes its grader from an image other than the pinned files image", FUN_P, TEST_DF,
     sub(r"(efe:embodied-olympics-fun-files-\S+@sha256:)[0-9a-f]{64}( /grade\.py )", r"\g<1>" + "0" * 64 + r"\2"), IDENTITY,
     "not the pinned"),
    ("... a standard sidecar's tooling edited (compared with the files image's)", OPEN, None,
     sidecar_drift(OPEN, "rcb_rfo.py"), IDENTITY, "embodied-olympics: 2 versions of rcb_rfo.py"),
    ("... a sidecar takes its shared files from an image other than the pinned files image", OPEN, "environment/sim/Dockerfile",
     sub(r"(efe:embodied-olympics-fun-files-\S+@sha256:)[0-9a-f]{64}", r"\g<1>" + "0" * 64), IDENTITY, "not the pinned"),
    # ---- caps (PROTOCOL §6): every container's, where Harbor and docker read them, and only those
    ("a GPU service without its GPU-memory cap", HEAVY, COMPOSE, sub(r"^    x-gpu-memory-gb: .*\n", ""), RESOURCES,
     "reserves a GPU but sets no `x-gpu-memory-gb`"),
    ("a separate verifier's GPU service without its GPU-memory cap", PRIV, TEST_COMPOSE, sub(r"^    x-gpu-memory-gb: .*\n", ""),
     RESOURCES, "tests/docker-compose.yaml: service main reserves a GPU but sets no `x-gpu-memory-gb`"),
    ("`[environment].gpus` (Harbor's local docker refuses it)", RT, TOML, sub(r"^(\[environment\]\n)", r"\1gpus = 1\n"),
     RESOURCES, "[environment].gpus"),
    ("the old minimums table brought back", RT, TOML, sub(r"^(\[verifier\]\n)", r"[metadata.resources]\nmin_cpus = 2.0\n\n\1"),
     RESOURCES, "task.toml has [metadata.resources]"),
    ("a sidecar without a memory cap", RT, COMPOSE, sub(r"^(  sim:\n(?:    .*\n)*?)    mem_limit: \d+m   # rcb-monitor\n", r"\1"),
     RESOURCES, "service sim: no `mem_limit`"),
    ("a declared cap that docker does not apply",
     STD, COMPOSE, sub(r"^    mem_limit: \d+m(   # rcb-monitor)$", r"    mem_limit: 1024m\1"), RESOURCES, "declare the cap that is applied"),
    # ---- seeds (PROTOCOL §2): the runner draws the seed; no other seed's instance where the agent's image is built
    ("the default seed is not among the allowed ones",
     TWIN_P, TOML, seeds_block("12345"), SEEDS, "is not in seeds.allowed"),
    ("an allowed seed without its frozen instance",
     TWIN_P, TOML, seeds_block("{d}, 12345"), SEEDS, "has no frozen instance"),
    ("a second copy of the default seed (it is instance_seed alone)",
     TWIN_P, TOML, append("\n[metadata.seeds]\ndefault = 0\n"), SEEDS, "[metadata.seeds] has `default`"),
    ("a task.toml without instance_seed",
     TWIN_P, TOML, sub(r"^instance_seed = .*\n", ""), SEEDS, "no `instance_seed`"),
    ("another seed's instance in the agent's build context",
     TWIN_P, "+environment/seeds/7/instance.json", append("{}"), SEEDS, "a `seeds` directory where the agent's image"),
    # PROTOCOL §2: scene dynamics, the task's own declaration (no table)
    ("a task.toml without dynamics",
     TWIN_P, TOML, sub(r'^dynamics = .*\n', ""), FIELDS, "[metadata].dynamics must be declared"),
    # copies of what another source says (the mode: the directory's suffix; the reset budget: the sim service's default)
    ("a copy of the mode in [metadata]",
     TWIN_P, TOML, sub(r'^(dynamics = .*\n)', r'\1mode = "privileged"\n'), FIELDS, "[metadata].mode"),
    ("a copy of the reset budget in [metadata]",
     STD, TOML, sub(r'^(dynamics = .*\n)', r'\1reset_budget = 0\n'), FIELDS, "[metadata].reset_budget"),
    # ---- Appendix H.7: twins share cutoff, seeds and frozen instance; H.3: no simulator in the agent's image; H.1: the
    # monitor's own isolation and the sanitize step; H.8: DIGEST; H.2: a benchmark's own leak hook
    ("a standard task whose cutoff is not its privileged twin's", STD, TOML,
     sub(r"(^\[agent\]\n(?:(?!\[).*\n)*?timeout_sec = )[0-9.]+", r"\g<1>1234.0"), TWINS, "the twins have the same cutoff"),
    ("a standard task whose allowed seeds are not its privileged twin's", STD, TOML,
     seeds_block("{d}, 12345"), TWINS, "differ from its privileged twin's"),
    ("the verifier's frozen instance is not the one the task runs from", PRIV, "tests/instance.json",
     sub(r"^\{", '{"x": 1, ', count=1, flags=0), INSTANCE, "differ, or one is missing"),
    ("a file of the verifier's instance directory is not the one the task runs from", MG_P, "tests/instance/instance.json",
     sub(r"^\{", '{"x": 1, ', count=1, flags=0), INSTANCE, "differ"),
    ("the verifier's instance lock is not the one the task runs from", ARC_P, "tests/runtime_binding.json",
     sub(r"^\{", '{"x": 1, ', count=1, flags=0), INSTANCE, "differ"),
    ("the tooling a RoboARC container loads is not the one its runtime binding pins", ARC_P, "environment/runtime_binding.json",
     sub(r'"tooling_sha256": "[0-9a-f]{64}"', '"tooling_sha256": "' + "0" * 64 + '"', flags=0), ARC_BIND,
     "the simulator refuses this session"),
    ("a match's frozen settings differ from its realtime twin's", EOM_P, "tests/match_instance.json",
     sub(r'"seed": 7\b', '"seed": 8', flags=0), EOM_MI, "has seed = 8"),
    ("a match's frozen level differs from its realtime twin's", EOM_P, "tests/match_instance.json",
     sub(r'"level": 2\b', '"level": 0', flags=0), EOM_MI, "has level = 0"),
    ("a match's frozen slowdown differs from its realtime twin's", EOM_P, "tests/match_instance.json",
     sub(r'"slowdown": 5\b', '"slowdown": null', flags=0), EOM_MI, "has slowdown = None"),
    ("a standard task's agent image takes the sidecar's code", STD, "environment/Dockerfile",
     append("COPY sim/ /opt/sim/\n"), STDIMG, "name files outside sim/ only"),
    ("the monitor sidecar gets a network", STD, COMPOSE, sub(r"^    network_mode: none\n", ""), MONITOR,
     "missing `network_mode: none`"),
    ("the monitor sidecar runs another image", STD, COMPOSE,
     sub(r"^    image: ghcr.io/mll-lab-nu/efe:monitor-\S+", "    image: python:3.12-slim"), MONITOR,
     "not the block images/monitor/rcb_monitor/inject.py writes"),
    ("the monitor sidecar mounts code over the image's", STD, COMPOSE,
     sub(r"^(      - \./rcb_monitor/limits\.json:/opt/rcb_monitor/limits\.json:ro\n)",
         r"\1      - ./rcb_monitor/monitor.py:/opt/rcb_monitor/monitor.py:ro\n"), MONITOR,
     "not the block images/monitor/rcb_monitor/inject.py writes"),
    ("the verifier image no longer takes rcb_limits.py from the monitor image", STD, "tests/Dockerfile",
     sub(r"^COPY --from=\S+ /opt/rcb_monitor/rcb_limits\.py /tests/rcb_limits\.py\n", ""), MONITOR,
     "does not COPY rcb_limits.py from"),
    ("tests/test.sh no longer sanitizes /app/output before the grader", STD, TEST_SH,
     sub(r"^.*rcb_limits\.py sanitize /app/output.*\n", ""), MONITOR, "no `rcb_limits.py sanitize /app/output` line"),
    ("a task file changed without its DIGEST", PRIV, "README.md", append("\nedited\n"), DIGESTS,
     "a DIGEST that is not the digest of the task's current files"),
    ("a RoboPaint agent image gets a file derived from the target", RP, "+environment/target_strokes.json", append("{}"),
     RP_LEAK, "not an allowed agent-side file"),
    ("a RoboPaint agent image takes a grader from the files-only image", RP, "environment/Dockerfile",
     sub(r"^(COPY --from=\S+) /rcb_brush\.py /opt/tools/rcb_brush\.py$", r"\1 /rcb_brush_score.py /opt/tools/rcb_brush.py"),
     RP_LEAK, "only an allowed agent-side file of the pinned"),
    ("a RoboPaint standard agent image takes a non-client file from the standard client image", RP.replace("-privileged", "-standard"),
     "environment/Dockerfile", sub(r"^(COPY --from=\S+standard-files\S+) /rcb_client\.py /rcb1\.py /opt/tools/$",
                                    r"\1 /rcb_client.py /rcb1.py /realtime/rcb_client.py /opt/tools/"),
     RP_LEAK, "only an allowed agent-side file of the pinned"),
    ("a RoboPaint task dir's own rcb_brush.py with grader code, next to the files-only image's", RP, "+environment/rcb_brush.py",
     append("def score_canvas(sheet):\n    pass\n"), RP_LEAK, "grader code ('def score_canvas') in the agent's tooling"),
    # PROTOCOL §2: a realtime task declares its slowdown S and its reset budget once, in its sim service
    ("a copy of the slowdown S in [metadata]",
     "humanoidbench-loco-walk-i00-realtime", TOML, sub(r'^(dynamics = .*\n)', r'\1slowdown = 1\n'), REALTIME,
     "[metadata] slowdown copies its service's default"),
    ("a realtime service whose reset budget is not the one its instruction states",
     "humanoidbench-loco-walk-i00-realtime", COMPOSE, sub(r"RCB_RESET_BUDGET:-50\}", "RCB_RESET_BUDGET:-7}"),
     REALTIME, "instruction.md states 50 resets, but the task's reset budget is 7"),
    ("a realtime service that declares no reset budget",
     "humanoidbench-loco-walk-i00-realtime", COMPOSE, sub(r"^\s*RCB_RESET_BUDGET:.*\n", ""), REALTIME,
     "must declare its reset budget"),
    # PROTOCOL §4: every graded trial leaves a replay video
    ("a privileged verifier that renders no video", TWIN_P, None,
     {"tests/grade.py": sub(r"\.mp4\b", ".bin", count=0), "tests/rcb_traj.py": sub(r"\.mp4\b", ".bin", count=0)}, VIDEO,
     "its verifier renders no replay video"),
    ("a standard task whose sim video is not collected", "humanoidbench-loco-walk-i00-standard", TOML,
     sub(r'^\s*\{ source = "/data/replay\.mp4", service = "sim" \},\n', ""), VIDEO, "the sim's video is never collected"),
    ("a video time bound shorter than the verdict replay's", MWP_P, "+tests/grading.json",
     append('{"replay_timeout_s": 1400, "video_timeout_s": 300}'), VIDEO, "shorter than the verdict replay's 1400 s"),
]


def run(cmd: list[str], task: Path) -> tuple[int, str]:
    r = subprocess.run(cmd + [str(task)], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def twin_cutoffs(tmp: Path) -> int:
    """The cutoff is each task's own (PROTOCOL §2): normalize renders a changed `[agent] timeout_sec` into the
    instruction's closing section, the README row and the sim service's wall clock, check-cutoffs.py accepts the task on
    its own, and check-twins.py refuses it next to its privileged twin, whose number differs (`same_cutoff_as`, H.7). Returns the
    number of failures."""
    import tomllib
    bad = 0

    def expect(ok: bool, what: str, out: str = "") -> None:
        nonlocal bad
        if not ok:
            bad += 1
            print(f"FAIL check-ci-selftest [twin cutoffs: {what}]" + (f":\n{out[-600:]}" if out else ""))

    work = tmp / "twins"
    shutil.copytree(tc.task_dir(STD), work / STD)   # alone first; its twin joins it below
    t = work / STD
    sec = int(tomllib.loads((t / "task.toml").read_text())["agent"]["timeout_sec"]) // 2   # a number that is not its twin's
    toml = (t / "task.toml").read_text()
    (t / "task.toml").write_text(sub(r"(^\[agent\]\n(?:(?!\[).*\n)*?timeout_sec = )[0-9.]+", rf"\g<1>{sec}.0")(toml))
    r = subprocess.run([sys.executable, str(ROOT / "scripts/task_conventions.py"), str(t)], capture_output=True, text=True)
    expect(r.returncode == 0, "normalize a task whose cutoff changed", r.stdout + r.stderr)
    expect(f"\nYou have {sec} seconds to complete this task." in (t / "instruction.md").read_text(),
           f"the instruction does not say {sec} seconds after normalize")
    expect(f"| Agent time budget | {sec} s;" in (t / "README.md").read_text(), f"the README row does not say {sec} s")
    expect(f'RCB_WALL_CLOCK_S: "{sec}"' in (t / "environment/docker-compose.yaml").read_text(),
           f"the sim service's wall clock is not {sec}")
    rc, out = run(CUTOFFS, t)
    expect(rc == 0, "check-cutoffs.py on the normalized task alone", out)
    shutil.copytree(tc.task_dir(PRIV), work / PRIV)
    r = subprocess.run(TWINS + [str(t)], capture_output=True, text=True)
    out = r.stdout + r.stderr
    expect(r.returncode != 0 and "the twins have the same cutoff" in out, "check-twins.py must refuse twins with two cutoffs", out)
    if not bad:
        print(f"check-ci-selftest: a task's own cutoff ({sec} s) rendered by normalize and accepted alone, refused next to its "
              "privileged twin")
    return bad


def gpu_rule_change(tmp: Path) -> int:
    """A rule's GPU-memory cap changes (PROTOCOL §6): normalize replaces the generated `x-gpu-memory-gb` line with the new
    value (never keeps the old one), check-resources.py then refuses the copy against the repository's rule with a
    message that names the fix, and normalize with the repository's rule brings the old value back and passes; inject.py
    run alone on a task whose compose file it generated keeps main's processes cap. Returns the number of failures."""
    sys.path.insert(0, str(ROOT / "images/monitor"))
    from rcb_monitor import inject
    bad = 0

    def expect(ok: bool, what: str, out: str = "") -> None:
        nonlocal bad
        if not ok:
            bad += 1
            print(f"FAIL check-ci-selftest [GPU rule change: {what}]" + (f":\n{out[-600:]}" if out else ""))

    t = tmp / "gpurule" / HEAVY
    shutil.copytree(tc.task_dir(HEAVY), t)
    comp = t / "environment/docker-compose.yaml"
    svc, old = next((n, c["gpu_memory_gb"]) for n, c in inject.service_caps(comp.read_text()).items()
                    if c.get("gpu") and c.get("gpu_memory_gb"))
    new = old + 7
    rules = tmp / "gpurule" / "task_resources.toml"   # the repository's rules plus a last one for this task: GPU + 7
    r = tc.rule_for(t)
    line = ", ".join(f"{k} = {v:g}" if isinstance(v, float) else f"{k} = {v}" for k, v in
                     dict(r["services"][svc], gpu_memory_gb=new).items())
    extra = "".join(f"{n} = {{ " + ", ".join(f"{k} = {v:g}" for k, v in c.items()) + " }\n"
                    for n, c in r["services"].items() if n != svc)
    gt = r.get("gpu_types")
    rules.write_text(tc.RESOURCES_FILE.read_text() + f"\n[[cap]]\nmatch = '^{re.escape(HEAVY)}$'\n{svc} = {{ {line} }}\n"
                     + extra + (("gpu_types = [" + ", ".join(f'"{x}"' for x in gt) + "]\n") if gt else ""))
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import task_conventions as tc; from pathlib import Path; "
            "tc.RESOURCES_FILE = Path(sys.argv[2]); tc.normalize(Path(sys.argv[3]))")
    p = subprocess.run([sys.executable, "-c", code, str(ROOT / "scripts"), str(rules), str(t)], capture_output=True, text=True)
    expect(p.returncode == 0, "normalize with the changed rule", p.stdout + p.stderr)
    got = inject.service_caps(comp.read_text())[svc]["gpu_memory_gb"]
    n = sum(1 for ln in comp.read_text().splitlines() if ln.strip().startswith(inject.GPU_KEY + ":"))
    expect(got == new and n == 1, f"service {svc}: x-gpu-memory-gb {got} ({n} line(s)) after normalize, the rule says {new:g}")
    rc, out = run(RESOURCES, t)
    expect(rc != 0 and "declare the cap that is applied" in out and "task_conventions.py" in out,
           "check-resources.py must refuse the copy against the repository's rule, naming normalize", out)
    p = subprocess.run([sys.executable, str(ROOT / "scripts/task_conventions.py"), str(t)], capture_output=True, text=True)
    rc, out = run(RESOURCES, t)
    expect(p.returncode == 0 and rc == 0 and inject.service_caps(comp.read_text())[svc]["gpu_memory_gb"] == old,
           "normalize with the repository's rule restores its value and passes", p.stdout + p.stderr + out)
    gen = next(x for x in tc.iter_tasks() if inject.is_generated((x / "environment/docker-compose.yaml").read_text()))
    g = tmp / "gpurule" / gen.name
    shutil.copytree(gen, g)
    before = inject.service_caps((g / "environment/docker-compose.yaml").read_text())["main"]["pids"]
    p = subprocess.run([sys.executable, str(ROOT / "images/monitor/rcb_monitor/inject.py"), str(g)], capture_output=True, text=True)
    after = inject.service_caps((g / "environment/docker-compose.yaml").read_text())["main"]["pids"]
    expect(p.returncode == 0 and before and after == before,
           f"inject.py alone on {gen.name} (a generated compose file): main's pids_limit {before} -> {after}", p.stderr)
    if not bad:
        print(f"check-ci-selftest: a rule's GPU-memory cap change ({old:g} -> {new:g} GiB on {svc}) reaches the compose file "
              "through normalize, and inject.py alone keeps a generated file's caps")
    return bad


def main(argv: list[str]) -> int:
    tier = argv[1] if argv[:1] == ["--tier"] and len(argv) > 1 else "all"
    if tier not in ("invariants", "advisory", "all"):
        raise SystemExit("--tier invariants|advisory|all")
    sel = [m for m in MUTATIONS if tier == "all" or (any(m[4] is c for c in INVARIANT_CMDS) == (tier == "invariants"))]
    bad = 0
    with tempfile.TemporaryDirectory(prefix="rcb-ci-selftest-") as tmp:
        clean = {}
        for name in sorted({m[1] for m in sel}):
            src = tc.task_dir(name)
            if not (src / "task.toml").is_file():
                print(f"FAIL check-ci-selftest: the task {name} this self-test mutates is gone (pick another one in MUTATIONS)")
                return 1
            clean[name] = Path(tmp) / "clean" / name
            shutil.copytree(src, clean[name])
            for cmd in sorted({id(m[4]): m[4] for m in sel if m[1] == name and m[4] not in WITH_NEIGHBOURS and m[4] is not DIGESTS}.values()):
                rc, out = run(cmd, clean[name])
                if rc != 0:
                    print(f"FAIL check-ci-selftest: the unmutated {name} does not pass {check_name(cmd)}:\n{out[-800:]}")
                    bad += 1
        for k, (what, name, rel, mutate, cmd, expect) in enumerate(sel):
            t = Path(tmp) / f"m{k}" / name                      # the directory keeps the task's name (its mode is in it)
            shutil.copytree(clean[name], t)
            try:
                for r, f in (mutate.items() if isinstance(mutate, dict) else [(rel, mutate)]):
                    if r.startswith("+"):                   # a file the mutation adds
                        r = r[1:]
                        (t / r).parent.mkdir(parents=True, exist_ok=True)
                        data = f("")
                        (t / r).write_bytes(data) if isinstance(data, bytes) else (t / r).write_text(data)
                        continue
                    (t / r).write_text(f((t / r).read_text()))
            except (AssertionError, StopIteration, OSError) as e:
                print(f"FAIL check-ci-selftest [{what}]: the mutation no longer applies to {name} ({e}): update MUTATIONS")
                bad += 1
                continue
            if any(cmd is c for c in WITH_NEIGHBOURS):   # the broken copy among every other task (links to the real ones)
                for other in tc.iter_tasks():
                    if other.name != name:
                        (t.parent / other.name).symlink_to(other)
                rc, out = run(cmd, t.parent if cmd is IDENTITY else t)
            else:
                rc, out = run(cmd, t)
            if rc == 0 or expect not in out:
                bad += 1
                print(f"FAIL check-ci-selftest [{what}]: {check_name(cmd)} "
                      + ("PASSED the broken task: the rule is blind" if rc == 0 else f"failed, but not with `{expect}`:\n{out[-600:]}"))
        if tier != "advisory":
            bad += twin_cutoffs(Path(tmp))
            bad += gpu_rule_change(Path(tmp))
    if not bad:
        print(f"check-ci-selftest ({tier}): {len(sel)} mutations of real tasks, each caught by its rule")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
