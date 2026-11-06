# ruff: noqa: RUF046, RUF059, C408
"""The full-state reference program for badminton at the LOW level (the oracle of the matchlow privileged twin): the
twin's in-loop oracle (builtin_players.SkillReference: the camera-only Reference's decisions, planned with act lead 0,
lowered by the seat's own act skill) with the shuttle's true state in place of the cameras, as the high-level
privileged twins' TruthReference (only the perception block of Reference.act is replaced), and the skill-server
plumbing replaced: each act is lowered in-process by the twin's toolkit-only reference skill (act.py, the twin's
solution/skill/act.py byte for byte) into the low-level traj rows; toss and move as is. The toolkit's files are those of
the public simulator copy on sys.path (sports/badminton/seat/, the twin's /opt/robot)."""

import math
import sys
import tempfile
import time
from pathlib import Path

import act as skill
import builtin_players as bp
import numpy as np


def _seat_dir():
    for p in sys.path:
        d = Path(p or ".") / "sports/badminton/seat"
        if (d / "robot_only.xml").is_file():
            return d.resolve()
    raise RuntimeError("sports/badminton/seat not on sys.path")


def skill_spec(spec, scratch):
    """The twin's in-loop skill spec (the low-level game spec) with the toolkit's /opt/robot paths at the tree's seat/
    (the robot-only model with its meshes from the scene's assets, as the seat image has them)."""
    seat = _seat_dir()
    xml = (seat / "robot_only.xml").read_text().replace(
        'meshdir="assets"', f'meshdir="{(seat.parent / "sim/scene/assets").resolve()}"')
    model = Path(scratch) / "robot_only.xml"
    model.write_text(xml)
    tk = dict(spec.get("toolkit") or {})
    tk["robot_model"] = str(model)
    for name in ("ik_library", "servo_model"):
        if isinstance(tk.get(name), dict) and tk[name].get("file"):
            tk[name] = dict(tk[name], file=str(seat / "lib" / Path(tk[name]["file"]).name))
    return dict(spec, toolkit=tk)


def make_policy(config):
    spec = dict(config["spec"])
    spec.setdefault("cameras", [])
    return Policy(spec, int((spec.get("cfg") or {}).get("seed", 0)))


class Policy:
    """The low level: the reference's high-level decision each view, its act lowered here."""

    def __init__(self, spec, seed):
        self.sk_spec = skill_spec(spec, tempfile.mkdtemp())
        # as SkillReference: the high-level planner with act lead 0 (the lowered rows take effect when it returns)
        self.ref = TruthReference(dict(spec, action_level="high", act=dict(spec.get("act") or {}, lead_steps=0)), "A", seed)
        self.sent = {"act": 0, "toss": 0, "other": 0, "lowered": 0}

    def act(self, view):
        a = self.ref.act(view)
        if not a:
            return None
        self.sent[a["type"] if a["type"] in self.sent else "other"] += 1
        if a["type"] != "act":
            return a  # ready, toss, move: the same command at both levels
        st = view.get("state") or {}
        args = [a["t"], a["pos"], a["normal"], a["vel"]] + ([a["base"]] if a.get("base") is not None else [])
        try:
            out = skill.act(*args, state=st, spec=self.sk_spec)
        except Exception:
            return None  # a failed skill call is a no-op (as in the loop)
        if out:
            self.sent["lowered"] += 1
        return out


class TruthReference(bp.Reference):
    def act(self, view):
        if (view.get("state") or {}).get("phase") == "unit_over":
            return {"type": "ready"}  # the review after a point: carry on (the camera player's service sent it)
        return self.play(view)

    def play(self, view):
        st, ob = view.get("state") or {}, view.get("observation") or {}
        if not self.high or st.get("world") != "running" or st.get("pending_commands"):
            return None
        if st.get("you_serve") and (st.get("serve") or {}).get("phase") in ("waiting", "open", "tossed"):
            return self.serve(st, ob)
        if (
            self.WAIT
            and st.get("ball_state") == "going to the opponent"
            and st.get("t_since_played") is not None
            and float(st["t_since_played"]) >= 0.05
        ):
            # (revision wallclock-11) no automatic return: after its stroke the base goes back to the middle of the court
            key = (st.get("point"), round(int(st.get("step", 0)) * bp.STEP - float(st["t_since_played"]), 2))
            if self.moved != key:
                self.moved = key
                return {"type": "move", "base": self.wait_xy}
        if st.get("ball_state") != "coming to you" or st.get("t_since_played") is None:
            self.flight, self.obs, self.plan, self.sent = None, [], None, None
            return None
        live = "obs_id" in ob
        t_entry = time.monotonic()
        step = int(st.get("step", 0))
        k_obs = float(step)
        if live:
            # the step at the reply, with its phase: the newest frame was taken at its step, obs_age_wall_s ago
            vs, age = ob.get("view_steps") or [], ob.get("obs_age_wall_s")
            if vs and isinstance(age, (int, float)):
                k_obs = max(k_obs, float(vs[-1]) + (float(age) + 0.02) / self.period)
            else:
                k_obs += (float(ob.get("render_wall_s") or 0.0) + 0.03) / self.period

        def now_k():
            return k_obs + ((time.monotonic() - t_entry) / self.period if live else 0.0)

        t_sim = step * bp.STEP
        t0 = round(t_sim - float(st["t_since_played"]), 3)
        if self.flight != (st.get("point"), t0):
            self.flight, self.obs, self.plan, self.sent = (st.get("point"), t0), [], None, None
            self.t_min = None
        if self.sent is not None and not self.sent["checked"]:
            c = st.get("command")
            if isinstance(c, dict) and isinstance(c.get("contact_in_s"), (int, float)):
                k_true = step + int(round(c["contact_in_s"] / bp.STEP))
                err = k_true - self.sent["k_c"]
                self.sent["checked"] = True
                if live and abs(err) <= 10:  # it took effect err steps later than assumed: arrive later next time
                    self.k_bias = max(-5.0, min(5.0, self.k_bias + 0.7 * err))
                plan = self.plan
                if plan is not None and not plan.get("skip"):
                    if err != 0:
                        plan["redo"] = True  # the act took effect at another step than assumed: send it again
                    # the reply's stroke notes bp.predict the delivery: if the joint speed limits cap the head speed or
                    # the pose is not delivered, take the next (faster-head or other-angle) stroke to the same target
                    notes = str(c.get("stroke") or "")
                    miss = bp._cm_off(notes)
                    vr = c.get("vel_rehearsed")
                    if (
                        not miss
                        and isinstance(vr, list)
                        and len(vr) == 3
                        and not plan.get("corrected")
                        and plan["t"] - t_sim > 0.35
                    ):
                        # the rehearsal predicts the head speed along the face: scale the command to make up for it
                        nrm = np.asarray(plan["normal"], float)
                        u_req, u_del = float(np.asarray(plan["vel"]) @ nrm), float(np.asarray(vr, float) @ nrm)
                        if u_req > 0.2 and u_del > 0.2 and abs(u_del - u_req) > 0.08 * u_req:
                            f = min(u_req / u_del, (bp.HEAD_MAX * 1.3) / max(1e-6, float(np.linalg.norm(plan["vel"]))))
                            plan["vel"] = np.asarray(plan["vel"], float) * f
                            plan["corrected"] = True
                            plan["redo"] = True
                    if miss is not None and miss > 4.0 and plan["t"] - t_sim > 0.35 and not plan.get("switched"):
                        # the arm cannot deliver that pose in time: a later contact (more time to swing), once
                        self.t_min = plan["t"] + bp.LATER_S
                        self.plan = None
                    elif (
                        ("head speed limited" in notes or "pose not delivered" in notes)
                        and plan.get("opts")
                        and plan["t"] - t_sim > 0.3
                        and not plan.get("switched")
                    ):
                        plan["switched"] = True  # once: every new plan restarts the swing from a moving arm
                        plan["normal"], plan["vel"] = plan["opts"].pop(0)
                        plan["redo"] = True
        tr = view.get("truth") or {}
        if not tr.get("shuttle_live"):
            return None
        tf, p, v = (
            t_sim,
            np.asarray(tr["shuttle_pos"], float),
            np.asarray(tr["shuttle_vel"], float),
        )  # the true state now
        ts, P, V = bp.predict(p, v, tf)
        land = P[-1]
        if land[2] <= 0.05 and (abs(land[0]) > bp.COURT_X + bp.OUT_MARGIN or land[1] < -bp.COURT_Y - bp.OUT_MARGIN):
            self.plan = {"skip": True}  # it lands out of your court: let it go (your point)
            return None
        t_now = now_k() * bp.STEP
        plan = self.plan
        if plan is None:
            opp = bp.backtrack(p, v, max(0.0, tf - t0))[:2]  # the shuttle where it was played: the opponent's spot
            later = self.t_min is not None
            c = bp.choose(
                ts,
                P,
                V,
                t_now + (self.lead + 2) * bp.STEP,
                np.asarray(st.get("robot_base_xy") or [0.0, -2.0]),
                self.vmax,
                self.amax,
                self.rng,
                opp=opp,
                t_min=self.t_min,
            )
            if c is None and later:  # no later contact: keep the stroke under way
                self.plan = {"skip": True}
                return None
            if c is None:
                self.plan = {"skip": True}
                return None
            t_c, pos, v_in, opts, target = c
            plan = self.plan = dict(
                t=float(t_c),
                pos=pos,
                normal=opts[0][0],
                vel=opts[0][1],
                target=target,
                opts=opts[1:],
                smash=bool(pos[2] >= bp.KILL_Z),
                switched=later,
            )
        elif plan.get("skip") or plan["t"] - t_now < bp.LAST_REFINE_S:
            return None
        elif plan.pop("redo", False):
            pass
        else:
            i = int(np.argmin(np.abs(ts - plan["t"])))
            if np.linalg.norm(P[i] - plan["pos"]) < bp.REFINE_M:
                return None
            th = (
                bp.SMASH_THETAS
                if plan.get("smash") and P[i][2] >= bp.KILL_Z
                else bp.DEEP_THETAS
                if plan["target"][1] > 0.6 * bp.COURT_Y
                else bp.SHORT_THETAS
            )
            opts = bp.strokes(P[i], V[i], plan["target"], th, bp.head_cap(plan["t"] - t_now))
            if not opts:
                return None
            plan.update(pos=P[i], normal=opts[0][0], vel=opts[0][1], opts=opts[1:])
        k_e = int(math.floor(now_k() + (self.k_bias if live else 0.0) + 1e-6)) + self.lead
        T = round(plan["t"] - k_e * bp.STEP, 3)
        pos = np.asarray(plan["pos"], float)
        if not (
            0.03 <= T <= 4.9
            and abs(pos[0]) <= self.act_x - 0.05
            and -(self.act_y - 0.05) <= pos[1] <= -0.35
            and 0.25 <= pos[2] <= 2.95
            and np.linalg.norm(plan["vel"]) <= 7.9
        ):
            return None  # outside the act's documented ranges
        self.sent = {"k_c": k_e + int(round(T / bp.STEP)), "checked": False}
        return {
            "type": "act",
            "t": T,
            "pos": [round(float(x), 4) for x in plan["pos"]],
            "normal": [round(float(x), 4) for x in plan["normal"]],
            "vel": [round(float(x), 4) for x in plan["vel"]],
        }
