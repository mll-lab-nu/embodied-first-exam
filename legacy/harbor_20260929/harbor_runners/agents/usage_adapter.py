"""Thin Harbor lifecycle wrapper for a shared pipeline and agent launch adapter."""
import asyncio
import json
from pathlib import Path

from harbor.agents.base import BaseAgent

from topogym.agents.usage import UsagePipeline
from topogym.agents.usage.pipeline import GatewaySource
from topogym.agents.usage.store import atomic_json
from harbor_runners.endpoints import credential_resolver, freeze_routes, routes_from_frozen
from harbor_runners.agents.opencode import create_delegate
from harbor_runners.supervisor import publish_usage, root_python, stop_trial
from harbor_runners.usage_bridge import require_capabilities


class RunEnvironment:
    """Block native adapter cleanup from spawning new agent work after stop."""
    def __init__(self, environment, service, gateway):
        self._environment, self._service, self._gateway = environment, service, gateway

    def __getattr__(self, name):
        return getattr(self._environment, name)

    async def exec(self, *args, **kwargs):
        if self._service.stopped.is_set() or self._gateway.closing.is_set():
            raise RuntimeError("Trial model and execution admission is closed")
        return await self._environment.exec(*args, **kwargs)


class UsageAgent(BaseAgent):
    def __init__(self, *, connection, usage, sockets, **kwargs):
        super().__init__(**kwargs)
        require_capabilities(connection, usage)
        self.connection = connection
        self.endpoints, self.binding = freeze_routes(connection)
        self.usage, self.sockets = usage, Path(sockets)
        self.delegate = None
        self._constructor = kwargs

    @staticmethod
    def name():
        return "topogym-budgeted"

    def version(self):
        return self.delegate.version() if self.delegate else "1"

    def _new_delegate(self, token=None, url=None, *, bindings=None):
        if bindings is not None:
            token, url = bindings["primary"]["token"], bindings["primary"]["url"]
        return create_delegate(self.connection, self._constructor, token=token, url=url)

    async def setup(self, environment):
        self.delegate = self._new_delegate("unavailable-during-setup", "http://127.0.0.1:1")
        await self.delegate.setup(environment)

    def _resolved_routes(self):
        require_capabilities(self.connection, self.usage)
        return routes_from_frozen(self.endpoints, self.binding)

    async def _start_relay(self, environment, name, binding, *, management):
        socket_name = Path(binding["socket_path"]).name
        argv = ['python', '-m', 'topogym.agents.usage.relay', '--socket',
                '/run/topogym-usage/' + socket_name, '--ready', '/trial/usage-relay-' + name + '.json']
        if management:
            argv += ['--token', binding['token'], '--budget-file', '/rollout/budget.json']
        relay = await root_python(environment, f"""import json,subprocess,time
from pathlib import Path
argv={argv!r}
ready=Path(argv[argv.index('--ready')+1])
ready.unlink(missing_ok=True)
p=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
 stderr=subprocess.DEVNULL,start_new_session=True)
for _ in range(100):
 if ready.exists():
  print(json.dumps(dict(json.loads(ready.read_text()),pid=p.pid)));break
 if p.poll() is not None: raise RuntimeError('Usage relay exited')
 time.sleep(.02)
else: p.kill();raise TimeoutError('Usage relay readiness timeout')
""")
        info = json.loads(relay.stdout)
        return info["pid"], dict(binding, url=f"http://127.0.0.1:{info['port']}")

    async def run(self, instruction, environment, context):
        from harbor.models.task.config import NetworkMode
        if environment.network_policy.network_mode != NetworkMode.NO_NETWORK:
            raise ValueError("Budgeted agent requires Harbor no-network agent phase")
        identity = self.logs_dir.parent.name
        root = self.logs_dir.parent / "usage"
        pipeline = UsagePipeline(root, scope_id=identity, settings=self.usage, source=GatewaySource(self.sockets))
        service = pipeline.service
        task, monitor, health = None, None, None
        relay_pids = []
        interrupted, stopped_trial = False, False
        loop = asyncio.get_running_loop()
        notice = asyncio.Event()
        # A committed receipt wakes the asyncio lifecycle immediately. The
        # watchdog interval only applies to out-of-process policy/health changes.
        def wake():
            if not loop.is_closed():
                loop.call_soon_threadsafe(notice.set)
        service.subscribe_stop(wake)

        async def enforce_stop(snapshot):
            nonlocal stopped_trial
            pipeline.cancel_requests()
            timings = await stop_trial(environment, snapshot, grace_ms=self.usage["stop_grace_ms"])
            atomic_json(root / "stop.json", timings)
            stopped_trial = True
            if task and not task.done():
                task.cancel()
                _, pending = await asyncio.wait({task}, timeout=self.usage["stop_grace_ms"] / 1000)
                if pending:
                    await asyncio.wait_for(environment.stop(delete=False), timeout=20)
                    timings.update(forced_environment_stop=True, evidence_complete=False)
                    atomic_json(root / "stop.json", timings)

        try:
            routes = self._resolved_routes()
            local = pipeline.start(routes, credential_resolver)
            public_binding = dict(self.binding, endpoints=self.endpoints["endpoints"],
                                  agent_version=self.delegate.version())
            atomic_json(root / "binding.json", public_binding)
            bindings = {}
            for position, (name, binding) in enumerate(local.items()):
                pid, bindings[name] = await self._start_relay(environment, name, binding, management=position == 0)
                relay_pids.append(pid)
            old_version = self.delegate.version()
            self.delegate = self._new_delegate(bindings=bindings)
            self.delegate._version = old_version
            await publish_usage(environment, service.ledger.snapshot())

            async def watch_relays():
                while not pipeline.closing.is_set():
                    await asyncio.sleep(1)
                    if pipeline.closing.is_set():
                        return
                    try:
                        await root_python(environment,
                            f"import os\nfor pid in {relay_pids!r}:\n if pid > 0: os.kill(pid,0)", timeout=2)
                    except Exception:
                        service.fail("gateway_failed")
                        return

            task = asyncio.create_task(self.delegate.run(instruction, RunEnvironment(environment, service, pipeline), context))
            monitor = asyncio.create_task(notice.wait())
            health = asyncio.create_task(watch_relays())
            await asyncio.wait({task, monitor}, return_when=asyncio.FIRST_COMPLETED)
            if service.error:
                service.fail("gateway_failed")
            if service.stopped.is_set():
                await enforce_stop(service.ledger.snapshot())
            else:
                await task
            snapshot = await asyncio.to_thread(pipeline.finalize)
            if snapshot["stop"] and not stopped_trial:
                await enforce_stop(snapshot)
            context.n_input_tokens = snapshot["input_tokens"]
            context.n_output_tokens = snapshot["output_tokens"]
            # Harbor runs its native verifier, emitting reward=0 from the latched
            # failure. Raising a budget exception here would skip verification.
        except BaseException:
            interrupted = True
            snapshot = service.ledger.snapshot()
            if not snapshot["closed"]:
                snapshot = service.fail("agent_interrupted")
            pipeline.cancel_requests()
            if not stopped_trial:
                try:
                    await enforce_stop(snapshot)
                except Exception:
                    pass
            raise
        finally:
            for future in (task, monitor, health):
                if future and not future.done():
                    future.cancel()
            pending_tasks = {t for t in (task, monitor, health) if t}
            if pending_tasks:
                done, pending = await asyncio.wait(pending_tasks, timeout=2)
                for future in done:
                    if not future.cancelled():
                        future.exception()
                for future in pending:
                    future.add_done_callback(lambda completed: None if completed.cancelled() else completed.exception())
            close_error = None
            try:
                snapshot = await asyncio.to_thread(pipeline.close)
            except Exception as error:
                close_error = error
                snapshot = service.ledger.snapshot()
                if not snapshot["stop"]:
                    snapshot = service.fail("gateway_failed")
            if snapshot["stop"] and not stopped_trial:
                try:
                    await enforce_stop(snapshot)
                except Exception:
                    if not interrupted and close_error is None:
                        close_error = RuntimeError("Trial shutdown could not be confirmed")
            for pid in relay_pids:
                if pid > 0:
                    try:
                        await root_python(environment, f"import os,signal; os.kill({pid},signal.SIGTERM)")
                    except Exception:
                        pass
            try:
                await publish_usage(environment, snapshot)
                await environment.upload_file(root / "events.jsonl", "/trial/rollout/usage_events.jsonl")
                if (root / "binding.json").exists():
                    await environment.upload_file(root / "binding.json", "/trial/rollout/usage_binding.json")
            except Exception:
                if not interrupted:
                    raise
            if close_error is not None and not interrupted:
                raise close_error

    def populate_context_post_run(self, context):
        if self.delegate:
            self.delegate.populate_context_post_run(context)
        path = self.logs_dir.parent / "usage/snapshot.json"
        if path.exists():
            snapshot = json.loads(path.read_text())
            context.n_input_tokens = snapshot["input_tokens"]
            context.n_output_tokens = snapshot["output_tokens"]
