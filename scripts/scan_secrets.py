#!/usr/bin/env python3
"""Make sure no saved rollout contains a model-API key or a Codex login token.

  scan_secrets.py <dir> [--env-file ../.env ...] [--var OPENROUTER_API_KEY ...] [--codex-auth ~/.codex/auth.json ...] [--redact]

Loads the secrets INSIDE this process and never prints them: the named variables from the .env files (default: the
repo's ../.env and OPENROUTER_API_KEY) and, with --codex-auth, the tokens of a Codex ChatGPT login (auth.json). It
reports only which files contain one (and how many times). With --redact every occurrence is replaced with
[REDACTED-<NAME>] in place. Binary files (videos, npz) are scanned too, as bytes."""
import argparse, json, pathlib, sys


def load_env(path: str) -> dict:
    out = {}
    for line in pathlib.Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip(); v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k] = v
    return out


ap = argparse.ArgumentParser()
ap.add_argument("dir")
ap.add_argument("--env-file", action="append", help="repeatable (default: <repo>/../.env)")
ap.add_argument("--var", action="append", help="repeatable (default: OPENROUTER_API_KEY)")
ap.add_argument("--codex-auth", action="append", default=[], help="a Codex auth.json whose login tokens are secrets too")
ap.add_argument("--redact", action="store_true")
a = ap.parse_args()
env = {}
for f in a.env_file or [str(pathlib.Path(__file__).resolve().parents[2] / ".env")]:
    if pathlib.Path(f).is_file():
        env.update(load_env(f))
secrets = {n: env[n].encode() for n in (a.var or ["OPENROUTER_API_KEY"]) if env.get(n)}
for f in a.codex_auth:
    d = json.loads(pathlib.Path(f).expanduser().read_text())
    for k, v in (d.get("tokens") or {}).items():
        if k != "account_id" and isinstance(v, str) and len(v) > 20:
            secrets[f"CODEX_{k.upper()}"] = v.encode()
    if d.get("OPENAI_API_KEY"):
        secrets["CODEX_OPENAI_API_KEY"] = d["OPENAI_API_KEY"].encode()
if not secrets:
    sys.exit("no secret loaded (check --env-file / --var / --codex-auth); nothing to scan for")
hits = scanned = 0
for p in pathlib.Path(a.dir).rglob("*"):
    if not p.is_file() or p.is_symlink():
        continue
    scanned += 1
    try:
        data = p.read_bytes()
    except OSError:
        continue
    found = {n: data.count(s) for n, s in secrets.items() if s in data}
    if found:
        hits += 1
        print(f"FOUND {', '.join(f'{n} x{c}' for n, c in found.items())}: {p}")
        if a.redact:
            for n in found:
                data = data.replace(secrets[n], f"[REDACTED-{n}]".encode())
            p.write_bytes(data)
            print("  redacted")
print(f"scanned {scanned} files under {a.dir} for {len(secrets)} secret(s) ({', '.join(sorted(secrets))}): {hits} contain one")
