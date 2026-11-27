#!/usr/bin/env python3
"""Advisory contract check of the benchmarks' own eai-standard/2.1 servers against docs/protocol/eai-standard-3.0.openapi.yaml.

check-openapi-contract.py runs the shared reference layers (rcb_service.py, rcb_limited.py, rcb_realtime.py) on toy
simulators; the benchmark servers that serve the 2.1 wire themselves (their own HTTP layer, no shared layer imported)
need their simulator and are not started there. This check reads their source instead (static, no simulator, no
docker): every `embodied_first_exam/benchmarks/*/sim/server*.py` whose PROTOCOL is "eai-standard/2.1" and that imports
neither rcb_service nor rcb_limited. In each one, from the dict literals it builds (a `**f()` spread of a module-level
function counts with the keys that function always returns; a conditional spread counts with none):

  - /status (the module's status() or _status()) and every answer meta (a dict with chunk_id, obs_id or reset_id, its
    meta_common() spread included) carry the keys components/schemas/Counters requires (calls, control_steps, done,
    reason);
  - every /submit answer (a dict with chunk_id) carries control_steps_chunk, clipped as a list (SubmitMeta: an array of
    {row, index, reason}) and n_clipped;
  - /spec (the module-level SPEC dict, with its later SPEC[...] = ... and SPEC.update / setdefault) carries what
    components/schemas/Spec requires, and max_control_steps, where it states one, is an integer: never `X or None`
    or None (Spec: max_control_steps is an integer; absent when there is no cap).

Before the real servers, the checker runs on a built-in good and bad source (each rule must pass the one and flag the
other), so a rule that went blind fails here. Exit 0: clean; 3: findings (advisory, ci_checks/run_all.sh); 2: the
check itself could not run (no OpenAPI document, a source that does not parse).

    python3 ci_checks/check-v21-servers.py [--repo DIR] [server.py ...]
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
SUBMIT_KEYS = ("control_steps_chunk", "clipped", "n_clipped")    # SubmitMeta: what a standard /submit answer reports
ANSWER_IDS = ("chunk_id", "obs_id", "reset_id")                  # the keys that make a dict an answer's meta
LIST_CALLS = {"list", "sorted"}


def required(doc: dict, name: str) -> list[str]:
    """The keys components/schemas/<name> requires (its own and its allOf parts')."""
    s = doc["components"]["schemas"][name]
    out = list(s.get("required") or [])
    for part in s.get("allOf") or []:
        if isinstance(part, dict) and "$ref" not in part:
            out += [k for k in part.get("required") or [] if "if" not in part]
    return out


def is_shared_layer_import(tree: ast.Module) -> bool:
    for n in ast.walk(tree):
        if isinstance(n, ast.Import) and any(a.name in ("rcb_service", "rcb_limited") for a in n.names):
            return True
        if isinstance(n, ast.ImportFrom) and n.module in ("rcb_service", "rcb_limited"):
            return True
    return False


def protocol_of(tree: ast.Module) -> str | None:
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PROTOCOL" for t in n.targets):
            if isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
                return n.value.value
    return None


class Module:
    """One server's source: its module-level functions and the keys their returned dict literals always carry."""

    def __init__(self, src: str, name: str):
        self.name, self.tree = name, ast.parse(src, filename=name)
        self.funcs = {n.name: n for n in self.tree.body if isinstance(n, ast.FunctionDef)}
        self._keys: dict[str, set | None] = {}

    def func_keys(self, fname: str) -> set | None:
        """The keys every `return {...}` of a module-level function carries (None: not a function of the module, or
        a return that is no dict)."""
        if fname in self._keys:
            return self._keys[fname]
        self._keys[fname] = None                         # recursion guard
        f = self.funcs.get(fname)
        if f is None:
            return None
        rets = [r.value for r in ast.walk(f) if isinstance(r, ast.Return) and r.value is not None]
        sets = []
        for v in rets:
            if isinstance(v, ast.Tuple) and v.elts:      # (meta, parts): the meta
                v = v.elts[0]
            k = self.dict_keys(v)
            if k is None:
                return None
            sets.append(k)
        out = set.intersection(*sets) if sets else None
        self._keys[fname] = out
        return out

    def dict_keys(self, node) -> set | None:
        """The string keys a dict expression always has: a literal's own keys, plus the keys of each `**f()` spread
        of a module-level function; None for anything that is not a dict literal."""
        if not isinstance(node, ast.Dict):
            return None
        out = set()
        for k, v in zip(node.keys, node.values):
            if k is None:                                # **spread
                if isinstance(v, ast.Call) and isinstance(v.func, ast.Name):
                    out |= self.func_keys(v.func.id) or set()
                elif isinstance(v, ast.Dict):
                    out |= self.dict_keys(v) or set()
            elif isinstance(k, ast.Constant) and isinstance(k.value, str):
                out.add(k.value)
        return out

    def dict_value(self, node: ast.Dict, key: str):
        """The value expression of `key` in a dict literal (its spreads' functions' returns too), or None."""
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and k.value == key:
                return v
            if k is None and isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in self.funcs:
                for r in ast.walk(self.funcs[v.func.id]):
                    if isinstance(r, ast.Return) and isinstance(r.value, ast.Dict):
                        got = self.dict_value(r.value, key)
                        if got is not None:
                            return got
        return None


def enclosing_assigns(fn: ast.AST | None, name: str) -> list:
    if fn is None:
        return []
    return [n.value for n in ast.walk(fn) if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]


def listy(v, fn) -> bool:
    """A value that is a list: a list display or comprehension, a slice of one, list() / sorted(), or a local name
    assigned one of those."""
    if isinstance(v, (ast.List, ast.ListComp)):
        return True
    if isinstance(v, ast.Subscript) and isinstance(v.slice, ast.Slice):
        return listy(v.value, fn) or isinstance(v.value, ast.Name)
    if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in LIST_CALLS:
        return True
    if isinstance(v, ast.Name):
        vals = enclosing_assigns(fn, v.id)
        return bool(vals) and all(listy(x, None) for x in vals)
    return False


def maybe_null(v) -> bool:
    return (isinstance(v, ast.Constant) and v.value is None) or (
        isinstance(v, ast.BoolOp) and isinstance(v.op, ast.Or) and maybe_null(v.values[-1])) or (
        isinstance(v, ast.IfExp) and (maybe_null(v.body) or maybe_null(v.orelse)))


def check_module(m: Module, counters: list[str], spec_req: list[str]) -> list[str]:
    out = []
    # /status
    st = next((m.funcs[n] for n in ("status", "_status") if n in m.funcs), None)
    if st is None:
        out.append(f"{m.name}: no module-level status() / _status(): /status not found")
    else:
        keys = m.func_keys(st.name)
        miss = [k for k in counters if keys is None or k not in keys]
        if miss:
            out.append(f"{m.name}: {st.name}() (/status, line {st.lineno}) lacks {miss} (OpenAPI Counters)")
    # answer metas
    parent = {}
    for f in m.funcs.values():
        for n in ast.walk(f):
            parent[id(n)] = f
    n_ans = 0
    for n in ast.walk(m.tree):
        if not isinstance(n, ast.Dict):
            continue
        own = {k.value for k in n.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        kind = next((k for k in ANSWER_IDS if k in own), None)
        if kind is None:
            continue
        n_ans += 1
        keys = m.dict_keys(n) or set()
        miss = [k for k in counters if k not in keys]
        if miss:
            out.append(f"{m.name}:{n.lineno}: an answer meta ({kind}) lacks {miss} (OpenAPI Counters)")
        if kind == "chunk_id":
            miss = [k for k in SUBMIT_KEYS if k not in keys]
            if miss:
                out.append(f"{m.name}:{n.lineno}: a /submit answer lacks {miss} (OpenAPI SubmitMeta)")
            v = m.dict_value(n, "clipped")
            if v is not None and not listy(v, parent.get(id(n))):
                out.append(f"{m.name}:{n.lineno}: a /submit answer's clipped is not a list (OpenAPI SubmitMeta: an "
                           f"array of {{row, index, reason}}; the count is n_clipped): {ast.unparse(v)[:60]}")
    if not n_ans:
        out.append(f"{m.name}: no answer meta found (no dict with {'/'.join(ANSWER_IDS)})")
    # /spec
    spec = next((n.value for n in m.tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict)
                 and any(isinstance(t, ast.Name) and t.id == "SPEC" for t in n.targets)), None)
    if spec is None:
        out.append(f"{m.name}: no module-level SPEC dict: /spec not found")
        return out
    keys, vals = set(m.dict_keys(spec) or ()), [m.dict_value(spec, "max_control_steps")]
    for n in ast.walk(m.tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == "SPEC"
                        and isinstance(t.slice, ast.Constant) and isinstance(t.slice.value, str)):
                    keys.add(t.slice.value)
                    if t.slice.value == "max_control_steps":
                        vals.append(n.value)
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
              and n.func.value.id == "SPEC" and n.func.attr in ("update", "setdefault") and n.args):
            a = n.args[0]
            if n.func.attr == "setdefault" and isinstance(a, ast.Constant) and isinstance(a.value, str):
                keys.add(a.value)
                if a.value == "max_control_steps" and len(n.args) > 1:
                    vals.append(n.args[1])
            elif isinstance(a, ast.Dict):
                keys |= m.dict_keys(a) or set()
                vals.append(m.dict_value(a, "max_control_steps"))
    miss = [k for k in spec_req if k not in keys]
    if miss:
        out.append(f"{m.name}: SPEC (/spec) lacks {miss} (OpenAPI Spec)")
    for v in vals:
        if v is not None and maybe_null(v):
            out.append(f"{m.name}:{v.lineno}: /spec max_control_steps may be null ({ast.unparse(v)[:60]}): the "
                       "OpenAPI Spec has it an integer; leave it out when there is no cap")
    return out


GOOD = '''
PROTOCOL = "eai-standard/2.1"
SPEC = {"protocol": PROTOCOL, "action_types": {}, "cameras": {}, "max_control_steps": 100}
SPEC["standard"] = "eai-standard/3.0"
def meta_common():
    return {"calls": 0, "control_steps": 0, "done": False, "reason": None, **({"x": 1} if 1 else {})}
def submit():
    clipped = []
    return {**meta_common(), "chunk_id": 1, "control_steps_chunk": 3, "clipped": clipped[:200], "n_clipped": 0}, []
def observe():
    return {**meta_common(), "obs_id": 2}, []
def status():
    return {**meta_common(), "elapsed_s": 1.0}
'''
BAD = '''
PROTOCOL = "eai-standard/2.1"
SPEC = {"protocol": PROTOCOL, "action_types": {}, "cameras": {}, "max_control_steps": CAP or None}
def meta_common():
    return {"calls": 0, "done": False, "reason": None}
def submit():
    n_clip = 0
    return {**meta_common(), "chunk_id": 1, "clipped": n_clip}, []
def observe():
    return {**meta_common(), "obs_id": 2, "control_steps": 0}, []
def status():
    return {"calls": 0, "physics_steps": 0, "done": False, "reason": None}
'''
BAD_EXPECT = ("status() (/status", "answer meta (chunk_id) lacks ['control_steps']", "lacks ['control_steps_chunk', "
              "'n_clipped']", "clipped is not a list", "lacks ['standard']", "max_control_steps may be null")


def selftest(counters, spec_req) -> list[str]:
    bad = []
    got = check_module(Module(GOOD, "<good>"), counters, spec_req)
    if got:
        bad.append(f"the built-in good source is flagged: {got}")
    got = check_module(Module(BAD, "<bad>"), counters, spec_req)
    for want in BAD_EXPECT:
        if not any(want in g for g in got):
            bad.append(f"a rule went blind: the built-in bad source is not flagged for {want!r} (got {got})")
    if any("obs_id" in g for g in got):
        bad.append(f"the built-in bad source's observe meta (complete) is flagged: {got}")
    return bad


def discover(repo: pathlib.Path) -> list[pathlib.Path]:
    out = []
    for p in sorted((repo / "embodied_first_exam/benchmarks").glob("*/sim/server*.py")):
        src = p.read_text(errors="replace")
        if '"eai-standard/2.1"' not in src:
            continue
        try:
            tree = ast.parse(src, filename=str(p))
        except SyntaxError:
            out.append(p)                                # reported as unparsable below
            continue
        if protocol_of(tree) == "eai-standard/2.1" and not is_shared_layer_import(tree):
            out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=str(HERE.parent))
    ap.add_argument("servers", nargs="*", help="server sources (default: discovered, see above)")
    a = ap.parse_args()
    repo = pathlib.Path(a.repo).resolve()
    try:
        import yaml
        doc = yaml.safe_load((repo / "docs/protocol/eai-standard-3.0.openapi.yaml").read_text())
        counters, spec_req = required(doc, "Counters"), required(doc, "Spec")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL check-v21-servers.py: cannot read the OpenAPI document: {exc}")
        return 2
    broken = selftest(counters, spec_req)
    if broken:
        for b in broken:
            print(f"FAIL check-v21-servers.py: {b}")
        return 2
    servers = [pathlib.Path(s) for s in a.servers] or discover(repo)
    if not servers:
        print("FAIL check-v21-servers.py: no benchmark-own eai-standard/2.1 server found (the discovery went blind)")
        return 2
    findings = []
    for p in servers:
        rel = str(p.resolve().relative_to(repo)) if p.resolve().is_relative_to(repo) else str(p)
        try:
            m = Module(p.read_text(), rel)
        except (OSError, SyntaxError) as exc:
            print(f"FAIL check-v21-servers.py: {rel}: {exc}")
            return 2
        findings += check_module(m, counters, spec_req)
    for f in findings:
        print(f"FAIL {f}")
    names = ", ".join(re.sub(r"^embodied_first_exam/benchmarks/", "", str(p.resolve().relative_to(repo)))
                      for p in servers if p.resolve().is_relative_to(repo))
    if findings:
        print(f"check-v21-servers.py: {len(findings)} finding(s) in {len(servers)} server(s) ({names}) -- advisory")
        return 3
    print(f"ok check-v21-servers.py: {len(servers)} benchmark-own 2.1 server(s) ({names}) carry the OpenAPI's keys")
    return 0


if __name__ == "__main__":
    sys.exit(main())
