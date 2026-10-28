"""Public HTTP instruments for local adaptation tests; no harness mappings are supplied."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import threading
from urllib.parse import urlsplit, parse_qs

import numpy as np


class PublicInstrument:
    """Serve an ordinary instrument manual, client, examples and a stateful API."""

    def __init__(self, family="schema"):
        self.family = family
        self.position = 0
        self.revision = 1
        self.actions = []
        self.receipts = {}
        self.uncertain = False
        self.reads = []
        self.depth = True
        self.depth_units = "mm"
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                path = urlsplit(self.path).path
                fixture.reads.append(path)
                if path.startswith("/public/"):
                    value = fixture.public(path)
                    if value is None:
                        self.send_error(404)
                        return
                elif path == "/api/sample":
                    value = fixture.sample()
                elif path == "/api/status":
                    ident = parse_qs(urlsplit(self.path).query).get("request_id", [""])[0]
                    value = {"request_id": ident, "status": "completed", "result": fixture.receipts[ident]} if ident in fixture.receipts else {"request_id": ident, "status": "not_executed"}
                else:
                    self.send_error(404)
                    return
                self.reply(value)

            def do_POST(self):
                args = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path != "/api/advance" or fixture.field not in args:
                    self.send_error(400)
                    return
                delta = args[fixture.field]
                if not isinstance(delta, (int, float)) or not 0 < delta <= 2:
                    self.send_error(400)
                    return
                fixture.position += delta * fixture.scale
                fixture.actions.append(args)
                result = fixture.sample()
                fixture.receipts[args.get("request_id", "")] = result
                if fixture.uncertain:
                    fixture.uncertain = False
                    self.close_connection = True
                    return
                self.reply(result)

            def reply(self, value):
                data = value if isinstance(value, bytes) else value.encode() if isinstance(value, str) else json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream" if isinstance(value, bytes) else "text/plain" if isinstance(value, str) else "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def field(self):
        return "delta_mm" if self.revision == 1 else "delta_cm"

    @property
    def scale(self):
        return 1 if self.revision == 1 else 10

    def sample(self):
        return {"position_mm": self.position, "revision": self.revision}

    def bootstrap(self):
        task = "Use the public instrument to reach position_mm=4, then obtain a confirming public sample. Complete the task after adapting the interface. Do not claim private evaluator success."
        if self.family == "rgbd":
            task += " Also retrieve the original RGB-D arrays and public calibration, use a scientific Python dependency to compute all valid depth pixels in world coordinates in metres, and save the point list as JSON in world-points.json in the scientific workspace outputs."
        return {"schema": "bootstrap-v1", "task": task,
                "entries": [self.url + "/public/manual.md"], "source_roots": [self.url + "/public"],
                "internet": False, "transports": [{"id": "instrument", "kind": "http", "root": self.url + "/api"}], "max_actions": 8}

    def public(self, path):
        if path == "/public/manual.md":
            schema = "The public machine schema is [schema.json](schema.json)." if self.family == "schema" else "There is no machine schema; use the client and this manual."
            return f"""# Linear instrument, revision {self.revision}
{schema}
Public [examples](examples.json), [Python client](client.py), [resources](resources.json).
GET /api/sample with no arguments is read-only and returns {{"position_mm": number, "revision": integer}}.
POST /api/advance takes {{"{self.field}": number, "request_id": string}}. {self.field} is positive and at most 2;
it advances the instrument by that many {'millimetres' if self.scale == 1 else 'centimetres'} along the positive rail axis.
Each call consumes one native action; it advances time by 0.1 seconds and returns a fresh sample.
A current sample is required before an advance. It returns the same fields as sample, always in mm.
request_id is an operation tracking identifier. GET /api/status?request_id=ID is read-only, costs zero actions,
and returns {{request_id:ID,status:'completed',result:the original response}} or {{request_id:ID,status:'not_executed'}}.
The status query does not replay an advance. No stop, reset, camera, contact, hidden success or robot geometry API exists.
Reads cost zero actions and do not advance time. No separate initialization is needed. All coordinates use rail frame.
For delta=1 at position 0, the returned position_mm is {self.scale}. For GET sample at position 0, it is 0.
The client is dependency-free and provides a pure request encoder; use it when constructing requests.
"""
        if path == "/public/client.py":
            return f'''"""Public pure Python client helpers; dispatch uses the caller's HTTP transport."""
def advance(delta, request_id):
    return {{"body": {{"{self.field}": delta, "request_id": request_id}}}}
def sample():
    return {{}}
def status(request_id):
    return {{"query": {{"request_id": request_id}}}}
'''
        if path == "/public/examples.json":
            return {"sample": {"args": {}, "wire": {}, "response": {"position_mm": 0, "revision": self.revision}},
                    "advance": {"args": {"delta": 1}, "wire": {"body": {self.field: 1, "request_id": "validation"}},
                                "response": {"position_mm": self.scale, "revision": self.revision}},
                    "status": {"args": {"request_id": "example"}, "wire": {"query": {"request_id": "example"}},
                               "response": {"request_id": "example", "status": "completed", "result": {"position_mm": self.scale, "revision": self.revision}}}}
        if path == "/public/schema.json" and self.family == "schema":
            return {"openapi": "3.1.0", "paths": {"/api/sample": {"get": {"description": "read-only public sample"}},
                "/api/advance": {"post": {"requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {
                    self.field: {"type": "number", "exclusiveMinimum": 0, "maximum": 2}, "request_id": {"type": "string"}}, "required": [self.field, "request_id"]}}}}}}}}
        if path == "/public/resources.json":
            return {"depth": {"uri": "depth.npy", "codec": "npy", "dtype": "uint16" if self.depth_units == "mm" else "float32", "shape": [2, 2], "units": self.depth_units, "invalid_values": [0],
                              "frame": "camera_optical", "timestamp": 12.5, "observation_id": "frame-7", "calibration": {
                                  "projection": "pinhole", "depth_convention": "optical_z", "pixel_axes": "u right, v down", "fx": 2, "fy": 2, "cx": 0, "cy": 0,
                                  "camera_to_world_rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "camera_to_world_translation_m": [1, 0, 0]}} if self.depth else None,
                    "rgb": {"uri": "rgb.npy", "codec": "npy", "dtype": "uint8", "shape": [2, 2, 3], "frame": "camera_optical", "timestamp": 12.5, "observation_id": "frame-7"}}
        if path in {"/public/depth.npy", "/public/rgb.npy"}:
            array = (np.array([[1000, 2000], [0, 4000]], dtype=np.uint16) if self.depth_units == "mm" else np.array([[1, 2], [0, 4]], dtype=np.float32)) if "depth" in path else np.zeros((2, 2, 3), dtype=np.uint8)
            output = io.BytesIO()
            np.save(output, array)
            return output.getvalue()
        return None

    def outcome(self, output):
        points = None
        if self.family == "rgbd":
            paths = list(output.rglob("world-points.json"))
            if paths:
                try:
                    points = json.loads(paths[-1].read_text())
                except (ValueError, OSError):
                    pass
        return {"public_sample": "/api/sample" in self.reads, "bounded_actions": bool(self.actions),
                "physical_actions": len(self.actions), "final_position_mm": self.position,
                "world_points": points,
                "task_success": self.position == 4 and (self.family != "rgbd" or points == [[1, 0, 1], [2, 0, 2], [3, 2, 4]])}

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def scripted_artifact(service, *, client=False, include_status=False):
    """Supply a scripted test artifact, never used in autonomous trials."""
    refs = {r["uri"].rsplit("/", 1)[-1]: r["id"] for r in service.discovery.records.values()
            if service.discovery.current[r["uri"]] == r["id"]}
    revision = service.discovery.value(refs["examples.json"])["sample"]["response"]["revision"]
    field = "delta_mm" if revision == 1 else "delta_cm"
    source = f'''def run(x, tools):
    if x['phase'] == 'decode': return x['value']
    if x['operation'] == 'sample': return {{}}
    if x['operation'] == 'status': return {{'query': {{'request_id': x['value']['request_id']}}}}
    return {{'body': {{'{field}': x['value']['delta'], 'request_id': x['request_id']}}}}
'''
    if client:
        source = '''def run(x, tools):
    import runpy
    if x['phase'] == 'decode': return x['value']
    client = runpy.run_path(next(p for p in x['sources'].values() if p.endswith('/client.py')))
    if x['operation'] == 'sample': return client['sample']()
    if x['operation'] == 'status': return client['status'](x['value']['request_id'])
    return client['advance'](x['value']['delta'], x['request_id'])
'''
    output_schema = {"type": "object", "properties": {"position_mm": {"type": "number"}, "revision": {"type": "integer"}}, "required": ["position_mm", "revision"], "additionalProperties": False}
    operations = []
    for name in ["sample", "advance"] + (["status"] if include_status else []):
        operations.append({"id": name, "description": "Public " + name, "transport": "instrument", "method": "POST" if name == "advance" else "GET", "path": name,
            "role": "action" if name == "advance" else "status" if name == "status" else "observation", "effect": "physical" if name == "advance" else "observe",
            "observation": name != "status", "cost_actions": int(name == "advance"), "requires_current_observation": name == "advance",
            "input_schema": {"type": "object", "properties": {"delta": {"type": "number", "exclusiveMinimum": 0, "maximum": 2}} if name == "advance" else {"request_id": {"type": "string"}} if name == "status" else {},
                             "required": ["delta"] if name == "advance" else ["request_id"] if name == "status" else [], "additionalProperties": False},
            "output_schema": output_schema if name != "status" else {"type": "object", "required": ["request_id", "status"], "properties": {"request_id": {"type": "string"}, "status": {"enum": ["completed", "not_executed", "unknown"]}, "result": output_schema}},
            "semantics": {"units": "mm" if revision == 1 else "cm input, mm output", "frame": "rail", "timing": "0.1s per advance, reads do not advance time", "lifecycle": "no init/stop/reset, status lookup available"}})
    cases = [{"operation": op["id"], "phase": phase, "source": refs["examples.json"],
              "input_pointer": f"/{op['id']}/" + ("args" if phase == "encode" else "response"),
              "expected_pointer": f"/{op['id']}/" + ("wire" if phase == "encode" else "response")}
             for op in operations for phase in ("encode", "decode")]
    return {"schema": "adapter-artifact-v1", "origin": "public_client" if client else "generated", "sources": list(refs.values()),
            "source": source, "operations": operations, "cases": cases, "unknowns": ["No hidden success, reset or depth API in the action interface"]}
