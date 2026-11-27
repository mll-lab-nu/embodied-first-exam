#!/usr/bin/env python3
"""Advisory contract check of the benchmarks' own eai-standard/3.0 servers against docs/protocol/eai-standard-3.0.openapi.yaml.

check-openapi-contract.py runs the shared reference layers (rcb_service.py, rcb_limited.py, rcb_realtime.py) on toy
simulators; the benchmark servers that serve the wire themselves (their own HTTP layer, no shared layer imported)
need their simulator and are not started there. This check reads their source instead (static, no simulator, no
docker): every `embodied_first_exam/benchmarks/*/sim/server*.py` whose PROTOCOL is "eai-standard/3.0" and that imports
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

    python3 ci_checks/check-own-servers.py [--repo DIR] [server.py ...]
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


def is_dict_call(node) -> bool:
    """`dict(...)`: a dict built by a call (keywords, a mapping, `**spreads`)."""
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict"


def is_dictish(node) -> bool:
    return isinstance(node, ast.Dict) or is_dict_call(node)


def own_keys(node) -> set:
    """The string keys a dict expression names itself (a literal's keys, a dict() call's keywords): no spreads."""
    if isinstance(node, ast.Dict):
        return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    if is_dict_call(node):
        return {kw.arg for kw in node.keywords if kw.arg is not None}
    return set()


class Module:
    """One server's source: its module-level functions and the keys their returned dicts always carry. A dict is a
    literal, a dict(...) call, or a local name assigned one, with the keys its function later adds to that name
    (name["key"] = ..., name.update(...), name.setdefault("key", ...))."""

    def __init__(self, src: str, name: str):
        self.name, self.tree = name, ast.parse(src, filename=name)
        self.funcs = {n.name: n for n in self.tree.body if isinstance(n, ast.FunctionDef)}
        self._keys: dict[str, set | None] = {}

    def module_assigns(self, name: str) -> list:
        """The values a module-level name is assigned (Assign and AnnAssign)."""
        out = []
        for n in self.tree.body:
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
                out.append(n.value)
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == name and n.value:
                out.append(n.value)
        return out

    def func_keys(self, fname: str) -> set | None:
        """The keys every `return ...` of a module-level function carries (None: not a function of the module, or
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
            k = self.dict_keys(v, f)
            if k is None:
                return None
            sets.append(k)
        out = set.intersection(*sets) if sets else None
        self._keys[fname] = out
        return out

    def added(self, fn, name: str | None) -> list:
        """(key, value) pairs a function adds to its local dict `name` after building it: name["key"] = value,
        name.update({...} / key=value / **f()), name.setdefault("key", value); key None: a mapping of keys not named
        here (the value is that mapping's expression)."""
        out = []
        if fn is None or name is None:
            return out
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == name
                            and isinstance(t.slice, ast.Constant) and isinstance(t.slice.value, str)):
                        out.append((t.slice.value, n.value))
            elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                  and n.func.value.id == name):
                if n.func.attr == "setdefault" and n.args and isinstance(n.args[0], ast.Constant) \
                        and isinstance(n.args[0].value, str):
                    out.append((n.args[0].value, n.args[1] if len(n.args) > 1 else None))
                elif n.func.attr == "update":
                    out += [(None, a) for a in n.args] + [(kw.arg, kw.value) for kw in n.keywords]
        return out

    def added_keys(self, fn, name: str | None) -> set:
        out = set()
        for k, v in self.added(fn, name):
            out |= {k} if k is not None else self.spread_keys(v, fn)
        return out

    def name_keys(self, fn, name: str) -> set | None:
        """The keys a local name of a function always holds: what every assignment of it builds, plus what is added."""
        vals = enclosing_assigns(fn, name)
        if not vals:
            return None
        sets = [self.dict_keys(v, None) for v in vals]
        if any(x is None for x in sets):
            return None
        return set.intersection(*sets) | self.added_keys(fn, name)

    def spread_keys(self, v, fn) -> set:
        """The keys of a `**spread` (or of a dict() / update() positional mapping): a dict, a module function's
        return, a local dict name; nothing for anything else (a conditional spread counts with none)."""
        if is_dictish(v):
            return self.dict_keys(v, fn) or set()
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Name):
            return self.func_keys(v.func.id) or set()
        if isinstance(v, ast.Name) and fn is not None:
            return self.name_keys(fn, v.id) or set()
        return set()

    def dict_keys(self, node, fn=None) -> set | None:
        """The string keys a dict expression always has: a literal's own keys or a dict() call's keywords, plus the
        keys of each spread; a local name of `fn` with its own and its added keys; None for anything that is not a
        dict."""
        if isinstance(node, ast.Name) and fn is not None:
            return self.name_keys(fn, node.id)
        if is_dict_call(node):
            out = own_keys(node)
            for a in node.args:
                out |= self.spread_keys(a, fn)
            for kw in node.keywords:
                if kw.arg is None:
                    out |= self.spread_keys(kw.value, fn)
            return out
        if not isinstance(node, ast.Dict):
            return None
        out = own_keys(node)
        for k, v in zip(node.keys, node.values):
            if k is None:                                # **spread
                out |= self.spread_keys(v, fn)
        return out

    def dict_value(self, node, key: str, fn=None, name: str | None = None):
        """The value expression of `key` in a dict expression (its spreads' functions' returns too; with `name`, what
        `fn` adds to that local name first), or None."""
        for k, v in self.added(fn, name):
            if k == key:
                return v
        if is_dict_call(node):
            for kw in node.keywords:
                if kw.arg == key:
                    return kw.value
            spreads = list(node.args) + [kw.value for kw in node.keywords if kw.arg is None]
        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == key:
                    return v
            spreads = [v for k, v in zip(node.keys, node.values) if k is None]
        else:
            return None
        for v in spreads:
            if is_dictish(v):
                got = self.dict_value(v, key)
                if got is not None:
                    return got
            elif isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in self.funcs:
                for r in ast.walk(self.funcs[v.func.id]):
                    if isinstance(r, ast.Return) and is_dictish(r.value):
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


def maybe_null(v, m: Module | None = None, depth: int = 0) -> bool:
    """None, `X or None`, a conditional with a None branch, or a module-level name assigned one of those."""
    if isinstance(v, ast.Name) and m is not None and depth < 8:
        return any(maybe_null(x, m, depth + 1) for x in m.module_assigns(v.id))
    return (isinstance(v, ast.Constant) and v.value is None) or (
        isinstance(v, ast.BoolOp) and isinstance(v.op, ast.Or) and maybe_null(v.values[-1], m, depth)) or (
        isinstance(v, ast.IfExp) and (maybe_null(v.body, m, depth) or maybe_null(v.orelse, m, depth)))


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
    parent, named = {}, {}
    for f in m.funcs.values():
        for n in ast.walk(f):
            parent[id(n)] = f
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                named[id(n.value)] = n.targets[0].id     # a local dict built here, then added to by name
    n_ans = 0
    for n in ast.walk(m.tree):
        if not is_dictish(n):
            continue
        fn, name = parent.get(id(n)), named.get(id(n))
        own = own_keys(n) | {k for k, _ in m.added(fn, name) if k is not None}
        kind = next((k for k in ANSWER_IDS if k in own), None)
        if kind is None:
            continue
        n_ans += 1
        keys = (m.dict_keys(n, fn) or set()) | m.added_keys(fn, name)
        miss = [k for k in counters if k not in keys]
        if miss:
            out.append(f"{m.name}:{n.lineno}: an answer meta ({kind}) lacks {miss} (OpenAPI Counters)")
        if kind == "chunk_id":
            miss = [k for k in SUBMIT_KEYS if k not in keys]
            if miss:
                out.append(f"{m.name}:{n.lineno}: a /submit answer lacks {miss} (OpenAPI SubmitMeta)")
            v = m.dict_value(n, "clipped", fn, name)
            if v is not None and not listy(v, fn):
                out.append(f"{m.name}:{n.lineno}: a /submit answer's clipped is not a list (OpenAPI SubmitMeta: an "
                           f"array of {{row, index, reason}}; the count is n_clipped): {ast.unparse(v)[:60]}")
    if not n_ans:
        out.append(f"{m.name}: no answer meta found (no dict with {'/'.join(ANSWER_IDS)})")
    # /spec
    spec = next((n.value for n in m.tree.body if isinstance(n, ast.Assign) and is_dictish(n.value)
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
            elif is_dictish(a):
                keys |= m.dict_keys(a) or set()
                vals.append(m.dict_value(a, "max_control_steps"))
    miss = [k for k in spec_req if k not in keys]
    if miss:
        out.append(f"{m.name}: SPEC (/spec) lacks {miss} (OpenAPI Spec)")
    for v in vals:
        if v is not None and maybe_null(v, m):
            out.append(f"{m.name}:{v.lineno}: /spec max_control_steps may be null ({ast.unparse(v)[:60]}): the "
                       "OpenAPI Spec has it an integer; leave it out when there is no cap")
    return out


GOOD = '''
PROTOCOL = "eai-standard/3.0"
SPEC = {"protocol": PROTOCOL, "action_types": {}, "max_control_steps": 100}
SPEC["cameras"] = {}
def meta_common():
    return {"calls": 0, "control_steps": 0, "done": False, "reason": None, **({"x": 1} if 1 else {})}
def submit():
    clipped = []
    return {**meta_common(), "chunk_id": 1, "control_steps_chunk": 3, "clipped": clipped[:200], "n_clipped": 0}, []
def observe():
    return {**meta_common(), "obs_id": 2}, []
def status():
    st = {}
    st.update(meta_common())
    st["elapsed_s"] = 1.0
    return st
def reset():
    out = dict(**meta_common(), reset_id=3)
    return out, []
def submit_hold():
    m = dict(meta_common())
    m["chunk_id"] = 4
    m.update({"control_steps_chunk": 0}, n_clipped=0)
    m["clipped"] = sorted([])
    return m, []
CAP = 100
SPEC["max_control_steps"] = CAP
'''
BAD = '''
PROTOCOL = "eai-standard/3.0"
SPEC = {"protocol": PROTOCOL, "action_types": {}, "max_control_steps": CAP or None}
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
              "'n_clipped']", "clipped is not a list", "lacks ['cameras']", "max_control_steps may be null")
OK_HEAD = '''
PROTOCOL = "eai-standard/3.0"
def meta_common():
    return {"calls": 0, "control_steps": 0, "done": False, "reason": None}
def status():
    return {**meta_common(), "elapsed_s": 1.0}
'''
# each a source with one kind of fault only (the rest complete), and what must be flagged in it
BAD_MORE = [
    ("answers built with dict(...)", OK_HEAD + '''SPEC = dict(protocol=PROTOCOL, action_types={}, cameras={})
def submit():
    return dict(**meta_common(), chunk_id=1, clipped=[], n_clipped=0), []
def observe():
    return dict(obs_id=2, calls=0, done=False, reason=None), []
''', ("a /submit answer lacks ['control_steps_chunk']", "an answer meta (obs_id) lacks ['control_steps']")),
    ("answers built by subscript assignment", OK_HEAD + '''SPEC = {"protocol": PROTOCOL, "action_types": {}, "cameras": {}}
def submit():
    meta = {**meta_common()}
    meta["chunk_id"] = 1
    meta["control_steps_chunk"] = 3
    meta["n_clipped"] = 0
    meta["clipped"] = 3
    return meta, []
def observe():
    m = {}
    m["obs_id"] = 2
    m.update(calls=0, done=False)
    return m, []
''', ("clipped is not a list", "an answer meta (obs_id) lacks ['control_steps', 'reason']")),
    ("max_control_steps null through a variable", OK_HEAD + '''LIM = CAP or None
SPEC = {"protocol": PROTOCOL, "action_types": {}, "cameras": {}, "max_control_steps": LIM}
def submit():
    return {**meta_common(), "chunk_id": 1, "control_steps_chunk": 3, "clipped": [], "n_clipped": 0}, []
''', ("max_control_steps may be null (LIM)",)),
]


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
    for what, src, wants in BAD_MORE:
        got = check_module(Module(src, "<bad>"), counters, spec_req)
        for want in wants:
            if not any(want in g for g in got):
                bad.append(f"a rule went blind ({what}): not flagged for {want!r} (got {got})")
        extra = [g for g in got if not any(w in g for w in wants)]
        if extra:
            bad.append(f"the built-in source with {what} only is flagged for more: {extra}")
    return bad


def discover(repo: pathlib.Path) -> list[pathlib.Path]:
    out = []
    for p in sorted((repo / "embodied_first_exam/benchmarks").glob("*/sim/server*.py")):
        src = p.read_text(errors="replace")
        if '"eai-standard/3.0"' not in src:
            continue
        try:
            tree = ast.parse(src, filename=str(p))
        except SyntaxError:
            out.append(p)                                # reported as unparsable below
            continue
        if protocol_of(tree) == "eai-standard/3.0" and not is_shared_layer_import(tree):
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
        print(f"FAIL check-own-servers.py: cannot read the OpenAPI document: {exc}")
        return 2
    broken = selftest(counters, spec_req)
    if broken:
        for b in broken:
            print(f"FAIL check-own-servers.py: {b}")
        return 2
    servers = [pathlib.Path(s) for s in a.servers] or discover(repo)
    if not servers:
        print("FAIL check-own-servers.py: no benchmark-own eai-standard/3.0 server found (the discovery went blind)")
        return 2
    findings = []
    for p in servers:
        rel = str(p.resolve().relative_to(repo)) if p.resolve().is_relative_to(repo) else str(p)
        try:
            m = Module(p.read_text(), rel)
        except (OSError, SyntaxError) as exc:
            print(f"FAIL check-own-servers.py: {rel}: {exc}")
            return 2
        findings += check_module(m, counters, spec_req)
    for f in findings:
        print(f"FAIL {f}")
    names = ", ".join(re.sub(r"^embodied_first_exam/benchmarks/", "", str(p.resolve().relative_to(repo)))
                      for p in servers if p.resolve().is_relative_to(repo))
    if findings:
        print(f"check-own-servers.py: {len(findings)} finding(s) in {len(servers)} server(s) ({names}) -- advisory")
        return 3
    print(f"ok check-own-servers.py: {len(servers)} benchmark-own server(s) ({names}) carry the OpenAPI's keys")
    return 0


if __name__ == "__main__":
    sys.exit(main())
