"""CPU contracts: nested attribution, native stalls and durable failure windows."""
import ctypes
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from .profiling import Profiler, TimingBook
from .inspection import EventWindows
from .supervisor import Supervisor
from .contracts import OperationTimeout


def blocked_worker(pipe, cancel, config, output, session_id, kind):
    os.setsid()
    pipe.send(dict(kind="ready", progress=dict(stage="idle", state_ref={"state_id": 7})))
    p = Profiler(pipe.send, lambda: dict(operation_id="blocked"))
    request = pipe.recv()
    # Commit a real test event before entering a native call holding the GIL.
    from .evidence import Evidence
    evidence = Evidence(output, session_id)
    events = EventWindows(evidence.event, durable_events=True)
    events.watch(["always"], before_steps=1, after_steps=2)
    events.push(dict(physics_step=7))
    pipe.send(dict(kind="control_sample", sample=dict(physics_step=7)))
    with p.span("physics_tick", target_physics_step=8):
        with p.span("ipc_native_advance", target_native_frame=29):
            native = ctypes.PyDLL(None)
            native.sleep.argtypes = [ctypes.c_uint]
            native.sleep(30)


class ProfilingTests(unittest.TestCase):
    def test_fem_volume_does_not_break_rigid_contact_summary(self):
        from types import SimpleNamespace
        from .inspection import contact_summary
        values = contact_summary(dict(physics_step=1, contacts={}),
                                 dict(rope=SimpleNamespace(material_coordinates=[])))
        self.assertEqual(values["contacts"], [])
        self.assertIn("no IPC", values["coverage"])

    def test_nested_accounting_does_not_double_count(self):
        book = TimingBook()
        for message in [
            dict(kind="span_begin", span=dict(span_id=1, parent_id=None, stage="step", started=10., operation_id="x", metadata={})),
            dict(kind="span_begin", span=dict(span_id=2, parent_id=1, stage="solver", started=11., operation_id="x", metadata={})),
            dict(kind="span_end", span=dict(span_id=2, ended=14., failed=False)),
            dict(kind="span_end", span=dict(span_id=1, ended=15., failed=False)),
        ]:
            book.accept(message)
        costs = book.snapshot()["costs"]
        self.assertEqual(costs["step"]["seconds"], 5.)
        self.assertEqual(costs["step"]["self_seconds"], 2.)
        self.assertEqual(costs["solver"]["self_seconds"], 3.)
        self.assertFalse(book.progress()["active_spans"])

    def test_nested_progress_does_not_extend_tick_deadline(self):
        book = TimingBook()
        book.accept(dict(kind="span_begin", span=dict(span_id=1, parent_id=None, stage="physics_tick", started=10., metadata={})))
        book.accept(dict(kind="span_begin", span=dict(span_id=2, parent_id=1, stage="retrieve", started=14., metadata={})))
        self.assertIsNotNone(book.expired_step(4., now=15.))

    def test_native_advance_during_build_is_also_bounded(self):
        book = TimingBook()
        book.accept(dict(kind="span_begin", span=dict(span_id=1, parent_id=None,
            stage="ipc_native_advance", started=10., metadata=dict(target_native_frame=1))))
        self.assertIsNotNone(book.expired_step(4., now=15.))

    def test_native_return_without_valid_state_is_not_completed_progress(self):
        book = TimingBook()
        book.accept(dict(kind="span_begin", span=dict(span_id=1, parent_id=None,
            stage="ipc_native_advance", started=10., metadata=dict(target_native_frame=3))))
        book.accept(dict(kind="span_end", span=dict(span_id=1, ended=11., failed=False,
            metadata=dict(native_frame=3, native_valid=False))))
        self.assertIsNone(book.last_completed_native_frame)

    def test_wrapping_restores_inherited_and_class_methods(self):
        class Base:
            def method(self, value):
                return value+1
            @classmethod
            def create(cls):
                return cls()
        class Child(Base):
            pass
        messages = []
        p = Profiler(messages.append, lambda: {})
        p.wrap(Child, "method", "method")
        p.wrap(Child, "create", "create")
        self.assertEqual(Child.create().method(3), 4)
        p.close()
        self.assertNotIn("method", vars(Child))
        self.assertNotIn("create", vars(Child))
        self.assertEqual([m["kind"] for m in messages], ["span_begin", "span_end"]*2)

    def test_exception_is_unchanged_and_span_is_sealed(self):
        events = []
        p = Profiler(events.append, lambda: {})
        with self.assertRaisesRegex(ValueError, "bad"):
            with p.span("test"):
                raise ValueError("bad")
        self.assertTrue(events[-1]["span"]["failed"])
        self.assertFalse(p.stack)

    def test_trigger_is_emitted_before_post_window_and_carries_identity(self):
        events = []
        windows = EventWindows(lambda kind, **row: events.append(dict(kind=kind, **row)), durable_events=True)
        windows.watch(["tracking_error"], before_steps=2, after_steps=2)
        windows.push(dict(physics_step=1, maximum_joint_tracking_error_rad=0.))
        windows.push(dict(physics_step=2, maximum_joint_tracking_error_rad=.1))
        self.assertEqual(events[0]["kind"], "event_window_triggered")
        self.assertEqual(events[0]["before"][0]["physics_step"], 1)
        windows.push(dict(physics_step=3, maximum_joint_tracking_error_rad=0.))
        self.assertEqual(events[1]["kind"], "event_window_progress")
        windows.reset("rewind")
        self.assertEqual(events[-1]["kind"], "event_window_incomplete")

    def test_native_stall_keeps_status_timing_and_trigger(self):
        with tempfile.TemporaryDirectory() as folder:
            supervisor = Supervisor({}, Path(folder)/"run", kind="geometry", worker_target=blocked_worker,
                budgets=dict(startup_s=10, operation_s=20, policy_s=20, physics_step_s=.25))
            try:
                op = supervisor.submit("run_policy", request_id="blocked")
                with self.assertRaises(OperationTimeout):
                    supervisor.wait(op)
                deadline = time.monotonic()+3
                while not (supervisor.output/"failure_window.json").exists() and time.monotonic()<deadline:
                    time.sleep(.01)
                self.assertFalse(supervisor.status()["worker_alive"])
                self.assertIn("physics_step_s", supervisor.status(op)["error"]["message"])
                self.assertEqual(supervisor.timings()["incomplete_spans"][-1]["stage"], "ipc_native_advance")
                failure = json.loads((supervisor.output/"failure_window.json").read_text())
                self.assertEqual(failure["pending_windows"][0]["trigger"]["physics_step"], 7)
                self.assertEqual(failure["before"][0]["physics_step"], 7)
                self.assertFalse(failure["after_available"])
            finally:
                supervisor.close()


if __name__ == "__main__":
    unittest.main()
