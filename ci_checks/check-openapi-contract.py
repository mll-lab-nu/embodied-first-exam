#!/usr/bin/env python3
"""Contract check of docs/protocol/eai-standard.openapi.yaml against the running reference services.

1. The document: openapi-spec-validator when it is installed (it is not a client pin; without it a structural check
   runs: openapi 3.1.0, info.version 3.0, the required paths, every $ref resolves, every operation has responses and
   an x-eai-mcp entry, every x-eai-rcb1-meta names a schema).
2. The services, each started as a plain process on a free localhost port (no docker), on the toy simulators the
   repository's own selftests use:
     sidecar     rcb_service.py (the sidecar layer, standard mode)  embodied_first_exam/standard/mcp/tests/toy_realtime.py --standard
     realtime    rcb_realtime.py over rcb_service.py (realtime mode)  embodied_first_exam/standard/mcp/tests/toy_realtime.py
     shared      rcb_limited.py (the shared layer)                    embodied_first_exam/standard/toy_server.py
     operations  operations/rcb_limited.py (toy_server.py staged next to it in the work directory)
   Every service is agent-ended (toy_server.py with rcb_agent_end.py staged next to it); sidecar and realtime run with a
   reset budget of 1. shared and operations check the layer's answers; shared-finish and operations-finish /finish,
   validated against FinishResponse, then the 409s after it. With a step
   limit (sidecar-limit, shared-limit, operations-limit: RCB_STEP_LIMIT): steps_left, the chunk cut at the limit (reason
   step_limit), then /submit and /finish 409 while /observe answers. A service that gave up (shared-gaveup:
   RCB_TOY_REFUSE): every endpoint 409 with gave_up. Every request is sent, and every answer is checked:
   its status code must be documented for that operation, its content type must be one the response lists, a JSON
   body must validate against the response's schema, and an RCB1 body is decoded and its header, part names and
   meta validated against Rcb1Header, Rcb1PartName and the schema the media type's x-eai-rcb1-meta names. Each valid
   request body is validated against the request schema; each deliberately invalid one must be rejected by it where
   the schema can express the rule (valid=None: a rule the schema cannot express, such as a service's own
   max_video_fps or rows x dt over max_chunk_s). Every layer must answer the same 400s (a bool or string where a
   number goes, interpolate cubic, a chunk over max_chunk_s, video_fps 0 / 0.5 / 99). Semantic assertions (a hold chunk's duration, observe never moving time, the
   realtime clock starting at the first /submit, /finish then 409) are checked on top.

    python3 ci_checks/check-openapi-contract.py [--repo DIR] [--spec FILE] [--targets sidecar,realtime,shared,...] [--work DIR]

Needs numpy, requests, PyYAML and jsonschema (>= 4.18). Exit 0: all passed; 1: a failure; 2: a missing dependency.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import pathlib
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True               # never leave __pycache__ in the repository we import rcb1 from

try:
    import numpy as np
    import requests
    import yaml
    import jsonschema
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012
except ImportError as exc:                    # pragma: no cover
    print(f"missing dependency: {exc}", file=sys.stderr)
    sys.exit(2)

HERE = pathlib.Path(__file__).resolve().parent
REQUIRED_PATHS = {"/spec": ["get"], "/observe": ["post"], "/submit": ["post"], "/finish": ["post"],
                  "/reset": ["post"], "/kinematics": ["post"]}
MCP_TOOLS = {"getSpec": "spec", "observe": "observe", "submit": "submit", "finish": "finish", "reset": "reset",
             "kinematics": "kinematics"}
HTTP_METHODS = ("get", "post", "put", "delete", "patch", "head", "options", "trace")

fails: list[str] = []
counts = {"requests": 0, "validated": 0}


def check(cond, what: str) -> bool:
    if not cond:
        fails.append(what)
        print(f"  FAIL {what}", flush=True)
    return bool(cond)


# ---------------------------------------------------------------------------------------------- the document
def resolve(doc: dict, ref: str):
    node = doc
    for bit in ref.lstrip("#/").split("/"):
        node = node[bit.replace("~1", "/").replace("~0", "~")]
    return node


def iter_refs(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str):
                yield path, v
            elif k == "x-eai-rcb1-meta" and isinstance(v, str):
                yield path, v
            else:
                yield from iter_refs(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from iter_refs(v, f"{path}/{i}")


def check_document(doc: dict, spec_path: pathlib.Path) -> None:
    print("document:", spec_path)
    try:
        from openapi_spec_validator import validate
        from openapi_spec_validator.readers import read_from_filename
    except ImportError:
        print("  openapi-spec-validator not installed: structural check only")
    else:
        try:
            spec_dict, base_uri = read_from_filename(str(spec_path))
            validate(spec_dict)
            print("  openapi-spec-validator: valid OpenAPI 3.1")
        except Exception as exc:  # noqa: BLE001
            check(False, f"openapi-spec-validator: {str(exc)[:500]}")
    check(doc.get("openapi") == "3.1.0", "openapi must be 3.1.0")
    check(str(doc.get("info", {}).get("version")) == "3.0", 'info.version must be "3.0"')
    paths = doc.get("paths", {})
    for p, methods in REQUIRED_PATHS.items():
        for m in methods:
            check(m in paths.get(p, {}), f"path {m.upper()} {p} missing")
    for p in ("/reset", "/kinematics"):
        op = paths.get(p, {}).get("post", {})
        check(op.get("x-eai-optional") is True and "optional" in op.get("tags", []), f"{p} must be marked optional")
    for p in ("/status", "/operations/{id}"):
        op = paths.get(p, {}).get("get", {})
        check(op.get("x-eai-client-internal") is True and op.get("x-eai-mcp", "x") is None,
              f"{p} must be marked client-internal with no MCP tool")
    for p in ("/start", "/ready", "/say", "/team"):
        check(all("match" in op.get("tags", []) for m, op in paths.get(p, {}).items() if m in HTTP_METHODS)
              and paths.get(p), f"match path {p} missing or not tagged match")
    for path, ref in iter_refs(doc):
        if ref.startswith("#/"):
            try:
                resolve(doc, ref)
            except (KeyError, TypeError):
                check(False, f"{path}: unresolved {ref}")
        else:
            check(False, f"{path}: external ref {ref}")
    n_ops = 0
    for p, item in paths.items():
        for m, op in item.items():
            if m not in HTTP_METHODS:
                continue
            n_ops += 1
            check(bool(op.get("responses")), f"{m.upper()} {p}: no responses")
            check("x-eai-mcp" in op, f"{m.upper()} {p}: no x-eai-mcp entry")
            check("x-eai-capability" in op, f"{m.upper()} {p}: no x-eai-capability")
            tool = MCP_TOOLS.get(op.get("operationId"))
            if tool:
                check((op.get("x-eai-mcp") or {}).get("tool") == tool, f"{op.get('operationId')}: x-eai-mcp tool != {tool}")
            if p in ("/observe", "/submit"):
                check(isinstance(op.get("x-eai-modes"), dict) and {"standard", "realtime"} <= set(op["x-eai-modes"]),
                      f"{m.upper()} {p}: x-eai-modes must describe standard and realtime")
    top = doc.get("x-eai-mcp", {}).get("tools", {})
    check(set(top) == set(MCP_TOOLS.values()), f"top-level x-eai-mcp.tools {sorted(top)}")
    print(f"  {len(paths)} paths, {n_ops} operations, {len(doc.get('components', {}).get('schemas', {}))} schemas")


# ---------------------------------------------------------------------------------------------- validation
def _absolute(node):
    """An inline schema with its "#/..." refs made absolute (urn:eai#/...), so they resolve against the document."""
    if isinstance(node, dict):
        return {k: ("urn:eai" + v if k == "$ref" and isinstance(v, str) and v.startswith("#/") else _absolute(v))
                for k, v in node.items()}
    if isinstance(node, list):
        return [_absolute(v) for v in node]
    return node


class Contract:
    def __init__(self, doc: dict, rcb1):
        self.doc, self.rcb1 = doc, rcb1
        self.registry = Registry().with_resource("urn:eai", Resource.from_contents(doc, default_specification=DRAFT202012))
        self.templates = [(p, re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", p) + "$")) for p in doc["paths"]]

    def errors(self, ref: str, instance) -> list[str]:
        v = jsonschema.Draft202012Validator({"$ref": "urn:eai" + ref}, registry=self.registry)
        return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message[:200]}" for e in v.iter_errors(instance)]

    def operation(self, method: str, path: str) -> dict | None:
        path = path.split("?")[0]
        for tpl, rx in self.templates:
            if rx.match(path):
                return self.doc["paths"][tpl].get(method.lower())
        return None

    @staticmethod
    def _ref_of(schema: dict) -> str | None:
        return schema.get("$ref") if isinstance(schema, dict) else None

    def request(self, method: str, path: str, ctype: str, meta, valid: bool, label: str) -> None:
        op = self.operation(method, path)
        if op is None or "requestBody" not in op or meta is None:
            return
        media = op["requestBody"]["content"].get(ctype)
        if not check(media is not None, f"{label}: request content type {ctype} not documented"):
            return
        ref = media.get("x-eai-rcb1-meta") if ctype == "application/x-rcb1" else self._ref_of(media.get("schema"))
        if ref is None:
            return
        errs = self.errors(ref, meta)
        if valid is None:                    # a rule the schema cannot express (the service's own limit)
            return
        if valid:
            check(not errs, f"{label}: a valid request is rejected by {ref}: {errs[:3]}")
        else:
            check(errs, f"{label}: an invalid request passes {ref}")

    def response(self, method: str, path: str, r: requests.Response, label: str):
        """Validate one answer against the document; returns (meta or JSON body, RCB1 parts or None)."""
        counts["requests"] += 1
        op = self.operation(method, path)
        if not check(op is not None, f"{label}: {method} {path} not in the document"):
            return None, None
        resp = op["responses"].get(str(r.status_code)) or op["responses"].get("default")
        if not check(resp is not None, f"{label}: status {r.status_code} not documented for {method} {path}: {r.text[:200]}"):
            return None, None
        if "$ref" in resp:
            resp = resolve(self.doc, resp["$ref"])
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip()
        content = resp.get("content") or {}
        if not content:
            return None, None
        if not check(ctype in content, f"{label}: content type {ctype!r} not documented for {r.status_code} ({sorted(content)})"):
            return None, None
        media = content[ctype]
        if ctype == "application/json":
            try:
                body = r.json()
            except ValueError:
                check(False, f"{label}: a body that is not JSON")
                return None, None
            ref = self._ref_of(media.get("schema"))
            errs = self.errors(ref, body) if ref else []
            if not ref:                                      # an inline schema: its refs point into the document
                v = jsonschema.Draft202012Validator(_absolute(media.get("schema", {})), registry=self.registry)
                errs = [e.message[:200] for e in v.iter_errors(body)]
            check(not errs, f"{label}: JSON body fails {ref or 'the inline schema'}: {errs[:4]}")
            counts["validated"] += 1
            return body, None
        if ctype == "application/x-rcb1":
            raw = r.content
            if not check(raw[:4] == b"RCB1", f"{label}: not an RCB1 frame"):
                return None, None
            (n,) = struct.unpack("<I", raw[4:8])
            header = json.loads(raw[8:8 + n].decode())
            check(not self.errors("#/components/schemas/Rcb1Header", header),
                  f"{label}: RCB1 header: {self.errors('#/components/schemas/Rcb1Header', header)[:3]}")
            total = 8 + n + sum(int(p["len"]) for p in header["parts"])
            check(total == len(raw), f"{label}: RCB1 length {len(raw)} != header + parts {total}")
            for p in header["parts"]:
                if p["kind"] == "array":
                    size = int(np.dtype(p["dtype"]).itemsize * int(np.prod(p["shape"], dtype=np.int64)))
                    check(size == p["len"], f"{label}: part {p['name']} len {p['len']} != dtype x shape {size}")
            meta, parts = self.rcb1.decode(raw)
            ref = media.get("x-eai-rcb1-meta")
            errs = self.errors(ref, meta) if ref else []
            check(not errs, f"{label}: RCB1 meta fails {ref}: {errs[:4]}")
            counts["validated"] += 1
            return meta, parts
        check(False, f"{label}: unexpected content type {ctype}")
        return None, None


# ---------------------------------------------------------------------------------------------- a service under test
def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Target:
    def __init__(self, name: str, argv: list[str], env: dict, work: pathlib.Path, contract: Contract, port: int):
        self.name, self.contract, self.port = name, contract, port
        self.base = f"http://127.0.0.1:{port}"
        self.log = open(work / f"{name}.log", "wb")
        self.proc = subprocess.Popen(argv, env=env, stdout=self.log, stderr=subprocess.STDOUT, cwd=str(work))
        print(f"{name}: pid {self.proc.pid} on :{port} ({' '.join(argv[1:3])})", flush=True)
        t0 = time.time()
        while time.time() - t0 < 120:
            if self.proc.poll() is not None:
                raise RuntimeError(f"{name}: the service exited ({self.proc.returncode}); see {work / (name + '.log')}")
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError(f"{name}: no listener on :{port} within 120 s")

    def stop(self) -> None:
        if self.proc.poll() is None:
            os.kill(self.proc.pid, signal.SIGTERM)          # the exact PID this script started
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                os.kill(self.proc.pid, signal.SIGKILL)
                self.proc.wait(10)
        self.log.close()

    # requests --------------------------------------------------------------------------------------------
    def bad(self, path: str, body: dict, label: str, valid=False) -> dict:
        """A request every layer refuses with a 400 before anything runs (the episode's control steps unchanged)."""
        _, st0, _ = self.get("/status", label=f"status before {label}")
        _, e, _ = self.post_json(path, body, expect=(400,), label=label, valid=valid)
        _, st1, _ = self.get("/status", label=f"status after {label}")
        check(st0.get("control_steps") == st1.get("control_steps"), f"{self.name} {label}: a refused request ran steps")
        return e

    def get(self, path: str, expect=(200,), label: str = ""):
        r = requests.get(self.base + path, timeout=60)
        return self._done("GET", path, r, expect, label)

    def post_json(self, path: str, body: dict, expect=(200,), label: str = "", valid: bool = True):
        self.contract.request("POST", path, "application/json", body, valid, f"{self.name} {label or path}")
        r = requests.post(self.base + path, json=body, timeout=120)
        return self._done("POST", path, r, expect, label)

    def post_rcb1(self, path: str, meta: dict, actions=None, expect=(200,), label: str = "", valid: bool = True):
        self.contract.request("POST", path, "application/x-rcb1", meta, valid, f"{self.name} {label or path}")
        rcb1 = self.contract.rcb1
        parts = [] if actions is None else [rcb1.array_part("actions", np.asarray(actions, np.float32))]
        r = requests.post(self.base + path, data=rcb1.encode(meta, parts),
                          headers={"Content-Type": "application/x-rcb1"}, timeout=120)
        return self._done("POST", path, r, expect, label)

    def post_bytes(self, path: str, data: bytes, expect=(200,), label: str = ""):
        """A POST whose body is sent as is, unvalidated (e.g. a body the service must ignore)."""
        r = requests.post(self.base + path, data=data, headers={"Content-Type": "application/json"}, timeout=120)
        return self._done("POST", path, r, expect, label)

    def post_raw_length(self, path: str, length: str, expect, label: str):
        """A POST whose Content-Length is `length` and whose body is never sent (the service must refuse it unread)."""
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        c.putrequest("POST", path)
        c.putheader("Content-Type", "application/json")
        c.putheader("Content-Length", length)
        c.endheaders()
        resp = c.getresponse()
        body = resp.read()
        c.close()
        r = requests.Response()
        r.status_code, r._content = resp.status, body
        r.headers = requests.structures.CaseInsensitiveDict(dict(resp.getheaders()))
        return self._done("POST", path, r, expect, label)

    def _done(self, method, path, r, expect, label):
        label = f"{self.name} {label or method + ' ' + path}"
        check(r.status_code in expect, f"{label}: status {r.status_code}, expected {list(expect)}: {r.text[:200]!r}")
        body, parts = self.contract.response(method, path, r, label)
        if body is None:                     # undocumented or invalid: still hand the scenario what came back
            try:
                body, parts = (self.contract.rcb1.decode(r.content) if r.content[:4] == b"RCB1" else (r.json(), None))
            except ValueError:
                body, parts = {}, None
        return r.status_code, (body if isinstance(body, dict) else {}), (parts or {})


# ---------------------------------------------------------------------------------------------- scenarios
def sidecar_layer(t: Target) -> None:
    """The sidecar layer (rcb_service.py), standard mode, agent-ended, reset budget 1."""
    J = "joint_position"
    _, spec, _ = t.get("/spec", label="spec")
    check(spec["protocol"] == "eai-standard/3.0" and not spec.get("timing", {}).get("realtime") and not spec.get("operations"),
          f"sidecar spec ids {spec.get('protocol')}")
    check(str(spec.get("success_signal", "")).startswith("hidden"), "sidecar spec success_signal hidden")
    rec = spec["timing"]["recorder"]
    check({"cameras", "fps", "buffer_s", "records", "depth"} <= set(rec) and rec["depth"] == [] and rec["fps"] == 10.0,
          f"sidecar spec timing.recorder {rec}")
    check("max_watch_s" not in spec, "sidecar spec still has max_watch_s (one cap: max_chunk_s)")
    t.get("/status", label="status")
    _, m, p = t.post_json("/observe", {}, label="observe now")
    check(m["last_s"] == 0 and m["frame_step"] == 0 and m["control_steps"] == 0, f"sidecar observe now meta {m}")
    check({"last/top", "frames/top", "proprio"} <= set(p), f"sidecar observe parts {sorted(p)}")
    _, e, _ = t.post_json("/observe", {"seconds": 1.0}, expect=(400,), label="observe seconds>0", valid=False)
    check("hold" in e.get("error", ""), "sidecar observe seconds>0 names the hold chunk")
    t.post_json("/observe", {"last_s": -1}, expect=(400,), label="observe last_s<0", valid=False)
    t.post_json("/observe", {"video_fps": 99}, expect=(400,), label="observe video_fps 99", valid=None)
    common_400s(t, J, 2)
    t.post_json("/observe", {"seconds": None, "last_s": None}, label="observe seconds null, last_s null")
    _, m, _ = t.get("/status", label="status after observes")
    check(m["control_steps"] == 0, "sidecar observe moved time")
    _, m, p = t.post_rcb1("/submit", {"type": J, "dt": 0.02, "video": "frames", "cameras": ["top"]},
                          np.tile([[0.01, 0.0]], (10, 1)), label="submit rcb1 10 rows")
    check(m["executed_rows"] == 10 and abs(m["duration_s"] - 0.2) < 1e-9 and abs(m["planned_duration_s"] - 0.2) < 1e-9,
          f"sidecar submit durations {m.get('duration_s')} {m.get('planned_duration_s')}")
    check("done" in m and not m["done"] and m["control_steps"] == 10, "sidecar submit counters")
    check(m.get("frame_step") == 10, f"sidecar submit with images has frame_step: {m.get('frame_step')}")
    check(p["frames/top"]["data"].shape[0] == p["proprio"]["data"].shape[0], "sidecar submit frames and proprio share the frame axis")
    _, m, _ = t.post_json("/submit", {"type": J, "dt": 0.04, "actions": [[0.0, 0.0]] * 5, "video": "none",
                                      "seconds": None}, label="submit json dt=2 steps (seconds null)")
    check(abs(m["duration_s"] - 0.2) < 1e-9 and m["control_steps_chunk"] == 10, f"sidecar submit dt 0.04 {m.get('duration_s')}")
    _, m, _ = t.post_json("/submit", {"type": J, "interpolate": "hold", "seconds": 0.5, "video": "frames"},
                          label="hold chunk")
    check(m.get("hold") is True and m["executed_rows"] == 0 and abs(m["duration_s"] - 0.5) < 1e-9
          and abs(m["planned_duration_s"] - 0.5) < 1e-9, f"sidecar hold chunk meta {m}")
    t.post_json("/submit", {"type": J, "interpolate": "hold", "seconds": 0.5, "actions": [[0, 0]]}, expect=(400,),
                label="rows + seconds", valid=False)
    t.post_json("/submit", {"type": J, "seconds": 0, "actions": [[0, 0]]}, expect=(400,), label="rows + seconds 0",
                valid=False)
    t.post_json("/submit", {"type": J, "interpolate": "hold", "seconds": spec["max_chunk_s"] + 0.5}, expect=(400,),
                label="hold over max_chunk_s")
    t.post_json("/submit", {"type": J}, expect=(400,), label="no rows, no hold", valid=False)
    t.post_json("/submit", {"type": J, "seconds": 0.5}, expect=(400,), label="seconds without interpolate hold", valid=False)
    t.post_json("/submit", {"type": J, "actions": [[0, 0]], "interpolate": "cubic"}, expect=(400,), label="bad interpolate",
                valid=False)
    t.post_json("/submit", {"type": J, "actions": [[0, 0]], "dt": 0.03}, expect=(400,), label="dt not a multiple")
    t.post_json("/submit", {"type": "nope", "actions": [[0, 0]]}, expect=(400,), label="unknown type")
    t.post_json("/submit", {"type": J, "actions": [[0, 0, 0]]}, expect=(400,), label="wrong dim")
    _, m, p = t.post_json("/observe", {"last_s": 0.6, "video": "frames"}, label="observe last_s 0.6")
    check(0 < m["last_s"] <= 0.6 + 1e-9 and "frame_step" in p and m["frame_step"] == int(p["frame_step"]["data"][-1]),
          f"sidecar observe last_s window {m.get('last_s')} {sorted(p)}")
    check(m["control_steps"] == 45, f"sidecar control steps after 10 + 10 + 25: {m['control_steps']}")
    t.post_json("/observe", {"last_s": 0.6, "include_depth": True}, expect=(400,), label="observe depth with last_s")
    t.post_json("/kinematics", {"op": "fk", "q": [0, 0]}, expect=(404,), label="kinematics (not sidecar)")
    t.get("/operations/abc", expect=(404,), label="operations (not sidecar)")
    t.post_raw_length("/submit", str(65 * 1024 * 1024), (413,), "body over 64 MiB")
    t.post_raw_length("/submit", "-1", (400,), "negative Content-Length")
    t.post_raw_length("/finish", str(65 * 1024 * 1024), (413,), "finish body over 64 MiB")
    _, s, _ = t.get("/status", label="status after a refused finish")
    check(not s["done"] and s["resets_left"] == 1, f"sidecar a refused /finish ended the episode: {s}")
    _, m, p = t.post_json("/reset", {}, label="reset")
    check(m["episode"] == 2 and m["resets_left"] == 0 and m["control_steps"] == 0, f"sidecar reset meta {m}")
    check(any(k.startswith("last/") for k in p) and isinstance(m.get("frame_step"), int),
          f"sidecar reset answers with the current frame and frame_step: {m.get('frame_step')} {sorted(p)}")
    t.post_json("/reset", {}, expect=(409,), label="reset over budget")
    t.post_json("/submit", {"type": J, "actions": [[0.01, 0.0]] * 3, "video": "none"}, label="submit after reset")
    _, f, _ = t.post_bytes("/finish", b"not json at all", label="finish with a body it ignores")
    check(f["ok"] is True and f["reason"] == "finished" and f["done"] is True, f"sidecar finish {f}")
    _, c, _ = t.post_json("/submit", {"type": J, "actions": [[0, 0]], "video": "none"}, expect=(409,),
                          label="submit after finish")
    check(c.get("resets_left", 0) == 0, f"sidecar 409 after finish reports resets_left {c.get('resets_left')}")
    t.post_json("/observe", {}, expect=(409,), label="observe after finish")
    t.post_json("/finish", {}, expect=(409,), label="finish after finish")
    t.post_json("/reset", {}, expect=(409,), label="reset after finish")
    t.get("/spec", label="spec after finish")
    _, s, _ = t.get("/status", label="status after finish")
    check(s["done"] and s["reason"] == "finished" and s["resets_left"] == 0, f"sidecar status after finish {s}")


def realtime_layer(t: Target) -> None:
    """The realtime layer: rcb_realtime.py over rcb_service.py (the thread recorder), agent-ended, reset budget 1."""
    J = "joint_position"
    _, spec, _ = t.get("/spec", label="spec")
    tm = spec["timing"]
    check(spec["protocol"] == "eai-standard/3.0" and tm.get("realtime") is True and "max_ahead_steps" in tm,
          f"realtime spec timing {sorted(tm)}")
    rec = tm.get("recorder", {})
    check({"cameras", "fps", "buffer_s", "records", "depth"} <= set(rec) and rec["fps"] == 10.0,
          f"realtime spec timing.recorder (thread recorder: 10 fps) {rec}")
    _, m, p = t.post_json("/observe", {}, label="observe before the clock")
    check(m["running"] is False, "realtime observe started the clock")
    _, m, p = t.post_json("/observe", {"cameras": []}, label="observe no images")
    check(not any(k.startswith(("last/", "frames/")) for k in p), f"realtime cameras [] parts {sorted(p)}")
    time.sleep(0.3)
    _, s, _ = t.get("/status", label="status before the first submit")
    check(s["running"] is False and s["control_steps"] == 0, f"realtime the clock ran before the first submit: {s}")
    _, e, _ = t.post_json("/observe", {"seconds": 1.0}, expect=(400,), label="observe seconds>0", valid=False)
    check("hold" in e.get("error", ""), "realtime observe seconds>0 names the hold chunk")
    t0 = time.time()
    _, m, p2 = t.post_rcb1("/submit", {"type": J, "dt": 0.02}, np.tile([[0.002, 0.0]], (10, 1)), label="submit rcb1")
    check(time.time() - t0 < 1.0, "realtime submit answers at once")
    check(m["running"] is True and m["end_step"] == m["plan_end_step"] and abs(m["duration_s"] - 0.2) < 1e-9
          and "start_step" in m and "late_steps" in m, f"realtime submit meta {m}")
    check(("last/top" not in p2) or isinstance(m.get("frame_step"), int), f"realtime submit with images has frame_step: {sorted(p2)}")
    time.sleep(0.6)
    _, m, p = t.post_json("/observe", {"last_s": 0.4, "video": "frames"}, label="observe last_s 0.4")
    check(m["control_steps"] > 10 and m.get("frame_step") is not None and 0 < m["last_s"] <= 0.4 + 1e-9,
          f"realtime observe window: steps {m['control_steps']} frame_step {m.get('frame_step')} last_s {m.get('last_s')}")
    no_depth = [c for c in rec.get("cameras", []) if c not in rec.get("depth", [])]
    if no_depth:                                             # per-frame depth only for the recorder's depth cameras
        t.post_json("/observe", {"last_s": 0.4, "include_depth": True, "cameras": no_depth[:1]}, expect=(400,),
                    label="observe depth with last_s, camera without recorded depth")
    if rec.get("depth"):
        t.post_json("/observe", {"last_s": 0.4, "include_depth": True, "cameras": rec["depth"][:1], "video": "frames"},
                    label="observe depth with last_s, recorder depth camera")
    _, m, _ = t.post_json("/submit", {"type": J, "interpolate": "hold", "seconds": 0.3}, label="hold chunk")
    check(m.get("hold") is True and abs(m["duration_s"] - 0.3) < 1e-9 and "end_step" in m and m.get("executed_rows") == 0,
          f"realtime hold meta {m}")
    common_400s(t, J, 2, status=False)
    t.post_json("/submit", {"type": J, "actions": [[0, 0]], "at": 10 ** 6}, expect=(400,), label="at too far ahead")
    t.post_json("/submit", {"type": J, "interpolate": "hold", "seconds": 0.5, "actions": [[0, 0]]}, expect=(400,),
                label="rows + seconds", valid=False)
    t.post_json("/submit", {"type": J, "seconds": 0, "actions": [[0, 0]]}, expect=(400,), label="rows + seconds 0",
                valid=False)
    t.post_json("/submit", {"type": J, "interpolate": "hold", "seconds": spec["max_chunk_s"] + 0.5}, expect=(400,),
                label="hold over max_chunk_s")
    t.post_json("/kinematics", {"op": "fk", "q": [0, 0]}, expect=(404,), label="kinematics (not realtime)")
    t.post_raw_length("/submit", str(65 * 1024 * 1024), (413,), "body over 64 MiB")
    t.post_raw_length("/finish", str(65 * 1024 * 1024), (413,), "finish body over 64 MiB")
    t.post_raw_length("/finish", "-1", (400,), "finish negative Content-Length")
    _, s, _ = t.get("/status", label="status after refused finishes")
    check(not s["done"], f"realtime a refused /finish ended the episode: {s}")
    _, m, p = t.post_json("/reset", {}, label="reset")
    check(m["episode"] == 2 and m["running"] is False, f"realtime reset meta {m}")
    check(any(k.startswith("last/") for k in p) and isinstance(m.get("frame_step"), int),
          f"realtime reset answers with the current frame and frame_step: {m.get('frame_step')} {sorted(p)}")
    time.sleep(0.2)
    _, s, _ = t.get("/status", label="status after reset")
    check(s["running"] is False and s["control_steps"] == 0, "realtime a reset leaves the episode paused")
    t.post_json("/submit", {"type": J, "actions": [[0.001, 0.0]] * 5}, label="submit after reset")
    _, f, _ = t.post_bytes("/finish", b"", label="finish with an empty body")
    check(f["ok"] is True and f["reason"] == "finished" and f["running"] is False, f"realtime finish {f}")
    t.post_json("/submit", {"type": J, "actions": [[0, 0]]}, expect=(409,), label="submit after finish")
    t.post_json("/observe", {}, expect=(409,), label="observe after finish")
    t.post_json("/finish", {}, expect=(409,), label="finish after finish")
    _, s, _ = t.get("/status", label="status after finish")
    check(s["done"] and s["reason"] == "finished" and s.get("resets_left") == 0, f"realtime status after finish {s}")


def common_400s(t: Target, J: str, dim: int, status: bool = True) -> None:
    """The 400s every layer answers before anything runs (the OpenAPI BadRequest): nothing ran (status=True: the
    control steps unchanged; a realtime clock may run, so it is checked by the answer only)."""
    send = t.bad if status else (lambda path, body, label, valid=False:
                                 t.post_json(path, body, expect=(400,), label=label, valid=valid)[1])
    row = [0.0] * dim
    send("/submit", {"type": J, "actions": [row], "interpolate": "cubic"}, "interpolate cubic")
    send("/submit", {"type": J, "actions": [row] * 800, "dt": 0.02 if dim == 2 else 0.05},
         "a chunk over max_chunk_s (rows x dt)", valid=None)
    send("/submit", {"type": J, "interpolate": "hold", "seconds": True}, "hold seconds true")
    send("/submit", {"type": J, "interpolate": "hold", "seconds": "0.1"}, "hold seconds string")
    send("/submit", {"type": J, "actions": [row], "dt": "0.05"}, "dt string")
    for fps, valid in ((0, False), (0.5, False), (99, None), (True, False)):
        send("/observe", {"video_fps": fps}, f"observe video_fps {fps!r}", valid=valid)
    send("/observe", {"last_s": "1"}, "observe last_s string")
    send("/observe", {"seconds": True}, "observe seconds true")


def shared_layer(t: Target, operations: bool = False) -> None:
    """The shared layer (rcb_limited.py) on toy_server.py: no reset budget; /kinematics."""
    J = "joint_position"
    _, spec, _ = t.get("/spec", label="spec")
    check(spec["protocol"] == "eai-standard/3.0" and bool(spec.get("operations")) == operations and "kinematics" in spec,
          f"{t.name} spec ids {spec.get('protocol')}")
    t.get("/status", label="status")
    _, m, p = t.post_json("/observe", {"last_s": 0}, label="observe now")
    check(m.get("last_s") == 0 and "frame_step" in p and "stopped" in m, f"{t.name} observe meta {m}")
    check(isinstance(m.get("frame_step"), int), f"{t.name} observe now has meta.frame_step: {m.get('frame_step')}")
    rec = spec["timing"]["recorder"]
    check(rec.get("depth") == [] and rec.get("fps") == 10.0 and "max_watch_s" not in spec, f"{t.name} recorder {rec}")
    t.post_json("/observe", {"seconds": 0.5}, expect=(400,), label="observe seconds>0", valid=False)
    _, m, _ = t.post_rcb1("/submit", {"type": J, "dt": 0.05}, np.zeros((6, 3)), label="submit rcb1")
    check(abs(m["duration_s"] - 0.3) < 1e-9 and abs(m["planned_duration_s"] - 0.3) < 1e-9, f"{t.name} submit durations {m}")
    check(isinstance(m.get("frame_step"), int), f"{t.name} submit has meta.frame_step: {m.get('frame_step')}")
    t.post_json("/submit", {"type": J, "seconds": 0, "actions": [[0, 0, 0]]}, expect=(400,), label="rows + seconds 0",
                valid=False)
    t.post_json("/submit", {"type": J, "interpolate": "hold", "seconds": spec["max_chunk_s"] + 0.5}, expect=(400,),
                label="hold over max_chunk_s")
    _, m, _ = t.post_json("/submit", {"type": J, "interpolate": "hold", "seconds": 0.25}, label="hold chunk")
    check(m.get("hold") is True and m["executed_rows"] == 0 and abs(m["duration_s"] - 0.25) < 1e-9, f"{t.name} hold {m}")
    t.post_json("/submit", {"type": J, "interpolate": "hold", "seconds": 0.5, "actions": [[0, 0, 0]]}, expect=(400,),
                label="rows + seconds", valid=False)
    _, m, _ = t.post_json("/submit", {"type": J, "interpolate": "hold", "seconds": 0.01, "video": "none"},
                          label="hold chunk under one control step")
    check(m.get("control_steps_chunk") == 1 and abs(m["duration_s"] - 0.05) < 1e-9
          and abs(m["planned_duration_s"] - 0.01) < 1e-9 and isinstance(m.get("chunk_id"), int),
          f"{t.name} a hold under one step runs one and plans what was sent: {m}")
    common_400s(t, J, 3)
    _, m, _ = t.post_json("/submit", {"type": J, "actions": [[0, 0, 0]] * 200, "dt": 0.05, "video": "none"},
                          label="a chunk of exactly max_chunk_s")
    check(m.get("executed_rows") == 200, f"{t.name} a chunk of max_chunk_s: {m.get('executed_rows')}")
    _, m, _ = t.post_json("/observe", {"video_fps": 30, "seconds": None}, label="observe video_fps 30, seconds null")
    _, m, p = t.post_json("/observe", {"last_s": 0.5, "video": "frames"}, label="observe last_s 0.5")
    check(m.get("last_s", 0) > 0 and m.get("frame_step") == int(p["frame_step"]["data"][-1]), f"{t.name} observe window {m}")
    t.post_json("/observe", {"last_s": 0.5, "depth": "frames"}, expect=(400,), label="observe depth frames with last_s")
    _, k, _ = t.post_json("/kinematics", {"op": "fk", "q": [0, 0, 0]}, label="kinematics fk")
    check(k.get("ok") is True and k.get("op") == "fk", f"{t.name} kinematics {k}")
    t.post_json("/kinematics", {"op": "xx"}, expect=(400,), label="kinematics bad op", valid=False)
    t.post_json("/reset", {}, expect=(404,), label="reset without a budget")
    t.post_raw_length("/submit", str(65 * 1024 * 1024), (413,), "body over 64 MiB")
    t.post_raw_length("/observe", "-1", (400,), "negative Content-Length")
    if not operations:
        simulator_error(t)


def simulator_error(t: Target) -> None:
    """A simulator error (the toy raises on note "raise"): a 500, the episode ends (reason error), /submit then 409."""
    t.post_json("/observe", {"note": "raise"}, expect=(500,), label="observe: the simulator raises")
    _, s, _ = t.get("/status", label="status after a simulator error")
    check(s["done"] and s["reason"] == "error", f"{t.name} a simulator error ends the episode: {s}")
    t.post_json("/submit", {"type": "joint_position", "actions": [[0, 0, 0]]}, expect=(409,), label="submit after the error")


def operations_layer(t: Target) -> None:
    shared_layer(t, operations=True)
    J = "joint_position"
    deadline = time.time() + 600
    _, m, _ = t.post_json("/submit", {"type": J, "actions": [[0, 0, 0]], "operation_id": "op-1",
                                      "request_deadline_unix_s": deadline}, label="submit with an operation id")
    check(m.get("operation_id") == "op-1", f"operations operation_id echoed: {m.get('operation_id')}")
    _, rec, _ = t.get("/operations/op-1", label="operation record")
    check(rec.get("status") == "completed" and rec.get("committed_rows", -1) >= rec.get("rows_before", 0), f"operations record {rec}")
    _, c, _ = t.post_json("/submit", {"type": J, "actions": [[0, 0, 0]], "operation_id": "op-1"}, expect=(409,),
                          label="operation id again")
    check(c.get("operation_id") == "op-1" and isinstance(c.get("operation"), dict), f"operations 409 body {c}")
    t.post_json("/submit", {"type": J, "actions": [[0, 0, 0]], "request_deadline_unix_s": time.time() - 5}, expect=(408,),
                label="deadline passed")
    t.post_json("/submit", {"type": J, "actions": [[0, 0, 0]], "operation_id": "bad id!"}, expect=(400,),
                label="malformed operation id", valid=False)
    t.get("/operations/bad.id", expect=(400,), label="operation malformed id")
    t.get("/operations/unknown", expect=(404,), label="operation unknown id")
    simulator_error(t)


def agent_ended(t: Target, operations: bool = False) -> None:
    """The shared and the operations layers' /finish (rcb_agent_end.py on the toy; FinishResponse), the 409s after it."""
    J = "joint_position"
    _, spec, _ = t.get("/spec", label="spec")
    check(spec["protocol"] == "eai-standard/3.0" and bool(spec.get("operations")) == operations
          and str(spec.get("success_signal", "")).startswith("hidden"),
          f"{t.name} spec {spec.get('protocol')} {spec.get('success_signal')}")
    _, m, _ = t.post_json("/submit", {"type": J, "actions": [[0.5, 0, 0]] * 12, "video": "none"}, label="submit")
    check(not m["done"] and m["reason"] is None and "success" not in m, f"{t.name} a submit shows nothing of the success: {m}")
    common_400s(t, J, 3)
    if operations:
        _, m, _ = t.post_json("/submit", {"type": J, "actions": [[0.5, 0, 0]], "operation_id": "op-ae",
                                          "video": "none"}, label="submit with an operation id")
        t.get("/operations/op-ae", label="operation record before finish")
    t.post_raw_length("/finish", str(65 * 1024 * 1024), (413,), "finish body over 64 MiB")
    t.post_raw_length("/finish", "-1", (400,), "finish negative Content-Length")
    _, s, _ = t.get("/status", label="status after refused finishes")
    check(not s["done"], f"{t.name} a refused /finish ended the episode: {s}")
    _, f, _ = t.post_bytes("/finish", b"not json at all", label="finish with a body it ignores")
    check(f.get("ok") is True and f.get("done") is True and f.get("reason") == "finished", f"{t.name} finish {f}")
    t.post_json("/submit", {"type": J, "actions": [[0, 0, 0]], "video": "none"}, expect=(409,), label="submit after finish")
    t.post_json("/submit", {"type": J, "interpolate": "hold", "seconds": 0.1}, expect=(409,), label="hold after finish")
    t.post_json("/observe", {}, expect=(409,), label="observe after finish")
    t.post_json("/observe", {"last_s": 0.5}, expect=(409,), label="observe last_s after finish")
    t.post_json("/kinematics", {"op": "fk", "q": [0, 0, 0]}, expect=(409,), label="kinematics after finish")
    t.post_json("/finish", {}, expect=(409,), label="finish after finish")
    if operations:
        t.get("/operations/op-ae", expect=(409,), label="operation record after finish")
    t.get("/spec", label="spec after finish")
    _, s, _ = t.get("/status", label="status after finish")
    check(s["done"] and s["reason"] == "finished", f"{t.name} status after finish {s}")


def agent_ended_operations(t: Target) -> None:
    agent_ended(t, operations=True)


def step_limit(t: Target) -> None:
    """RCB_STEP_LIMIT=30: steps_left in every meta and /status, the hold chunk cut at the limit (reason
    step_limit), then /submit and /finish 409 while /observe answers."""
    J = "joint_position"
    _, spec, _ = t.get("/spec", label="spec")
    dim = int(spec["action_types"][J]["dim"])
    hz = spec.get("control_hz") or 1.0 / spec["control_dt"]
    check(spec.get("budget", {}).get("steps") in (30, None), f"{t.name} spec budget.steps {spec.get('budget')}")
    _, m, _ = t.post_json("/submit", {"type": J, "actions": [[0.01] + [0.0] * (dim - 1)] * 10, "video": "none"},
                          label="submit 10 rows")
    check(m.get("step_limit") == 30 and m.get("steps_left") == 20 and not m["done"], f"{t.name} steps_left {m}")
    _, s, _ = t.get("/status", label="status")
    check(s.get("step_limit") == 30 and s.get("steps_left") == 20, f"{t.name} status steps_left {s}")
    _, m, _ = t.post_json("/submit", {"type": J, "interpolate": "hold", "seconds": 2.0, "video": "none"},
                          label="hold chunk past the step limit")
    check(m.get("hold") is True and m["done"] and m["reason"] == "step_limit" and m.get("steps_left") == 0
          and abs(m["duration_s"] - 20 / hz) < 1e-6 and m.get("executed_rows") == 0,
          f"{t.name} the hold chunk cut at the step limit: {m}")
    t.post_json("/submit", {"type": J, "actions": [[0.0] * dim], "video": "none"}, expect=(409,),
                label="submit after the step limit")
    t.post_json("/finish", {}, expect=(409,), label="finish after the step limit")
    _, m, _ = t.post_json("/observe", {"last_s": 0.5}, label="observe after the step limit")
    check(m["done"] and m["reason"] == "step_limit" and m.get("steps_left") == 0, f"{t.name} observe after the limit {m}")


def gave_up(t: Target) -> None:
    """A service that gave up on the trial (RCB_TOY_REFUSE): every endpoint is a 409 with gave_up."""
    for method, path, body in (("GET", "/spec", None), ("GET", "/status", None), ("POST", "/observe", {}),
                               ("POST", "/submit", {"type": "joint_position", "actions": [[0, 0, 0]]}),
                               ("POST", "/finish", {}), ("POST", "/kinematics", {"op": "fk", "q": [0, 0, 0]})):
        if method == "GET":
            _, b, _ = t.get(path, expect=(409,), label=f"{path} after a give-up")
        else:
            _, b, _ = t.post_json(path, body, expect=(409,), label=f"{path} after a give-up")
        check(b.get("gave_up") is True and b.get("reason"), f"{t.name} {path}: {b}")


def stage(work: pathlib.Path, std: pathlib.Path, name: str, layer: str) -> pathlib.Path:
    """toy_server.py staged with a layer (shared: rcb_limited.py; operations: operations/rcb_limited.py), rcb1.py and
    rcb_agent_end.py (the toy is an agent-ended adapter). Returns the directory."""
    d = work / f"stage_{name}"
    d.mkdir(exist_ok=True)
    shutil.copy2(std / "toy_server.py", d / "toy_server.py")
    shutil.copy2(std / "agent_end/rcb_agent_end.py", d / "rcb_agent_end.py")
    shutil.copy2(std / layer, d / "rcb_limited.py")
    shutil.copy2(std / "rcb1.py", d / "rcb1.py")
    (d / "launch_toy.py").write_text(LAUNCH_TOY)
    return d


LAUNCH_TOY = """import os, runpy, sys, time
sys.dont_write_bytecode = True
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import rcb_limited as L
if not hasattr(L, "agent_time"):
    L.agent_time = lambda state: 0.0 if state.get("t_first") is None else max(0.0, time.time() - float(state["t_first"]))
runpy.run_path(os.path.join(here, "toy_server.py"), run_name="__main__")
"""


# ---------------------------------------------------------------------------------------------- main
# the toy_server.py targets: (layer file, extra environment, scenario)
TOYS = {"shared": ("rcb_limited.py", {}, shared_layer),
        "shared-finish": ("rcb_limited.py", {}, agent_ended),
        "shared-limit": ("rcb_limited.py", {"RCB_STEP_LIMIT": "30"}, step_limit),
        "shared-gaveup": ("rcb_limited.py", {"RCB_TOY_REFUSE": "the contract check's refusal"}, gave_up),   # (+ RCB_PORT)
        "operations": ("operations/rcb_limited.py", {}, operations_layer),
        "operations-finish": ("operations/rcb_limited.py", {}, agent_ended_operations),
        "operations-limit": ("operations/rcb_limited.py", {"RCB_STEP_LIMIT": "30"}, step_limit)}
TARGETS = ("sidecar", "sidecar-limit", "realtime", "shared", "shared-finish", "shared-limit", "shared-gaveup", "operations",
           "operations-finish", "operations-limit")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=str(HERE.parent), help="repository root (default: this script's parent's parent)")
    ap.add_argument("--spec", default=None, help="the OpenAPI file (default: <repo>/docs/protocol/eai-standard.openapi.yaml)")
    ap.add_argument("--targets", default=",".join(TARGETS))
    ap.add_argument("--work", default=None, help="scratch directory (default: a new temporary one, removed at the end)")
    ap.add_argument("--keep", action="store_true", help="keep the scratch directory")
    a = ap.parse_args()
    repo = pathlib.Path(a.repo).resolve()
    spec_path = pathlib.Path(a.spec) if a.spec else repo / "docs/protocol/eai-standard.openapi.yaml"
    doc = yaml.safe_load(spec_path.read_text())
    check_document(doc, spec_path)

    std = repo / "embodied_first_exam/standard"
    sys.path.insert(0, str(std))
    import rcb1                                             # the shipped codec (never writes bytecode: see top)
    contract = Contract(doc, rcb1)

    work = pathlib.Path(a.work) if a.work else pathlib.Path(tempfile.mkdtemp(prefix="openapi_contract_"))
    work.mkdir(parents=True, exist_ok=True)
    base_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "RCB_WALL_CLOCK_S": "600", "RCB_STARTUP_TIMEOUT_S": "120"}
    for k in ("RCB_STEP_LIMIT", "RCB_RESET_BUDGET", "RCB_SLOWDOWN", "RCB_CAMERA_FPS", "RCB_LOOKBACK_S"):
        base_env.pop(k, None)
    toy = std / "mcp/tests/toy_realtime.py"
    py = sys.executable
    targets = [x.strip() for x in a.targets.split(",") if x.strip()]
    results = {}
    try:
        for name in targets:
            n0 = len(fails)
            port = free_port()
            data = work / f"data_{name}"
            shutil.rmtree(data, ignore_errors=True)            # a fresh trial: never an episode a previous run ended
            env = {**base_env, "RCB_DATA": str(data)}
            if name in ("sidecar", "realtime", "sidecar-limit"):
                env.update(RCB_RESET_BUDGET="1")
                if name == "sidecar-limit":
                    env.update(RCB_STEP_LIMIT="30")
                argv = [py, str(toy), str(port)] + (["--standard"] if name != "realtime" else [])
                run = {"sidecar": sidecar_layer, "realtime": realtime_layer, "sidecar-limit": step_limit}[name]
            elif name in TOYS:
                # toy_server.py (the shared-layer toy) staged next to the layer (operations/rcb_limited.py for operations: the
                # repository has no runnable operations toy service), with rcb_agent_end.py; a launcher gives the operations module the one helper the toy needs that it lacks (agent_time, the shared
                # layer's first-request clock)
                layer, extra, run = TOYS[name]
                d = stage(work, std, name, layer)
                env.update(RCB_TOY_PORT=str(port), RCB_PORT=str(port), **extra)   # RCB_PORT: the give-up's refusal
                argv = [py, str(d / "launch_toy.py")]
            else:
                check(False, f"unknown target {name}")
                continue
            t = None
            try:
                t = Target(name, argv, env, work, contract, port)
                run(t)
            except Exception as exc:  # noqa: BLE001
                check(False, f"{name}: {type(exc).__name__}: {exc}")
            finally:
                if t is not None:
                    t.stop()
            results[name] = len(fails) == n0
            print(f"{name}: {'PASS' if results[name] else 'FAIL'}", flush=True)
    finally:
        if not a.keep and not a.work:
            shutil.rmtree(work, ignore_errors=True)
    print(f"\n{counts['requests']} answers checked ({counts['validated']} bodies validated against the schemas); "
          + ", ".join(f"{k}: {'PASS' if v else 'FAIL'}" for k, v in results.items()))
    if fails:
        print(f"{len(fails)} failure(s)")
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
