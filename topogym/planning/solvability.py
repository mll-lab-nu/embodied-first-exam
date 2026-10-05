"""Owner-side staged qualification, using the existing Env / SegmentRunner.

Path cache entries are geometric candidates. Local windows, including successful
diagnostic branches, never grant a complete solvability proof. A continuous run
from birth (a proof run, or a diagnostic run that never rewound) still needs its
task-specific independent audit.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import math
import time

from topogym.planning.harbor_bridge.callbacks import fingerprint
from topogym.utils.io import sha256_file, to_jsonable, write_json_atomic


IDENTITY_FIELDS = {"task_id", "variation_id", "seed", "instance_id",
                   "config_sha256", "source_sha256", "assets_sha256", "engine_version"}
KINDS = {"transit", "grasp", "interaction", "release", "settle"}


def identity_for(runner, *, owner_sources=()):
    """Bind actual runner metadata and the files defining owner callbacks."""
    import json
    from importlib.metadata import version
    episode = runner.env.episode_metadata
    config = to_jsonable(runner.env.config)
    config.pop("work_dir", None)  # Output location does not change dynamics.
    owners = {str(Path(path).resolve()): sha256_file(path) for path in owner_sources}
    sources = json.loads((runner.root / "source_manifest.json").read_text())
    return dict(task_id=episode["task_id"], variation_id=episode["variation_id"],
                seed=episode["seed"], instance_id=episode["instance_id"],
                config_sha256=fingerprint(config), assets_sha256=fingerprint(episode["asset_sha256"]),
                source_sha256=fingerprint(dict(simulator=sources, owner=owners)),
                engine_version={name: version(name) for name in ("genesis-world", "torch", "numpy")},
                owner_sources=owners)


def validate_identity(identity):
    if not IDENTITY_FIELDS <= identity.keys():
        raise ValueError("Problem identity must bind instance, configuration, sources, assets and engine")
    for name in ("config_sha256", "source_sha256", "assets_sha256"):
        value = identity[name]
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError(f"Invalid SHA-256 field: {name}")
    fingerprint(identity)  # Reject nonfinite/nonserializable identity values.


class PathCache:
    """Exact-input cache for read-only planning, never for physical success."""

    def __init__(self, directory, identity):
        validate_identity(identity)
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.identity = to_jsonable(identity)

    def plan(self, request, measured, build):
        # Require both the full world and robot measurement. This intentionally
        # misses when velocities, passive fingers or contact state have changed.
        if not all(isinstance(measured.get(key), Mapping) and measured[key] for key in ("world", "robot")):
            raise ValueError("Path reuse requires measured world and robot state")
        key = fingerprint(dict(identity=self.identity, request=request, measured=measured))
        path = self.root / (key + ".json")
        started = time.perf_counter()
        if path.exists():
            import json
            record = json.loads(path.read_text())
            if (record["key"] != key or record["scope"] != "read_only_path"
                    or fingerprint(record["plan"]) != record["plan_sha256"]):
                raise ValueError("Changed path-cache entry")
            return record["plan"], dict(cache_hit=True, key=key, wall_s=time.perf_counter()-started)
        result = to_jsonable(build())
        if not isinstance(result, dict) or not result:
            raise ValueError("Planner must return a nonempty path record")
        write_json_atomic(path, dict(key=key, scope="read_only_path", plan=result,
                                     plan_sha256=fingerprint(result)))
        return result, dict(cache_hit=False, key=key, wall_s=time.perf_counter()-started)


@dataclass(frozen=True)
class Stage:
    name: str
    kind: str
    definition: dict
    build_policy: object
    entry: object
    invariant: object
    exit: object
    max_simulation_s: float

    def __post_init__(self):
        if not self.name or self.kind not in KINDS:
            raise ValueError("Stage requires a name and a supported interaction kind")
        if not math.isfinite(self.max_simulation_s) or self.max_simulation_s <= 0:
            raise ValueError("Stage requires a positive finite simulation-time budget")
        if any(not callable(value) for value in (self.build_policy, self.entry, self.invariant, self.exit)):
            raise ValueError("Stage requires explicit policy, entry, invariant and exit callbacks")
        fingerprint(self.definition)


@dataclass(frozen=True)
class Step:
    """One task step: ordered candidate parameters and build(parameters) -> Stage.

    build runs at the step's actual start state (after any rewind) and may plan
    read-only. The built Stage's definition["parameters"], if present, is what a
    later execution needs to rebuild the same choice without searching again.
    """
    name: str
    candidates: tuple
    build: object

    def __post_init__(self):
        if not self.name or not callable(self.build):
            raise ValueError("Step requires a name and a build callback")
        if any(not isinstance(value, Mapping) for value in self.candidates):
            raise ValueError("Step candidates must be parameter mappings")
        fingerprint(list(self.candidates))


def checks(callback, tick):
    values = callback(tick)
    if not isinstance(values, Mapping) or not values:
        raise ValueError("A stage check must return a nonempty named check mapping")
    values = to_jsonable(values)
    if any(not isinstance(name, str) or type(value) is not bool for name, value in values.items()):
        raise ValueError("Stage checks must be named booleans; missing evidence cannot pass")
    return [name for name, passed in values.items() if not passed]


class QualificationWorkflow:
    """Run measured stages in a single live owner; do not implement physics.

    Invariants observe every committed physics tick, including ticks between
    policy decisions. A violation is latched and stops the next control action;
    it cannot be hidden by recovery before a control-decimated observation.
    Independent audit remains mandatory even after native success.
    """

    def __init__(self, runner, output, identity, *, mode="diagnostic", abort_file=None):
        validate_identity(identity)
        if mode not in {"diagnostic", "proof", "session"}:
            raise ValueError("Mode must be diagnostic, proof or session")
        if fingerprint(identity) != fingerprint(identity_for(runner, owner_sources=identity.get("owner_sources", {}))):
            raise ValueError("Workflow identity differs from the actual runner or owner sources")
        self.runner, self.mode = runner, mode
        # Diagnostic only: creating this file fails the running stage at the
        # next physics tick, so run_step can rewind without restarting.
        self.abort_file = Path(abort_file) if abort_file is not None and mode == "diagnostic" else None
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        initial = runner.env.tick_record()
        # The episode birth is state 0 at physics step 0. A Harbor Session restores its frozen birth on a new branch
        # (branch_id 1, state_id 0) before any action; the proof is still continuous from that birth.
        if mode == "proof" and (initial["state"]["physics_step"] != 0 or initial["state"]["state_id"] != 0):
            raise ValueError("A proof execution must start at the fresh episode birth")
        if mode == "session":
            # Harbor restores its bound initial checkpoint before the oracle,
            # creating a nonzero branch without taking a robot action. Keep
            # that identity intact and still forbid progressed/rewound runs.
            session = getattr(runner, "session", None)
            if (session is None or session.env is not runner.env or session.n_steps or session._resets
                    or not session.runtime_binding or not session.instance_exact
                    or initial["state"]["physics_step"] != 0
                    or initial["state"]["state_id"] != session.S0["state_id"]
                    or initial["state"]["episode_id"] != session.S0["episode_id"]):
                raise ValueError("Session stages require the fresh, exactly bound initial checkpoint")
        self.episode = initial["state"]["episode_id"]
        # chain: indices of passed stages on the current history. Rewind
        # truncates the history after its target, so the chain stays linear.
        self.report = dict(schema_version=1, mode=mode, identity=to_jsonable(identity),
                           birth=to_jsonable(initial["state"]), stages=[], rewinds=[], chain=[],
                           status="running", accepted_proof=False)
        self._write()

    def _write(self):
        write_json_atomic(self.output / "workflow.json", self.report)
        selection = [dict(step=row["step"], parameters=row["parameters"],
                          parameters_sha256=fingerprint(row["parameters"]))
                     for row in (self.report["stages"][i] for i in self.report["chain"]) if "step" in row]
        write_json_atomic(self.output / "selection.json", selection)

    def rewind(self, state_ref):
        if self.mode != "diagnostic":
            raise ValueError("Rewind is unavailable in proof mode")
        if state_ref.get("episode_id") != self.episode:
            raise ValueError("Diagnostic rewind must remain in this live episode")
        _, receipt = self.runner.interaction(privileged=True).rewind_to(state_ref)
        self.report["rewinds"].append(dict(target=to_jsonable(state_ref), receipt=to_jsonable(receipt)))
        self.report["chain"] = [i for i in self.report["chain"]
                                if self.report["stages"][i]["end"]["state_id"] <= state_ref["state_id"]]
        self._write()
        return receipt

    def run_step(self, step, candidates=None, wait=None):
        """Try candidates from one start state; in diagnostic mode rewind after each failure.

        When all candidates fail, wait(step, start, tried) may return new
        parameters (diagnostic only); returning None ends the step as failed.
        """
        start = self.runner.env.tick_record()["state"]
        target = {key: start[key] for key in ("episode_id", "state_id")}
        queue = [dict(value) for value in (step.candidates if candidates is None else candidates)]
        tried = []
        while True:
            if not queue:
                parameters = wait(step, to_jsonable(start), tried) if wait and self.mode == "diagnostic" else None
                if parameters is None:
                    raise ValueError(f"Step {step.name} failed with every candidate: {tried}")
                queue.append(dict(parameters))
            parameters = queue.pop(0)
            start = self.runner.env.tick_record()["state"]  # A rewind changes branch_id.
            planning_started = time.perf_counter()
            try:
                stage = step.build(parameters)
                planning_wall_s = time.perf_counter()-planning_started
                if self.runner.env.tick_record()["state"] != start:
                    raise ValueError("Step planning must not advance or rewind the simulator")
                chosen = to_jsonable(stage.definition.get("parameters", parameters))
                record = self.run(stage)
            except Exception as error:
                tried.append(dict(parameters=to_jsonable(parameters), error=str(error),
                                  wall_s=time.perf_counter()-planning_started))
                if self.mode != "diagnostic":
                    raise
                if self.runner.env.tick_record()["state"] != start:
                    self.rewind(target)
                if self.abort_file is not None:
                    self.abort_file.unlink(missing_ok=True)
                continue
            record.update(step=step.name, parameters=chosen, failed_candidates=tried,
                          planning_wall_s=planning_wall_s)
            self._write()
            return record

    def run(self, stage):
        initial = self.runner.env.tick_record()
        if initial["state"]["episode_id"] != self.episode:
            raise ValueError("Workflow episode expired")
        if self.mode != "diagnostic" and (initial["state"]["branch_id"] != self.report["birth"]["branch_id"]
                                      or any(not row["passed"] for row in self.report["stages"])):
            raise ValueError("Failed or rewound proof execution cannot be continued as a proof")
        prior = self.report["stages"][-1].get("end") if self.report["stages"] else self.report["birth"]
        if self.mode != "diagnostic" and to_jsonable(initial["state"]) != prior:
            raise ValueError("Unmonitored steps occurred between proof stages")
        index = len(self.report["stages"])
        record = dict(name=stage.name, kind=stage.kind, attempt=len(self.report["rewinds"]),
                      definition=to_jsonable(stage.definition),
                      start=to_jsonable(initial["state"]), passed=False,
                      checked_physics_ticks=0, violations=[])
        self.report["stages"].append(record)
        started = time.perf_counter()
        violations = record["violations"]
        sequence = [initial["state"]]
        unsubscribe = None

        def monitor(tick):
            state = tick["state"]
            record["checked_physics_ticks"] += 1
            previous = sequence[0]
            sequence[0] = state
            failures = []
            if (state["episode_id"] != self.episode or state["branch_id"] != initial["state"]["branch_id"]
                    or state["parent_state_id"] != previous["state_id"]
                    or state["physics_step"] != previous["physics_step"]+1):
                failures.append("discontinuous_physics_history")
            if state["sim_time_s"]-initial["state"]["sim_time_s"] > stage.max_simulation_s+1e-9:
                failures.append("stage_time_budget")
            if self.abort_file is not None and self.abort_file.exists():
                failures.append("operator_abort")
            # A bad check is latched as a qualification failure, not raised
            # through the engine's state-output callback (which faults Env).
            try:
                failures.extend(checks(stage.invariant, tick))
            except Exception as error:
                failures.append("invalid_invariant: " + str(error))
            if failures and not violations:
                violations.append(dict(state=to_jsonable(state), checks=failures))

        try:
            failed_entry = checks(stage.entry, initial) + checks(stage.invariant, initial)
            if failed_entry:
                raise ValueError("Stage entry rejected: " + ", ".join(failed_entry))
            policy = stage.build_policy(initial)  # Replan from the actual handoff state.
            if self.runner.env.tick_record()["state"] != initial["state"]:
                raise ValueError("Policy construction must not advance or rewind the simulator")

            class GuardedPolicy:
                def initialize(self, context):
                    initialize = getattr(policy, "initialize", None)
                    if initialize is not None:
                        return initialize(context)

                def act(self, observation):
                    if violations:
                        raise RuntimeError("Stage invariant failed: " + str(violations[0]["checks"]))
                    try:
                        return policy.act(observation)
                    except Exception as error:
                        # The segment result only says policy_error; keep why.
                        record["policy_exception"] = repr(error)
                        raise

                def on_segment_end(self, observation, result):
                    callback = getattr(policy, "on_segment_end", None)
                    if callback is not None:
                        return callback(observation, result)

            unsubscribe = self.runner.env.add_state_sink(monitor)
            submission = fingerprint(dict(identity=self.report["identity"], stage=record["definition"],
                                           name=stage.name, kind=stage.kind,
                                           max_simulation_s=stage.max_simulation_s))
            result = self.runner.run_policy(request_id=f"qualification-{index}-{stage.name}",
                policy=GuardedPolicy(), submission_hash=submission, mode="unlimited",
                state_fields=("world",), observation_profile={"rgb_camera_ids": []})
            record["segment_result"] = to_jsonable(result)
            final = self.runner.env.tick_record()
            record["end"] = to_jsonable(final["state"])
            if final["state"]["physics_step"]-initial["state"]["physics_step"] != record["checked_physics_ticks"]:
                raise ValueError("Missing physics-tick checks")
            exit_failures = checks(stage.exit, final)
            if violations or exit_failures or result["reason"] not in {"policy_done", "env_terminal"}:
                raise ValueError(f"Stage failed: {violations or exit_failures or result['reason']}"
                                 + (f" ({record['policy_exception']})" if "policy_exception" in record else ""))
            feedback = result.get("feedback", {})
            if feedback.get("task_outcome") == "failure":
                raise ValueError("Native Task failed during stage")
            record["passed"] = True
            self.report["chain"].append(index)
        except Exception as error:
            record["error"] = str(error)
            self.report["status"] = "stage_failed"
            raise
        finally:
            if unsubscribe is not None:
                unsubscribe()
            record["wall_s"] = time.perf_counter()-started
            self._write()
        return record

    def finish(self):
        stages = [self.report["stages"][i] for i in self.report["chain"]]
        current = to_jsonable(self.runner.env.tick_record()["state"])
        complete = bool(stages) and stages[-1]["end"] == current
        # Birth-to-end without rewinds, physical failures or unmonitored gaps is
        # the same evidence a proof run produces; the independent audit
        # re-checks it. A candidate rejected before any physics tick is allowed.
        birth = self.report["birth"]
        continuous = (complete and not self.report["rewinds"]
                      and all(row["passed"] or not row["checked_physics_ticks"] for row in self.report["stages"])
                      and birth["physics_step"] == 0 and birth["state_id"] == 0
                      and stages[0]["start"] == birth
                      and all(b["start"] == a["end"] for a, b in zip(stages, stages[1:])))
        solved = bool(self.runner.env.is_solved())
        self.report.update(native_task_success=solved, continuous_from_birth=continuous, accepted_proof=False)
        session_continuous = (self.mode == "session" and complete and not self.report["rewinds"]
                              and all(row["passed"] for row in self.report["stages"])
                              and stages[0]["start"] == birth
                              and all(b["start"] == a["end"] for a, b in zip(stages, stages[1:])))
        self.report["continuous_from_frozen_instance"] = session_continuous
        if not complete:
            self.report["status"] = "incomplete"
        elif session_continuous and solved:
            self.report["status"] = "native_success_pending_harbor_verifier"
        elif continuous and solved:
            self.report["status"] = "native_success_pending_independent_audit"
        else:
            self.report["status"] = "local_windows_passed" if self.mode == "diagnostic" else "incomplete"
        self._write()
        return self.report
