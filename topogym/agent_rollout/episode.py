"""Disposable simulator process; the trial and token ledger live in its parent."""
import json
import multiprocessing
import os
from pathlib import Path
import signal
import time
import traceback


def _worker(connection, job, parent_pid):
    # A killed trial must not leave a GPU scene alive. Linux is required by the
    # Codex rollout sandbox; no simulator library is imported in the parent.
    import ctypes
    ctypes.CDLL(None).prctl(1, signal.SIGTERM)
    if os.getppid() != parent_pid:
        return
    private = Path(job["episode_private"])
    session = None
    with (private / "worker.log").open("w", buffering=1) as log:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        try:
            from topogym.agent_bridge.session import Session
            from .runtime import VisualAdapter
            from .initial import audit_initial
            from .suite import load_preset, resolve
            from .media import publish_segment
            preset = load_preset(job["preset"])
            factory = lambda assets: VisualAdapter(resolve(preset["factory"])(assets, **preset["kwargs"]))
            session = Session(factory, private / "execution", mode="manual",
                              max_steps=job["max_steps"], allow_internet=False)
            adapter = session.adapter.adapter
            cameras, dt = session.description["cameras"], session.description["control_dt_s"]
            public = Path(job["episode_public"])

            def publish(index, manifest):
                return publish_segment(session.root, public, manifest, index, cameras, dt,
                                       samples=job["samples_per_camera"])

            initial = audit_initial(session, preset, private, job.get("expected_initial"))
            latest = publish(0, "initial/manifest.json")
            connection.send(dict(ok=True, data=dict(task=session.description, audit=initial, media=latest,
                state=session.state, tick=0, segments=0,
                physics_qualified=bool(adapter.describe().get("physics_qualified", False)),
                simulator=getattr(adapter, "simulator_spec", {}))))
            while True:
                request = connection.recv()
                method, params = request["method"], request.get("params", {})
                if method == "close":
                    break
                try:
                    if method == "step":
                        session.max_steps = request["max_steps"]
                        response = session.submit(request_id=request["request_id"],
                            expected_segment=len(session.segments)+1,
                            code="env.step(" + repr(params["action"]) + ", steps=" + str(params["steps"]) + ")")
                        latest = publish(response["segment"], response["manifest"])
                        # Preserve measured partial execution even if a controller
                        # or camera failed after advancing physics. Never expose
                        # raw simulator exceptions through the RGB endpoint.
                        data = dict(media=latest, state=session.state, tick=session.tick, segments=len(session.segments),
                                    execution_error=bool(response["error"]))
                    elif method == "get_state":
                        fields = params.get("fields", list(adapter.simulator_spec["state_fields"]))
                        if not isinstance(fields, list) or any(f not in adapter.simulator_spec["state_fields"] for f in fields):
                            raise ValueError("Unsupported state fields; consult capabilities")
                        data = adapter.get_state(fields)
                    elif method == "get_pose":
                        if params.get("frame", "world") != "world" or params.get("entity") not in adapter.simulator_spec.get("pose_entities", []):
                            raise ValueError("Unsupported entity or coordinate frame; consult capabilities")
                        data = adapter.get_pose(params["entity"])
                    else:
                        raise ValueError("Unknown episode method")
                    json.dumps(data, allow_nan=False)
                    connection.send(dict(ok=True, data=data))
                except ValueError as exc:
                    connection.send(dict(ok=False, validation=True, error=str(exc)))
                except Exception:
                    traceback.print_exc(file=log)
                    connection.send(dict(ok=False, error="Simulator operation failed; see private episode log"))
        except Exception:
            traceback.print_exc(file=log)
            try:
                connection.send(dict(ok=False, error="Episode initialization/transport failed; see private episode log"))
            except (BrokenPipeError, EOFError):
                pass
        finally:
            if session:
                adapter = session.adapter.adapter
                try:
                    if hasattr(adapter, "close"):
                        adapter.close()
                    elif hasattr(adapter, "scene"):
                        adapter.scene.destroy()
                except Exception:
                    traceback.print_exc(file=log)
            connection.close()


class Episode:
    def __init__(self, job, index, expected_initial, deadline):
        self.deadline, self.closed = deadline, False
        self.public = Path(job["public"]) / "episodes" / f"episode_{index}"
        self.private = Path(job["private"]) / "episodes" / f"episode_{index}"
        self.public.mkdir(parents=True, exist_ok=False)
        self.private.mkdir(parents=True, exist_ok=False)
        spec = dict(job, episode_public=str(self.public), episode_private=str(self.private),
                    expected_initial=expected_initial)
        ctx = multiprocessing.get_context("spawn")
        self.connection, child = ctx.Pipe()
        self.process = ctx.Process(target=_worker, args=(child, spec, os.getpid()))
        self.process.start()
        child.close()
        try:
            self.initial = self._receive()
        except BaseException:
            self.close()
            raise

    def _receive(self):
        if not self.connection.poll(max(0, self.deadline-time.monotonic())):
            raise TimeoutError("Trial wall-time budget exhausted during simulator operation")
        try:
            response = self.connection.recv()
        except EOFError:
            raise RuntimeError("Simulator worker exited; see private episode log") from None
        if not response["ok"]:
            raise (ValueError if response.get("validation") else RuntimeError)(response["error"])
        return response["data"]

    def call(self, method, params, **kwargs):
        self.connection.send(dict(method=method, params=params, **kwargs))
        return self._receive()

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.process.is_alive():
                self.connection.send(dict(method="close"))
                self.process.join(timeout=min(3, max(0, self.deadline-time.monotonic())))
        except (BrokenPipeError, EOFError, OSError):
            pass
        finally:
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=3)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=3)
            self.connection.close()
