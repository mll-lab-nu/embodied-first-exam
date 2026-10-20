#!/usr/bin/env python3
"""The agent's network egress of tasks: `allowlist` (the model APIs and the package registries; what every task in
tasks/ has, PROTOCOL §2.11), or, for a run's own copy of a task, `only <hosts>` / `public`.

    scripts/set_agent_egress.py allowlist    [task dirs...]     # default: all tasks/*/*
    scripts/set_agent_egress.py only <host>[,<host>]  <task dirs...>   # a run's copy: exactly these hosts
    scripts/set_agent_egress.py package-hosts                   # prints PACKAGE_HOSTS, comma-separated (for the runner)
    scripts/set_agent_egress.py network <task dir>              # prints the task's declared egress: allowlist or open
    scripts/set_agent_egress.py public       <task dirs...>     # a run's copy with no restriction: Harbor's default, open

HOSTS below is the one list, and the one switch: every task ships with it, ci_checks/check-verifier-isolation.sh requires
exactly it of every task in tasks/, the generators and the usage gateway read it from this file's text. It is the model
APIs (what was measured to keep Codex with a ChatGPT login, Claude Code and OpenRouter working, 2026-09-24) and
PACKAGE_HOSTS, the package registries (owner, 2026-10-11: installing packages is part of what an agent may do): PyPI
(pip contacts pypi.org for the index and files.pythonhosted.org for the files) and the apt archives the images'
distributions name in their sources (Debian: deb.debian.org; Ubuntu: archive / security / snapshot.ubuntu.com; plain
HTTP, which Harbor's egress control allows by the request's Host). GitHub, Hugging Face and the general web stay closed:
that is where the benchmarks' sources, demonstrations and trained policies are (with open egress agents downloaded them);
registries mostly are not (the PyPI distributions that do carry a solution: PROTOCOL §2.11). To change what agents reach, edit the two lists, run `allowlist` (it rewrites the
`allowed_hosts` line of every task and leaves the other lines as the generators wrote them), update the generators'
copies of the list, and `cd tasks && harbor add --scan .`.

A task whose author chose open egress declares it, `[metadata] network = "open"` (PROTOCOL §2, Appendix H.6): `allowlist`
leaves such a task alone, and a runner does not narrow its copy to the gateway (`network` prints the declaration).

A run with no restriction at all: `public` on a copy of the task directories (never in tasks/: CI requires the list
there), and run that copy (docs/protocol/running.md).

`only <hosts>`: Harbor can add hosts to a task's allowlist at run time (`--allow-agent-host`) but not take any off, and
the model APIs' hosts also serve what a trial does not get (account connectors, files, web tools). A run through the
usage gateway therefore runs from a copy of the task whose allowlist is the gateway's address and PACKAGE_HOSTS
(scripts/run_agent_batch.sh, GATEWAY=1; plus chatgpt.com for Codex with a ChatGPT login, whose start-up lookup needs
it); the gateway forwards the model-API paths and refuses the rest. `only` and
`public` take explicit directories and refuse one inside this repository's tasks/."""
import pathlib, re, sys
try:
    import tomllib               # Python 3.11+: the result is parsed back as a check; older runner hosts go without
except ModuleNotFoundError:
    tomllib = None

# Two literal lists (the CI check reads them from this file's text; the usage gateway imports them): HOSTS is every
# task's allowlist; PACKAGE_HOSTS, its last entries, is the part that is not a model API.
HOSTS = ["chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com",
         "api.anthropic.com", "*.anthropic.com", "openrouter.ai",
         "*.openai.azure.com", "*.cognitiveservices.azure.com",
         "pypi.org", "files.pythonhosted.org", "deb.debian.org", "security.debian.org", "archive.ubuntu.com",
         "security.ubuntu.com", "snapshot.ubuntu.com"]
PACKAGE_HOSTS = ["pypi.org", "files.pythonhosted.org", "deb.debian.org", "security.debian.org", "archive.ubuntu.com",
                 "security.ubuntu.com", "snapshot.ubuntu.com"]
assert not PACKAGE_HOSTS or HOSTS[-len(PACKAGE_HOSTS):] == PACKAGE_HOSTS
COMMENT = "# model APIs and package registries (scripts/set_agent_egress.py); PROTOCOL §2.11"
root = pathlib.Path(__file__).resolve().parents[1]


def network_of(d: pathlib.Path) -> str:
    """The egress the task declares (`[metadata] network`, default "allowlist"; scripts/task_conventions.py network_of)."""
    m = re.search(r'(?m)^network\s*=\s*"([^"]*)"', (d / "task.toml").read_text().partition("[metadata]\n")[2].partition("\n[")[0])
    return m.group(1) if m else "allowlist"


def main(argv: list) -> None:
    mode = argv[1] if len(argv) > 1 else ""
    if mode == "package-hosts":
        print(",".join(PACKAGE_HOSTS)); sys.exit(0)
    if mode == "network":
        if len(argv) != 3:
            sys.exit(__doc__)
        print(network_of(pathlib.Path(argv[2]))); sys.exit(0)
    if mode not in ("public", "allowlist", "only"):
        sys.exit(__doc__)
    args = argv[2:]
    hosts = HOSTS
    if mode == "only":
        if not args or not re.fullmatch(r"[A-Za-z0-9.*:-]+(,[A-Za-z0-9.*:-]+)*", args[0]):
            sys.exit(__doc__)
        hosts, args = args[0].split(","), args[1:]
    dirs = [pathlib.Path(d) for d in args]
    if mode != "allowlist":      # a run's or an experiment's copy, never the repository's tasks
        inside = [d for d in dirs if (root / "tasks").resolve() in [d.resolve(), *d.resolve().parents]]
        if not dirs or inside:
            sys.exit(f"`{mode}` takes copies of task directories, outside {root / 'tasks'}" + (f": {inside[0]}" if inside else ""))
    if not dirs:
        sys.path.insert(0, str(root / "scripts"))
        import task_conventions as tc
        dirs = tc.iter_tasks(root / "tasks")
    if mode == "allowlist":
        dirs = [d for d in dirs if network_of(d) != "open"]      # the author's choice of open egress is kept
    done = 0
    for d in dirs:
        p = d / "task.toml"; s = p.read_text()
        head, sep, rest = s.partition("[agent]\n")
        if not sep:
            if mode != "allowlist":      # a run's copy that cannot be narrowed must not run
                sys.exit(f"{d}: task.toml has no plain `[agent]` section; nothing written")
            print(f"skip {d.name}: no [agent] section"); continue
        if mode != "allowlist" and re.search(r"(?m)^\s*\[\[?\s*steps\b", s):
            # Harbor lets a step's own agent policy override [agent] (trial/network_policy.py): this script does not rewrite those
            sys.exit(f"{d}: task.toml has [[steps]]; a step's network policy would override [agent]; nothing written")
        block, sep2, tail = rest.partition("\n[")
        if re.search(r"(?m)^\s*allowed_hosts\s*=\s*\[[^\]\n]*$", block):      # a list over several lines: not rewritten line by line
            sys.exit(f"{d}: [agent] allowed_hosts spans several lines; write it on one line; nothing written")
        if mode == "allowlist":          # already on an allowlist: only its host list (and this script's own comment) change
            m = re.search(r'(?m)^allowed_hosts[ \t]*=[ \t]*\[(.*)\][ \t]*$', block)
            if re.search(r'(?m)^network_mode\s*=\s*"allowlist"', block) and m:
                if re.findall(r'"([^"]+)"', m.group(1)) != hosts or re.search(r"# model APIs (only|and PyPI) \(scripts", block):
                    block2 = block[:m.start()] + "allowed_hosts = [" + ", ".join(f'"{h}"' for h in hosts) + "]" + block[m.end():]
                    block2 = re.sub(r"# model APIs (?:only|and PyPI) \(scripts/set_agent_egress\.py\)(; PROTOCOL §[0-9.]+)?",
                                    lambda k: COMMENT if k.group(1) else COMMENT.split(";")[0], block2)
                    s2 = head + "[agent]\n" + block2 + (("\n[" + tail) if sep2 else "")
                    if tomllib is not None:
                        tomllib.loads(s2)
                    p.write_text(s2)
                done += 1; continue
        lines = [l for l in block.splitlines() if not re.match(r"\s*(network_mode|allowed_hosts)\s*=", l) and "set_agent_egress" not in l]
        lines = [l for l in lines if l.strip()]
        if mode == "allowlist":
            lines.append('network_mode = "allowlist"      ' + COMMENT)
            lines.append("allowed_hosts = [" + ", ".join(f'"{h}"' for h in hosts) + "]")
        elif mode == "only":
            lines.append('network_mode = "allowlist"      # this run\'s copy: the usage gateway and the package registries (scripts/set_agent_egress.py only)')
            lines.append("allowed_hosts = [" + ", ".join(f'"{h}"' for h in hosts) + "]")
        else:
            lines.append("# egress: Harbor default (public), in this copy only (scripts/set_agent_egress.py public).")
        s2 = head + "[agent]\n" + "\n".join(lines) + "\n" + (("\n[" + tail) if sep2 else "")
        if tomllib is not None:
            tomllib.loads(s2)
        p.write_text(s2); done += 1
    print(f"{mode}: {done} task(s)")


if __name__ == "__main__":
    main(sys.argv)
