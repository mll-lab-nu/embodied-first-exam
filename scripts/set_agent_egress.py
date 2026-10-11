#!/usr/bin/env python3
"""The agent's network egress of tasks: `allowlist` (model APIs only; what every task in tasks/ has, PROTOCOL §2.7), or,
for a run's own copy of a task, `only <host>` / `public`.

    scripts/set_agent_egress.py allowlist    [task dirs...]     # default: all tasks/*
    scripts/set_agent_egress.py only <host>[,<host>]  <task dirs...>   # a run's copy: the usage gateway's address alone
    scripts/set_agent_egress.py public       <task dirs...>     # a copy for an experiment: Harbor's default, open

Every task ships with the allowlist (owner, 2026-10-10: with open egress agents downloaded upstream sources, reference
solutions and robot models from their own shell); ci_checks/check-verifier-isolation.sh requires it of every task in
tasks/, with exactly HOSTS. The host list below is what was measured to keep Codex (ChatGPT login), Claude Code and
OpenRouter working while GitHub/PyPI are blocked (2026-09-24). This rewrites task.toml (re-run
`cd tasks && harbor add --scan .` afterwards; digests change).

`only <hosts>`: Harbor can add hosts to a task's allowlist at run time (`--allow-agent-host`) but not take any off, and
the model APIs' hosts also serve what a trial must not reach (account connectors, files, web tools). A run through the
usage gateway therefore runs from a copy of the task whose allowlist is the gateway's address alone
(scripts/run_agent_batch.sh, GATEWAY=1; plus chatgpt.com for Codex with a ChatGPT login, whose start-up lookup needs
it); the gateway forwards the model-API paths and refuses the rest. `only` and
`public` take explicit directories and refuse one inside this repository's tasks/."""
import pathlib, re, sys, tomllib

HOSTS = ["chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com",
         "api.anthropic.com", "*.anthropic.com", "openrouter.ai",
         "*.openai.azure.com", "*.cognitiveservices.azure.com"]
root = pathlib.Path(__file__).resolve().parents[1]
mode = sys.argv[1] if len(sys.argv) > 1 else ""
if mode not in ("public", "allowlist", "only"):
    sys.exit(__doc__)
args = sys.argv[2:]
hosts = HOSTS
if mode == "only":
    if not args or not re.fullmatch(r"[A-Za-z0-9.*:-]+(,[A-Za-z0-9.*:-]+)*", args[0]):
        sys.exit(__doc__)
    hosts, args = args[0].split(","), args[1:]
dirs = [pathlib.Path(d) for d in args]
if mode != "allowlist":      # a run's or an experiment's copy, never the repository's tasks
    inside = [d for d in dirs if d.resolve().is_relative_to(root / "tasks")]
    if not dirs or inside:
        sys.exit(f"`{mode}` takes copies of task directories, outside {root / 'tasks'}" + (f": {inside[0]}" if inside else ""))
dirs = dirs or sorted(p for p in (root / "tasks").iterdir() if (p / "task.toml").is_file())
for d in dirs:
    p = d / "task.toml"; s = p.read_text()
    head, sep, rest = s.partition("[agent]\n")
    if not sep:
        print(f"skip {d.name}: no [agent] section"); continue
    block, sep2, tail = rest.partition("\n[")
    lines = [l for l in block.splitlines() if not re.match(r"\s*(network_mode|allowed_hosts)\s*=", l) and "set_agent_egress" not in l]
    lines = [l for l in lines if l.strip()]
    if mode == "allowlist":
        lines.append('network_mode = "allowlist"      # model APIs only (scripts/set_agent_egress.py); PROTOCOL §4')
        lines.append("allowed_hosts = [" + ", ".join(f'"{h}"' for h in hosts) + "]")
    elif mode == "only":
        lines.append('network_mode = "allowlist"      # this run\'s copy: the usage gateway only (scripts/set_agent_egress.py only)')
        lines.append("allowed_hosts = [" + ", ".join(f'"{h}"' for h in hosts) + "]")
    else:
        lines.append("# egress: Harbor default (public), in this copy only (scripts/set_agent_egress.py public).")
    s2 = head + "[agent]\n" + "\n".join(lines) + "\n" + (("\n[" + tail) if sep2 else "")
    tomllib.loads(s2); p.write_text(s2)
print(f"{mode}: {len(dirs)} task(s)")
