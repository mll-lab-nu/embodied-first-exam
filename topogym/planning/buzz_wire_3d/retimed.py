"""oraclefix2: Jianwen's compiled Buzz joint rows re-timed to fewer rows, with a measured wand-wire clearance guard.

The compiled medium/hard rows creep along the wire (about 2 mrad per row in the traverse, 29.5k / 43.6k rows in all).
``RetimedJointPolicy`` replays the same joint path faster by path-parameter resampling: within a segment of source rows
the source index advances ``factor`` rows per control step (fractional positions interpolate the joint targets; the
gripper keeps the value of the source row reached), outside every segment one row per step. Pauses inside a segment
shrink by the same factor.

Every row is checked against the wand-wire clearance measured from privileged state (the wand's FCL hull against the
wire's metal pieces, as ``BuzzIK.wand_clearance`` plans it): below ``slow_m`` the source advances one row per step
(Jianwen's own timing) until the clearance is back above ``fast_m``; below ``hold_m`` the targets hold so the arm
catches up with them, for at most ``max_hold_rows`` steps per event. The robot-wire guard of CompiledJointPolicy stays.
Fast rows still go through the caller's standard-rate limiter."""
import numpy as np
from scipy.spatial.transform import Rotation


def expand(document):
    """Forward-filled per-row targets: arm joints (n, 7) and gripper (n,). Rows before the first joint (gripper)
    target hold the robot's home targets; they take the first given target here and are only ever replayed as
    recorded (re-timed segments must start after both targets are set)."""
    actions = document["actions"]
    arm, grip = np.full((len(actions), 7), np.nan), np.full(len(actions), np.nan)
    q, g = None, None
    for index, action in enumerate(actions):
        command = action.get("arm") or {}
        if "joint_position_rad" in command:
            q = np.asarray(command["joint_position_rad"], dtype=float)
        if "gripper_position_rad" in command:
            g = float(command["gripper_position_rad"])
        if q is not None:
            arm[index] = q
        if g is not None:
            grip[index] = g
    first_q = int(np.argmax(~np.isnan(arm[:, 0])))
    first_g = int(np.argmax(~np.isnan(grip)))
    if np.isnan(arm[first_q, 0]) or np.isnan(grip[first_g]):
        raise ValueError("Compiled rows never set the arm or gripper targets")
    arm[:first_q], grip[:first_g] = arm[first_q], grip[first_g]
    return arm, grip, max(first_q, first_g)


class RetimedJointPolicy:
    def __init__(self, document, *, segments=(), start=0, stop=None, clearance=None, fast_m=.002, slow_m=.001,
                 hold_m=.0005, max_hold_rows=40):
        if document["schema"] != "buzz_compiled_joint_policy_v1":
            raise ValueError("Unknown compiled policy format")
        self.document = document
        self.arm, self.grip, first = expand(document)
        self.start = int(start)
        self.count = len(self.arm) if stop is None else int(stop)
        self.segments = [(int(a), int(b), float(f)) for a, b, f in segments]
        if any(not (first < a < b <= len(self.arm)) or not 1. <= f <= 8. for a, b, f in self.segments):
            raise ValueError("Re-timing segments must lie in the compiled rows with factors from 1 to 8")
        if not 0 <= self.start < self.count <= len(self.arm):
            raise ValueError("Re-timed replay must start before it stops")
        if not 0. <= hold_m <= slow_m <= fast_m:
            raise ValueError("Clearance thresholds must satisfy hold <= slow <= fast")
        self.clearance = clearance          # callable(observation) -> metres, or None for no guard
        self.fast_m, self.slow_m, self.hold_m, self.max_hold_rows = fast_m, slow_m, hold_m, int(max_hold_rows)
        self.source = None                  # the source position of the last emitted row
        self.slow = False
        self.held = 0
        self.phase, self.tracking = "retimed_joint_actions", {}
        self.log = []                       # (source position, step, clearance) per emitted row
        self.minimum_clearance_m = np.inf
        self.events = dict(slowed=0, holds=0, held_rows=0)

    def initialize(self, context):
        if context["action_spec"]["mode"] != "JOINT_ABS":
            raise ValueError("Re-timed policy requires JOINT_ABS")
        if abs(context["timing_spec"]["control_dt_s"] - self.document["control_dt_s"]) > 1e-12:
            raise ValueError("Compiled action timing differs")
        # as CompiledJointPolicy (oraclefix 13): targets stay 1 urad inside the public limits
        self.joint_limits = {name: [(float(lo) + 1e-6, float(hi) - 1e-6) for lo, hi in group["joint_limits_rad"]]
                             for name, group in context["action_spec"].get("groups", {}).items()}

    def factor_at(self, source):
        for a, b, f in self.segments:
            if a <= source < b:
                return f
        return 1.

    def act(self, observation):
        events = observation["privileged"]["world"]["contact_events"]["events"]
        if any(e["touching"] and {e["role_a"], e["role_b"]} == {"robot", "wire_metal"} for e in events):
            raise RuntimeError("Robot touched the wire")
        gap = float(self.clearance(observation)) if self.clearance is not None else np.inf
        self.minimum_clearance_m = min(self.minimum_clearance_m, gap)
        if self.source is None:
            source, step = float(self.start), 1.
        else:
            step = self.factor_at(self.source)
            if step > 1.:
                # the guard acts only where the rows are re-timed; elsewhere Jianwen's rows run unchanged
                if gap < self.slow_m and not self.slow:
                    self.slow = True
                    self.events["slowed"] += 1
                elif self.slow and gap >= self.fast_m:
                    self.slow = False
                if self.slow:
                    step = 1.
                if gap < self.hold_m and self.held < self.max_hold_rows:
                    self.events["holds"] += self.held == 0
                    self.held += 1
                    self.events["held_rows"] += 1
                    step = 0.
                elif gap >= self.hold_m:
                    self.held = 0
            source = self.source + step
        if source > self.count - 1 + 1e-9:
            return None
        self.source = source
        self.log.append((source, step, gap))
        self.tracking = dict(source_row=source, step=step, clearance_m=gap)
        low = int(np.floor(source + 1e-9))
        if step == 1. and abs(source - low) < 1e-9:
            action = self.document["actions"][low]       # consecutive source rows: Jianwen's row as recorded
        else:
            high = min(low + 1, len(self.arm) - 1)
            q = self.arm[low] + (source - low) * (self.arm[high] - self.arm[low])
            action = {"arm": {"joint_position_rad": q.tolist(), "gripper_position_rad": float(self.grip[low])}}
        limits = getattr(self, "joint_limits", {})
        return {name: (dict(command, joint_position_rad=[min(max(float(v), lo), hi) for v, (lo, hi) in
                                                         zip(command["joint_position_rad"], limits[name])])
                       if isinstance(command, dict) and "joint_position_rad" in command and name in limits
                       else command) for name, command in action.items()}


def wand_clearance_guard(env):
    """A callable(observation) -> metres: the measured wand's distance to the wire's metal pieces."""
    from .kinematics import BuzzIK
    kin = BuzzIK(env)

    def gap(observation):
        body = observation["privileged"]["world"]["bodies"]["wand"]
        r = Rotation.from_quat(np.asarray(body["quaternion_wxyz"], dtype=float)[[1, 2, 3, 0]])
        return kin.wand_clearance((np.asarray(body["position_m"], dtype=float), r), wire_only=True)
    return gap


def run_retimed(session, document, retime, *, request_id, submission_hash):
    """Jianwen's compiled rows re-timed (``retime["segments"]``) under the clearance guard (``retime["guard"]``), every
    row through the standard-rate limiter. ``retime["insert"]`` = {"at": source row, "instructions": [...]} runs a
    BuzzWirePolicy script when the replay reaches that source row (medium: lower the held wand before the release);
    the rows after it run unless ``retime["stop"]`` (default: all rows) ends the replay there."""
    from topogym.planning.standard_rate import rate_limited_runner
    from .kinematics import CheckedJointPolicy
    from .policy import BuzzWirePolicy
    from .recipes import script
    env = session.env
    guard = wand_clearance_guard(env)
    guard_args = dict(retime.get("guard") or {})
    insert = retime.get("insert")
    at = None if insert is None else int(insert["at"])
    parts = []

    def run(name, policy):
        runner = rate_limited_runner(session)
        result = runner.run_policy(request_id=f"{request_id}-{name}", policy=policy, submission_hash=submission_hash,
                                   state_fields=("world",))
        part = dict(name=name, result=result, limiter=runner.rate_limiter.report())
        if isinstance(policy, RetimedJointPolicy):
            part.update(rows=len(policy.log), last_source_row=policy.source, guard_events=dict(policy.events),
                        minimum_clearance_m=policy.minimum_clearance_m)
        parts.append(part)
        return session.episode_done or session.episode_end is not None

    segments = retime.get("segments", ())
    if not run("rows", RetimedJointPolicy(document, segments=segments, stop=at, clearance=guard, **guard_args)) \
            and insert is not None:
        policy = BuzzWirePolicy(route=env._task.route, origin=env._task.origin, **script(insert["instructions"]))
        stop = retime.get("stop")
        if not run("insert", CheckedJointPolicy(policy, env._robot)) and (stop is None or int(stop) > at):
            run("rows_after_insert", RetimedJointPolicy(document, segments=segments, start=at, stop=stop,
                                                        clearance=guard, **guard_args))
    return dict(reason=parts[-1]["result"]["reason"], control_steps=sum(p["result"]["control_steps"] for p in parts),
                physics_steps=sum(p["result"]["physics_steps"] for p in parts), task_success=bool(session.success()),
                minimum_clearance_m=min(p.get("minimum_clearance_m", np.inf) for p in parts), parts=parts)
