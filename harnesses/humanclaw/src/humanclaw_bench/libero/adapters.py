"""Transport adapters only: upstream agent loops remain their decision owners."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager, nullcontext
import functools
import json
import os
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

from humanclaw_bench.experiments.recorder import event, get_recorder, span
from humanclaw_bench.harnesses.runtime import NativeHarness, JsonProcess, native_command, runtime_identity, child_environment
from humanclaw_bench.harnesses.native_events import NativeEvents
from .protocol import mcp_result


def responses_images(images):
    """Convert the common image blocks to Responses API content."""
    return [{"type": "input_image", "image_url": f"data:{im['mimeType']};base64,{im['data']}"} for im in images]


def run_bare(bridge, meter, config):
    """Ordinary persistent message history; no extra planner, verifier or summary."""
    from openai import OpenAI
    client = OpenAI(base_url=meter.url + "/v1", api_key=meter.bearer,
                    timeout=config.get("request_timeout_seconds", 600), max_retries=2,
                    default_headers={"X-Bench-Context": meter.register_context()})
    messages = [{"role": "user", "content": [{"type": "input_text", "text": bridge.initial_prompt()},
                                             *responses_images(bridge.initial_images())]}]
    tools = [{"type": "function", "name": d["name"], "description": d["description"],
              "parameters": d["inputSchema"]} for d in bridge.definitions]
    while not bridge.done:
        response = client.responses.create(model=config["model"], input=messages, tools=tools,
            reasoning={"effort": config.get("reasoning_effort", "medium")},
            max_output_tokens=config.get("max_output_tokens", 8192))
        messages.extend(item.model_dump(exclude_none=True) for item in response.output)
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            bridge.done, bridge.termination = True, "agent_completed"
            break
        for call in calls:
            try:
                arguments = json.loads(call.arguments)
                result = bridge.call_tool(call.name, arguments)
                public = mcp_result(result)
            except (ValueError, TypeError) as exc:
                public = {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
            messages.append({"type": "function_call_output", "call_id": call.call_id,
                             "output": public["content"][0]["text"]})
            images = [x for x in public["content"] if x["type"] == "image"]
            if images:
                messages.append({"role": "user", "content": responses_images(images)})
            if bridge.done:
                break
    return {"termination_reason": bridge.termination}


def run_native(harness, bridge, meter, config, *, require_isolation=True):
    """Reuse the existing App Server / RPC protocol without changing their loops."""
    recorder = get_recorder()
    directory = recorder.directory.resolve() / "native"
    home, workspace = directory / "home", directory / "workspace"
    directory.mkdir(mode=0o700)
    home.mkdir(mode=0o700)
    workspace.mkdir(mode=0o700)
    (workspace / "PUBLIC_KNOWLEDGE.md").write_text(bridge.backend.knowledge)
    adapter = NativeHarness(harness, config, {"model": config["model"],
        "max_tokens": config.get("max_output_tokens", 8192), "send_max_tokens": True})
    command = native_command(harness, config)
    env = child_environment(home)
    if require_isolation:
        # The launcher must prove the private simulator/data/run paths are absent
        # in its actual mount namespace. An isolated cwd alone is insufficient.
        check = subprocess.run(command[:1] + ["--isolation-check"], cwd=workspace, env=env,
                               capture_output=True, text=True, timeout=30)
        if check.returncode or "private_credentials_and_benchmark_paths_hidden" not in check.stdout:
            raise RuntimeError(f"Native filesystem isolation check failed: {check.stderr[-1000:]}")
        event("isolation.verified", name=harness, data={"stdout": check.stdout})
    identity = runtime_identity(harness, config)
    with span("harness.session", input={"harness": harness}, attributes={"identity": identity,
              "filesystem_isolation_verified": require_isolation}) as operation:
        meter.context = __import__("contextvars").copy_context()
        if harness == "codex":
            adapter._codex_config(home, meter, env)
            # User-authorized benchmark tools in this dedicated MCP server.
            # Newer native Codex versions have an independent MCP permission
            # policy even when shell approval_policy is never.
            with (home / ".codex" / "config.toml").open("a") as handle:
                handle.write('\ndefault_tools_approval_mode = "approve"\n')
        else:
            adapter._pi_config(home, meter, env)
            command += ["--mode", "rpc", "--provider", "humanclaw", "--model", config["model"],
                        "--session-dir", str(directory / "sessions"),
                        "--thinking", config.get("reasoning_effort", "medium")]
        events = NativeEvents(harness, meter.call_names, meter.requested_calls)
        process = JsonProcess(command, workspace, env, events)
        deadline = time.monotonic() + config.get("timeout_seconds", 1800)
        try:
            if harness == "codex":
                adapter._codex(process, meter, bridge, deadline)
            else:
                adapter._wait_for_tools(process, meter, bridge, deadline)
                adapter._pi(process, bridge, deadline)
            if not bridge.done:
                bridge.done, bridge.termination = True, "agent_completed"
            if meter.calls == 0 or not meter.tools_listed.is_set():
                raise RuntimeError("Native process completed without model requests/tool discovery")
            result = {"identity": identity, "termination_reason": bridge.termination}
            operation.set_output(result)
            return result
        finally:
            process.close()
            events.close()


@contextmanager
def robor_instrumentation(meter, bridge, config):
    """Scope reversible transport/trace hooks; do not replace role decisions."""
    import roborsi.embodied.agent_loop as agent_loop
    import roborsi.embodied.agent_loop.rollout as rollout
    from roborsi.embodied.agent_loop import vlm_io
    from roborsi.agents.roles.engineer import Engineer
    from roborsi.agents.roles.planner import Planner
    from roborsi.agents.roles.reviewer import Reviewer
    from roborsi.agents.tools import reviewer as reviewer_tools
    from openai import OpenAI

    def client():
        """Create a metered role client with its current causal trace context."""
        return OpenAI(base_url=meter.url + "/v1", api_key=meter.bearer,
                      timeout=config.get("request_timeout_seconds", 600),
                      default_headers={"X-Bench-Context": meter.register_context()})

    def role_wrapper(original, role):
        """Add a nested role or module span without changing its return value."""
        @functools.wraps(original)
        def wrapped(*args, **kwargs):
            """Execute the original function inside its recorded operation span."""
            with span("roborsi." + role, kind="module") as operation:
                output = original(*args, **kwargs)
                operation.set_output(output)
                return output
        return wrapped

    original_inner = rollout._dispatch_tool
    def inner(state, tool_name, args=None):
        """Record an internal skill dispatch separately from the public tool call."""
        with span("skill." + tool_name, kind="module", input=args,
                  attributes={"internal_subtool": True, "tool_name": tool_name}) as operation:
            output = original_inner(state, tool_name, args)
            operation.set_output(output[0])
            if isinstance(output[0], dict) and output[0].get("ok") is False:
                operation.fail(output[0])
            return output

    original_image = vlm_io._call_vlm_image_impl
    def perception(*args, **kwargs):
        """Trace a tool-internal visual model invocation."""
        with span("perception.vlm", kind="module"):
            return original_image(*args, **kwargs)

    original_review_dispatch = reviewer_tools._dispatch
    def review_dispatch(workspace, name, arguments):
        """Trace native Reviewer evidence-tool requests and outcomes."""
        event("tool.requested", kind="tool", name=name, data={"arguments": arguments, "role": "reviewer"})
        with span(name, kind="tool", input=arguments, attributes={"role": "reviewer"}) as operation:
            result = original_review_dispatch(workspace, name, arguments)
            operation.set_output(result)
            if result[0].get("ok") is False:
                operation.fail(result[0])
            return result

    with ExitStack() as stack:
        stack.enter_context(patch.object(vlm_io, "_openai_client", client))
        stack.enter_context(patch.object(vlm_io, "_call_vlm_image_impl", perception))
        stack.enter_context(patch.object(rollout, "_dispatch_tool", inner))
        stack.enter_context(patch.object(reviewer_tools, "_dispatch", review_dispatch))
        for cls, method, role in ((Planner, "plan", "planner"), (Engineer, "execute", "engineer"), (Reviewer, "review", "reviewer")):
            stack.enter_context(patch.object(cls, method, role_wrapper(getattr(cls, method), role)))
        # Function-entry timing for published perception/solver code. Some
        # plugins were imported while resolving the catalog and hold direct
        # aliases, so replace those aliases too, without changing call results.
        import sys
        from roborsi.embodied.skills.base._lib.libero import _perception, _control
        for module, names, prefix in (
            (_perception, ("vlm_point", "local_vlm_point", "locate_pixel", "locate_by_owlv2",
                           "locate_by_sam3", "sam_mask_at_point", "grasps_at_pixel"), "perception"),
            (_control, ("_request",), "solver.pyroki"),
        ):
            for name in names:
                original = getattr(module, name)
                wrapped = role_wrapper(original, prefix + "." + name)
                for loaded in list(sys.modules.values()):
                    if loaded is None or not str(getattr(loaded, "__name__", "")).startswith(
                            ("roborsi.", "_baseplugin_", "_compound_")):
                        continue
                    for key, val in list(vars(loaded).items()):
                        if val is original:
                            stack.enter_context(patch.object(loaded, key, wrapped))
        for method in ("servo_to", "set_gripper", "execute_previewed_trajectory"):
            stack.enter_context(patch.object(_control.LiberoControl, method,
                role_wrapper(getattr(_control.LiberoControl, method), "motion." + method)))
        yield stack


def run_roborsi(bridge, meter, config):
    """Run the upstream Planner → Engineer → Reviewer coordinator unchanged."""
    import roborsi.embodied.agent_loop as agent_loop
    import roborsi.embodied.agent_loop.rollout as rollout
    import roborsi.channels.core.agent as coordinator
    from roborsi.channels.core.agent import run_atomic_episode
    from roborsi.embodied.agent_loop.messages import _image_version

    class BorrowedBackend:
        """Expose the already initialized environment to the native coordinator."""
        def available(self):
            """Confirm that the shared environment has already passed construction."""
            return True, "prepared shared environment"
        def make_env(self, *_args, **_kwargs):
            """Borrow the environment without taking ownership of its lifetime."""
            return nullcontext(bridge.backend.env)

    class SessionLog:
        """Translate upstream session notifications into original structured events."""
        def append(self, name, **data):
            """Preserve an upstream coordinator notification and its fields."""
            event("roborsi." + name, kind="native", name=name, data=data)

    def dispatch(state, call, timeout_s=600):
        """Route an Engineer tool call through the common execution journal."""
        response = bridge.call_tool(call["tool"], call.get("args") or {})
        state.last_image_path = bridge.backend.context.last_image_path
        result = response.get("result")
        if not isinstance(result, dict):
            result = {"result": result}
        result = {**result, "observation_id": response["observation_id"],
                  "request_status": response["status"], "control_steps": response["control_steps"]}
        if response["error"]:
            result.update(ok=False, error=response["error"])
        return result, bridge.backend.env.take_snapshot()

    # Engineer imports this function inside execute(), rather than storing a
    # module-level alias. Patch the actual import target.
    original_run = rollout.run_rollout
    def run_loop(*args, **kwargs):
        """Supply the common protocol while retaining the upstream rollout loop."""
        kwargs["instruction"] += "\n\nCOMMON TOOL PROTOCOL:\n" + bridge.initial_prompt()
        # The upstream loop still owns turns, reflections and history compression.
        return original_run(*args, **kwargs)

    def specs(*_args, **_kwargs):
        """Convert the single resolved catalog to the upstream function-tool format."""
        return [{"type": "function", "function": {"name": d["name"], "description": d["description"],
                 "parameters": d["inputSchema"]}} for d in bridge.definitions]

    def attach(convo, state):
        """Publish the common observation when the native loop requests fresh images."""
        version = _image_version(state.last_image_path)
        if version is not None and version != state._attached_image_path:
            public = bridge.backend.observe()
            content = [{"type": "text", "text": json.dumps({"observation_id": bridge.observation_id,
                        "proprioception": public["proprioception"]})}]
            content += [{"type": "image_url", "image_url": {"url": f"data:{i['mimeType']};base64,{i['data']}"}} for i in public["images"]]
            convo.append({"role": "user", "content": content})
            state._attached_image_path = version
        return convo

    def save_views(env, workspace, *, initial):
        """Save Planner and Reviewer evidence with the shared camera encoding."""
        import base64
        from .backend import image_block
        out = Path(workspace) / "rollout"
        if not initial:
            rounds = sorted(out.glob("round_*"))
            if not rounds:
                return
            out = rounds[-1]
        out.mkdir(parents=True, exist_ok=True)
        prefix = "initial" if initial else "final"
        for name, rgb in env.take_snapshot().images.items():
            if name in {"head_camera", "wrist"}:
                (out / f"{prefix}_view_{name}.jpg").write_bytes(base64.b64decode(image_block(rgb)["data"]))

    with ExitStack() as stack:
        stack.enter_context(patch.object(agent_loop, "get_backend", lambda _name: BorrowedBackend()))
        # The evaluator already reset and snapshotted this exact initial state.
        stack.enter_context(patch.object(bridge.backend.env, "reset", lambda _seed: bridge.backend.env.take_snapshot()))
        stack.enter_context(patch.object(rollout, "_dispatch_with_timeout", dispatch))
        stack.enter_context(patch.object(rollout, "_build_tool_specs", specs))
        stack.enter_context(patch.object(rollout, "_attach_latest_image", attach))
        stack.enter_context(patch.object(rollout, "run_rollout", run_loop))
        # Shared camera contract, including Planner/Reviewer evidence. Do not
        # silently grant those roles their upstream 512px inspection render.
        stack.enter_context(patch.object(coordinator, "_save_initial_view", lambda env, workspace: save_views(env, workspace, initial=True)))
        stack.enter_context(patch.object(coordinator, "_save_round_view", lambda env, workspace: save_views(env, workspace, initial=False)))
        result = run_atomic_episode(text=bridge.backend.instruction, atomic="libero_pick_place",
            seed=bridge.backend.seed, sess=SessionLog(), target_chat_id=None, channel=None, ctx=None,
            tool_budget=bridge.max_calls, backend_name="libero-pro", sim_task=bridge.backend.task,
            planner_model="openai/" + config["model"], engineer_model="openai/" + config["model"],
            reviewer_model="openai/" + config["model"], return_details=True)
        bridge.done = True
        if bridge.termination == "running":
            bridge.termination = "roborsi_completed"
        return {"termination_reason": bridge.termination, "upstream_result": result}
