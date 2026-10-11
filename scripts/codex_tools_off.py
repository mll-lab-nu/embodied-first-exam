#!/usr/bin/env python3
"""A Codex config.toml that offers the model no tool run at the provider (PROTOCOL D11, §2.11).

    scripts/codex_tools_off.py [<config.toml>] > <the config a run passes as --ak config=>

Under a ChatGPT login Codex hands the model the account's connectors and apps (`mcp__codex_apps__*`: web open and
search, GitHub, mail, drives), an image generator and plugin installs. They run at OpenAI and are reached through
chatgpt.com, the model's own host: past `web_search = "disabled"`, the egress allowlist and the usage gateway.
`scripts/run_agent_batch.sh` therefore starts every Codex run (`WEB_SEARCH=disabled`, the default) from a config with
the keys of OFF set to false: this script's output, the caller's config (`AGENT_CONFIG`) with those keys added.
Measured on Codex 0.160.1 (2026-10-10): with these keys a ChatGPT login and an API key list the same 8 local tools;
`features.apps = false` alone leaves the image generator.

A config that sets one of the keys itself may set it to false only (that line is replaced by this script's own);
anything else is refused (exit 2), never overridden silently. The keys are written where TOML lets them stand: inside
the config's own `[features]` / `[apps]` / `[apps._default]` table if it has one, else as dotted keys before its
first table. Standard library only; with Python 3.11+ the result is parsed back and checked."""
import re
import sys

try:
    import tomllib
except ModuleNotFoundError:  # older runner hosts go without the parse-back
    tomllib = None

OFF = ["features.apps", "features.plugins", "features.remote_plugin", "features.tool_suggest",
       "features.image_generation", "features.skill_mcp_dependency_install", "apps._default.enabled"]
HEADER = re.compile(r"^\s*\[\s*([^\[\]]+?)\s*\]\s*(#.*)?$")
ARRAY = re.compile(r"^\s*\[\[")
ASSIGN = re.compile(r"^\s*([A-Za-z0-9_.\"' -]+?)\s*=\s*(.*?)\s*$")


def path(text):
    return ".".join(p.strip().strip("\"'") for p in text.split("."))


def tools_off(text):
    """`text` (a config.toml, possibly empty) with every key of OFF = false; ValueError if it sets one otherwise."""
    lines, table, headers = [], "", {}
    for line in text.splitlines():
        header, assign = HEADER.match(line), ASSIGN.match(line)  # no walrus: runner hosts may have an old python3
        if ARRAY.match(line):
            table = "[[]]"  # an array of tables: none of the keys lives in one
        elif header:
            table = path(header.group(1))
            headers[table] = len(lines)
        elif assign and table != "[[]]":
            key = path(f"{table}.{assign.group(1)}" if table else assign.group(1))
            value = assign.group(2).split("#")[0].strip()
            if key in OFF:
                if value != "false":
                    raise ValueError(f"the config sets {key} = {value}; an official run sets it to false")
                continue  # written below, once
            if any(k.startswith(key + ".") for k in OFF):  # an inline table: features = { ... }
                raise ValueError(f"the config writes {key} as an inline table; write its keys one per line")
        lines.append(line)
    top = []
    inside = {}  # line index of a table header -> the keys to write under it
    for key in OFF:
        parts = key.split(".")
        for n in range(len(parts) - 1, 0, -1):  # the config's deepest table this key belongs to
            if ".".join(parts[:n]) in headers:
                inside.setdefault(headers[".".join(parts[:n])], []).append(".".join(parts[n:]) + " = false")
                break
        else:
            top.append(f"{key} = false")
    out = ["# scripts/codex_tools_off.py: no tool that runs at the model provider (PROTOCOL D11)", *top]
    for i, line in enumerate(lines):
        out.append(line)
        out.extend(inside.get(i, []))
    result = "\n".join(out) + "\n"
    if tomllib is not None:
        parsed = tomllib.loads(result)  # raises on a layout the rules above did not foresee
        for key in OFF:
            node = parsed
            for part in key.split("."):
                node = node.get(part) if isinstance(node, dict) else None
            if node is not False:
                raise ValueError(f"{key} is not false in the result")
    return result


if __name__ == "__main__":
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1].startswith("-")):
        sys.exit(__doc__)
    try:
        sys.stdout.write(tools_off(open(sys.argv[1]).read() if len(sys.argv) == 2 else ""))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"codex_tools_off.py: {sys.argv[1] if len(sys.argv) == 2 else '(no config)'}: {exc}", file=sys.stderr)
        sys.exit(2)
