#!/usr/bin/env python3
"""Make sure no saved rollout contains a model-API key or a login token (a runner-side tool: scripts/run_agent_batch.sh).

  scan_secrets.py <dir> [--env-file ../.env ...] [--var NAME ...] [--codex-auth ~/.codex/auth.json ...] [--redact]

Loads the secrets INSIDE this process and never prints them: the named variables (default: the keys Harbor's native
agents read, VARS below) from the .env files (default: the repo's ../.env) or, where a file does not set one, from this
process's environment, and, with --codex-auth, the tokens of a Codex ChatGPT login (auth.json). Values shorter than 16
characters are not treated as secrets. It reports only which files contain one (and how many times). With --redact every
occurrence is replaced with [REDACTED-<NAME>] in place. Binary files (videos, npz) are scanned too, as bytes; .gz and .xz
files (the usage gateway's raw logs) decompressed. A damaged .gz / .xz (truncated, corrupt) is scanned as far as it
decompresses, and as bytes; it is reported as DAMAGED and counted in the last line, and --redact rewrites it with only
its readable part."""
import argparse, gzip, json, lzma, os, pathlib, re, sys, zlib

MAGIC = {".gz": b"\x1f\x8b", ".xz": b"\xfd7zXZ\x00"}
DECOMPRESSOR = {".gz": lambda: zlib.decompressobj(zlib.MAX_WBITS | 16), ".xz": lzma.LZMADecompressor}

VARS = ["OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
        "AZURE_API_KEY", "AZURE_OPENAI_API_KEY"]


def decompress(data: bytes, suffix: str) -> tuple[bytes, bool]:
    """(what decompresses, whether all of it did): every stream of a multi-stream file (the gateway's live raw log is
    one gzip stream per request), fed in 64 kB pieces; after a damaged stream it resumes at the next stream header."""
    out, rest, whole = [], data, True
    while rest:
        d, i = DECOMPRESSOR[suffix](), 0
        try:
            while not d.eof and i < len(rest):
                out.append(d.decompress(rest[i:i + (1 << 16)]))
                i += 1 << 16
        except (zlib.error, lzma.LZMAError):
            pass
        if not d.eof:
            whole = False
            j = rest.find(MAGIC[suffix], 1)
            if j < 0:
                break
            rest = rest[j:]
            continue
        rest = (d.unused_data + rest[i:]).lstrip(b"\0")      # the next stream (zero padding between streams allowed)
    return b"".join(out), whole


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
        else:
            v = re.split(r"\s+#", v, maxsplit=1)[0].strip()   # as dotenv (Harbor, efe.py) reads it: an unquoted value ends at " #"
        out[k] = v
    return out


ap = argparse.ArgumentParser()
ap.add_argument("dir")
ap.add_argument("--env-file", action="append", help="repeatable (default: the clone's .env and .env.local, which Harbor loads, and <repo>/../.env)")
ap.add_argument("--var", action="append", help="repeatable (default: VARS)")
ap.add_argument("--codex-auth", action="append", default=[], help="a Codex auth.json whose login tokens are secrets too")
ap.add_argument("--redact", action="store_true")
a = ap.parse_args()
REPO = pathlib.Path(__file__).resolve().parents[1]
sources = [load_env(f) for f in a.env_file or [str(REPO.parent / ".env"), str(REPO / ".env"), str(REPO / ".env.local")]
           if pathlib.Path(f).is_file()] + [dict(os.environ)]
secrets = {}
for n in a.var or VARS:   # every value a key has in any source (the env files and this environment): any of them may be in use
    vals = list(dict.fromkeys(s[n] for s in sources if len(s.get(n) or "") >= 16))
    secrets.update({n if i == 0 else f"{n}#{i + 1}": v.encode() for i, v in enumerate(vals)})
for f in a.codex_auth:
    d = json.loads(pathlib.Path(f).expanduser().read_text())
    for k, v in (d.get("tokens") or {}).items():
        if k != "account_id" and isinstance(v, str) and len(v) > 20:
            secrets[f"CODEX_{k.upper()}"] = v.encode()
    if d.get("OPENAI_API_KEY"):
        secrets["CODEX_OPENAI_API_KEY"] = d["OPENAI_API_KEY"].encode()
if not secrets:
    sys.exit("no secret loaded (check --env-file / --var / --codex-auth); nothing to scan for")
hits = scanned = damaged = 0
for p in pathlib.Path(a.dir).rglob("*"):
    if not p.is_file() or p.is_symlink():
        continue
    scanned += 1
    try:
        raw = p.read_bytes()
    except OSError:
        continue
    codec, data, whole = None, raw, True
    if p.suffix in MAGIC and raw.startswith(MAGIC[p.suffix]):     # otherwise not really compressed: scan it as bytes
        codec = p.suffix
        data, whole = decompress(raw, codec)
        if not whole:
            damaged += 1
            print(f"DAMAGED {codec} (scanned the {len(data)} bytes that decompress, and the file as bytes): {p}")
    found = {n: data.count(s) + (0 if whole else raw.count(s)) for n, s in secrets.items()}
    found = {n: c for n, c in found.items() if c}
    if found:
        hits += 1
        print(f"FOUND {', '.join(f'{n} x{c}' for n, c in found.items())}: {p}")
        if a.redact:
            for n in found:
                data = data.replace(secrets[n], f"[REDACTED-{n}]".encode())
            p.write_bytes(lzma.compress(data, preset=9) if codec == ".xz" else gzip.compress(data) if codec else data)
            print("  redacted" + ("" if whole else " (only the readable part is kept)"))
print(f"scanned {scanned} files under {a.dir} for {len(secrets)} secret(s) ({', '.join(sorted(secrets))}): "
      f"{hits} contain one" + (f", {damaged} damaged compressed file(s)" if damaged else ""))
