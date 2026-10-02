#!/usr/bin/env python3
"""Switch the agent's network egress for tasks: `public` (default; Harbor's own default) or `allowlist` (model APIs only).

    scripts/set_agent_egress.py public      [task dirs...]     # default: all tasks/*
    scripts/set_agent_egress.py allowlist   [task dirs...]

Why a switch and not a fixed default: the reference solutions we scrub from the agent image are public upstream, so an
agent with open egress *could* fetch them; when a run must rule that out, flip to `allowlist`. The host list below is
what was measured to keep Codex (ChatGPT login), Claude Code and OpenRouter working while GitHub/PyPI are blocked
(2026-09-24). Harbor has no run-time override for [agent].network_mode, so this rewrites task.toml (re-run
`cd tasks && harbor add --scan .` afterwards; digests change)."""
import pathlib, re, sys, tomllib

HOSTS = ["chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com",
         "api.anthropic.com", "*.anthropic.com", "openrouter.ai",
         "*.openai.azure.com", "*.cognitiveservices.azure.com"]
root = pathlib.Path(__file__).resolve().parents[1]
mode = sys.argv[1] if len(sys.argv) > 1 else ""
if mode not in ("public", "allowlist"):
    sys.exit(__doc__)
dirs = [pathlib.Path(d) for d in sys.argv[2:]] or sorted(p for p in (root / "tasks").iterdir() if (p / "task.toml").is_file())
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
        lines.append("allowed_hosts = [" + ", ".join(f'"{h}"' for h in HOSTS) + "]")
    else:
        lines.append("# egress: Harbor default (public). `scripts/set_agent_egress.py allowlist` closes it to the model APIs.")
    s2 = head + "[agent]\n" + "\n".join(lines) + "\n" + (("\n[" + tail) if sep2 else "")
    tomllib.loads(s2); p.write_text(s2)
print(f"{mode}: {len(dirs)} task(s)")
