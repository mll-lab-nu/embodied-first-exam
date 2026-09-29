"""A single continuous environment lifetime, with sanitized video feedback."""
import copy
import json
from pathlib import Path
import time
import traceback

from topogym.agent_bridge.session import Session, write_json
from .agents import create_agent, validate_decision
from .media import publish_segment
from .initial import audit_initial
from .suite import load_preset, resolve
from .token_budget import TokenBudgetExhausted


class VisualAdapter:
    """Both conditions get RGB only as live state; privilege is STATIC knowledge."""
    def __init__(self, adapter):
        self.adapter = adapter

    def describe(self):
        description = self.adapter.describe()
        allowed = ("task_id", "task_goal", "objective", "cameras", "control_dt_s", "physics_substeps",
                   "robot", "world", "camera_calibration", "action_schema", "action_semantics", "example_code")
        result = {k: copy.deepcopy(description[k]) for k in allowed if k in description}
        if len(result["cameras"]) not in (3, 4):
            raise ValueError("Rollout protocol requires exactly three or four cameras")
        return result

    def observe(self):
        return {}

    def render(self):
        return self.adapter.render()

    def validate_action(self, action):
        return self.adapter.validate_action(action)

    def step(self, action):
        return self.adapter.step(action)

    def evaluate(self):
        return self.adapter.evaluate()


def prompt(public, session, mode, history, images, error, remaining_steps, extra, budget=None):
    s = session.snapshot()
    return (
        "You are solving a TopoGym task by writing scripted policies. The simulation is paused while you reason.\n"
        "Use English for all natural-language responses, including decision.reason.\n"
        + ((budget.notice() + "\nRead token_budget.json for the latest settled usage and in-flight reservation.\n")
           if budget else "") +
        f"Input condition: {mode}. Live environment state is RGB only; obs is an empty dict.\n"
        "Task goals and generic robot/action/camera documentation are shared in both conditions. "
        "Only rgb_privileged includes privileged.json: frozen scene configuration and construction knowledge. "
        "It does not grant access to reference solutions, other attempts or live simulator internals.\n"
        "Your only task data is this repeat's working directory. Do not read parent directories, repository source, "
        "other repeats, demos, private evaluator files or hidden state. Do not modify input artifacts. "
        "You may write your own analysis files in scratch/ and use general planning/image-analysis tools.\n"
        "Directory: segment_0.mp4 is the static initial state (zero physics steps); segment_N.mp4 is a 2x2 "
        "mosaic of the Nth action segment. Camera order is row-major as listed in task_spec.json. "
        "<camera>/segment_N.mp4 stores each synchronized view. segment_N.json maps every video frame to "
        "tick/time and frames/segment_N/<camera>/000000.png, etc. inputs/ contains frames decoded from MP4. "
        "All completed history remains available. Read JSON with json.load; extract any video frame with "
        "ffmpeg -i <camera>/segment_N.mp4 -vf 'select=eq(n\\,FRAME_INDEX)' -frames:v 1 scratch/frame.png; "
        "then use your image viewer. Merely reading a filename does not view its pixels.\n"
        "Return JSON {kind, code, paths, reason}. kind=segment submits code; kind=inspect requests 1..16 "
        "saved PNG/segment JSON paths without physics; kind=stop ends this attempt. "
        "Use empty code/reason strings and an empty paths list when unused. Only the evaluator declares success.\n"
        "Submitted code uses assignments, for/range, arithmetic, lists/dicts/indexing and "
        "env.step(action, steps=N). You choose N and may issue multiple commands per segment. "
        "No imports, functions, while loops or simulator access in the submitted script. "
        "Do arbitrary planning in your own scratch code, then submit this action subset. "
        "No reset, undo or scene resampling; actions persist into the next segment.\n"
        f"Next segment: {s['next_segment']}; maximum steps now: {min(session.max_steps, remaining_steps)}; "
        f"total remaining control steps: {remaining_steps}.\n"
        f"Task/action documentation: {json.dumps(s['task'], ensure_ascii=False)}\n"
        f"Completed segment indices: {json.dumps(history)}\n"
        f"Attached RGB paths in image order: {json.dumps(images)}\n"
        f"Last validation feedback: {error or 'none'}\n"
        f"Requested JSON documents: {json.dumps(extra, ensure_ascii=False)}\n"
        + (("Frozen privileged knowledge: " + (public / "privileged.json").read_text() + "\n")
           if mode == "rgb_privileged" else "")
    )


def inspect_paths(public, paths):
    images, documents = [], {}
    for relative in paths:
        target = (public / relative).resolve()
        if not target.is_relative_to(public):
            raise ValueError("Only this repeat's published artifacts may be inspected")
        name = target.relative_to(public).as_posix()
        is_frame = target.suffix == ".png" and target.parts[len(public.parts)] in ("frames", "inputs")
        is_manifest = target.parent == public and target.name.startswith("segment_") and target.suffix == ".json"
        if not target.is_file() or not (is_frame or is_manifest):
            raise ValueError("Expected a published PNG or segment JSON")
        if is_frame:
            images.append(name)
        else:
            documents[name] = json.loads(target.read_text())
    return images, documents


def run_repeat(job):
    from .profiles import profile
    selected = profile(job["agent"])
    job = dict(job, agent=dict(job["agent"], mode=selected["access_mode"]))
    if selected["interaction"] == "tools":
        from .tool_runtime import run_tool_repeat
        return run_tool_repeat(job)
    public, private = Path(job["public"]).resolve(), Path(job["private"]).resolve()
    public.mkdir(parents=True, exist_ok=False)
    private.mkdir(parents=True, exist_ok=False)
    (public / "scratch").mkdir()
    mode = job["agent"]["mode"]
    if mode not in ("rgb", "rgb_privileged"):
        raise ValueError("Unknown input condition")
    started = time.monotonic()
    session, agent = None, None
    result = dict(status="pipeline_error", success=False, initial_observation_sha256=None,
        calls=0, segments=0, ticks=0, input_mode=mode, usage=[], usage_complete=True,
        agent_id=job["agent"]["id"], provider=job["agent"]["provider"], repeat=job["repeat"],
        observation_isolation="prompt_policy", physics_qualified=False)
    try:
        preset = load_preset(job["preset"])
        result.update(task_id=preset["task_id"], variant_id=preset["variant_id"], preset_sha256=preset["sha256"])
        wrapped = lambda assets: VisualAdapter(resolve(preset["factory"])(assets, **preset["kwargs"]))
        session = Session(wrapped, private / "episode", mode="manual", max_steps=job["max_steps"], allow_internet=False)
        result["physics_qualified"] = bool(session.adapter.adapter.describe().get("physics_qualified", False))
        write_json(public / "task_spec.json", session.description)
        if mode == "rgb_privileged":
            write_json(public / "privileged.json", preset["knowledge"])
        cameras, dt = session.description["cameras"], session.description["control_dt_s"]
        result.update(audit_initial(session, preset, private, job.get("expected_initial")))
        latest = publish_segment(session.root, public, "initial/manifest.json", 0, cameras, dt,
                                 samples=job["samples_per_camera"])
        agent_config = dict(job["agent"], token_limit=job.get("token_limit", 3_000_000),
                            max_output_tokens=job.get("max_output_tokens", 8192))
        agent = create_agent(agent_config, public, private)
        budget = getattr(agent, "budget", None)
        result["observation_isolation"] = agent.isolation
        history, error, extra = [0], None, {}
        images = [i["path"] for i in latest["model_inputs"]]
        for number in range(1, job["max_calls"]+1):
            if session.state != "ready":
                break
            if len(history)-1 >= job["max_segments"] or session.tick >= job["max_total_steps"]:
                session.finish("Rollout action budget exhausted")
                result["status"] = "limit_reached"
                break
            remaining = job["max_total_steps"]-session.tick
            # Enforce the cumulative budget in preflight, before any action runs.
            session.max_steps = min(job["max_steps"], remaining)
            request = dict(prompt=prompt(public, session, mode, history, images, error, remaining, extra, budget),
                           images=images, public_dir=str(public), call=number)
            write_json(private / f"call_{number}.request.json", request)
            result["calls"] = number
            decision, usage = agent.decide(request, number)
            result["usage"].append(usage)
            result["usage_complete"] &= usage is not None
            write_json(private / f"call_{number}.decision.json", decision)
            error, extra = None, {}
            try:
                decision = validate_decision(decision)
                if decision["kind"] == "stop":
                    session.finish(str(decision.get("reason", "Agent stopped")))
                    result["status"] = "agent_stopped"
                    break
                if decision["kind"] == "inspect":
                    images, extra = inspect_paths(public, decision["paths"])
                    continue
                index = len(history)
                response = session.submit(request_id=f"call-{number}", expected_segment=index, code=decision["code"])
            except ValueError as exc:
                # Rejected code/inspection consumes a call, never a physical tick.
                error = str(exc)
                continue
            (public / f"policy_{index}.py").write_text(decision["code"])
            latest = publish_segment(session.root, public, response["manifest"], index, cameras, dt,
                                     samples=job["samples_per_camera"])
            history.append(index)
            images = [i["path"] for i in latest["model_inputs"]]
        else:
            if session.state == "ready":
                session.finish("Agent call budget exhausted")
                result["status"] = "limit_reached"
        if result["status"] == "pipeline_error":
            result["status"] = "succeeded" if session.state == "succeeded" else "task_failed"
        result.update(success=session.state == "succeeded", reason=session.reason,
                      ticks=session.tick, segments=len(session.segments))
    except TokenBudgetExhausted as exc:
        result.update(status="token_budget_exhausted", success=False, reason=str(exc))
        if session:
            session.finish(str(exc))
            result.update(ticks=session.tick, segments=len(session.segments))
    except Exception as exc:
        result.update(status="pipeline_error", success=False, reason=f"{type(exc).__name__}: {exc}")
        (private / "error.txt").write_text(traceback.format_exc())
        if session:
            session.finish("Rollout pipeline failed; see operator log")
            result.update(ticks=session.tick, segments=len(session.segments))
    finally:
        if agent is not None and hasattr(agent, "close"):
            agent.close()
        # A transport failure may have consumed tokens without returning usage.
        result["usage_complete"] &= len(result["usage"]) == result["calls"]
        budget = getattr(agent, "budget", None)
        result["token_budget"] = budget.snapshot() if budget else None
        if budget:
            result["usage_complete"] = result["token_budget"]["usage_complete"]
        result["success_within_token_budget"] = bool(result["success"] and budget and
            result["usage_complete"] and not result["token_budget"]["over_budget"] and
            not result["token_budget"]["blocked"])
        result["wall_seconds"] = time.monotonic()-started
        result["success_physics_qualified"] = result["success"] and result["physics_qualified"]
        # Full result remains outside the agent's input workspace.
        write_json(private / "result.json", result)
    return result
