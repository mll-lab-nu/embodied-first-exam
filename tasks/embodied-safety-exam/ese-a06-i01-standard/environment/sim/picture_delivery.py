"""Benchmark extension for captured-frame transport, without changing the shared protocol implementation.

A completed server write is a transport observation, not proof that the model read an image. The realtime HTTP
thread queues completion; only the simulator thread applies it, conservatively at its next service boundary.
"""

from __future__ import annotations

import collections
import json
import struct
import threading
import time


def frame_ids(body):
    if body[:4] != b"RCB1":
        return []
    n = struct.unpack("<I", body[4:8])[0]
    header = json.loads(body[8 : 8 + n])
    ids = []
    for part in header["parts"]:
        if part["name"].startswith(("last/", "frames/", "video/", "depth/")):
            ids.extend(part.get("picture_frame_ids", ()))
    return list(dict.fromkeys(ids))


def install_http(service_class, realtime=False):
    original = service_class.http_server

    def http_server(self, address):
        http = original(self, address)
        base = http.RequestHandlerClass
        service = self

        class Handler(base):
            def _send(self, code, ctype, body):
                ids = frame_ids(body) if code == 200 and ctype == "application/x-rcb1" else []
                try:
                    super()._send(code, ctype, body)
                    self.wfile.flush()
                except OSError:
                    if ids:
                        service.log("picture_transport_failed", frame_ids=ids)
                    raise
                if ids:
                    completed = {"frame_ids": ids, "transport_completed_wall_s": time.time()}
                    if realtime:
                        with service._picture_completion_lock:
                            service._picture_completions.append(completed)
                    else:
                        service.sim.pictures_transport_completed(ids)
                        service.log("picture_transport_completed", **completed)

        http.RequestHandlerClass = Handler
        return http

    service_class.http_server = http_server
    if realtime:
        old_poll = service_class.poll

        def poll(self):
            # Before the next action/tick or finalizer: no MuJoCo or episode state access on an HTTP thread.
            with self._picture_completion_lock:
                completions = list(self._picture_completions)
                self._picture_completions.clear()
            for completed in completions:
                self.sim.pictures_transport_completed(completed["frame_ids"])
                self.log("picture_transport_completed", application="next_simulator_boundary", **completed)
            return old_poll(self)

        service_class.poll = poll


def install_standard(module):
    if getattr(module.Recorder, "_captured_transport_installed", False):
        return
    original_init, original_grab, original_parts = (
        module.Recorder.__init__,
        module.Recorder._grab,
        module.Recorder.parts,
    )

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._picture_ids = {camera: [] for camera in self.cams}

    def grab(self, images, proprio=True):
        original_grab(self, images, proprio)
        hook = getattr(self.sim, "picture_frame_ids", None)
        if images and self.cams and callable(hook):
            ids = hook(self.cams)
            for camera in self.cams:
                self._picture_ids[camera].append(ids[camera])

    def parts(self):
        result = []
        for name, kind, data, extra in original_parts(self):
            prefix, _, camera = name.partition("/")
            ids = self._picture_ids.get(camera, [])
            if ids and prefix in ("last", "frames", "video", "depth"):
                retained = ids[-1:] if prefix == "last" else ids
                retained = [frame_id for frame_id in retained if frame_id is not None]
                if retained:
                    extra = {**extra, "picture_frame_ids": retained}
            result.append((name, kind, data, extra))
        return result

    module.Recorder.__init__, module.Recorder._grab, module.Recorder.parts = init, grab, parts
    module.Recorder._captured_transport_installed = True
    old_init = module.Service.__init__

    def service_init(self, sim, **kwargs):
        old_init(self, sim, **kwargs)
        self._picture_completions = collections.deque()
        self._picture_completion_lock = threading.Lock()
        if callable(getattr(sim, "pictures_transport_completed", None)):
            # A successfully transported frame must never depend on unjournaled action rows after a crash.
            sim.before_picture_capture = lambda: self._checkpoint("picture_capture")

    module.Service.__init__ = service_init
    install_http(module.Service)
