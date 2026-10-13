"""penalty-kick (v2, official goal and mark): the referee says no to standing still, to a weak kick, to a kick the
goalkeeper dummy reaches, to a ball wide of the post or over the bar, to a backward kick, to a second touch (a
dribble), to a ball played with another part and to a ball that goes in without a kick; yes to a hard kick into the
corner.

The positive is an INJECTION: no kicking controller exists for the G1 (measured: a foot that runs into the ball at
4 m/s sends it off at 3 to 5 m/s; the dummy is beaten from about 12 m/s). Real: the robot walks up to the ball and its
right foot really touches it; the ball then really flies 11 m in air and crosses the line beside the moving dummy.
Injected: the ball's velocity at that contact (what a real kick would have given it)."""
import numpy as np

from rfo.testing import act, hold, make, verdict

FAMILY = "penalty-kick"
CORNER = (19.0, 5.6, 2.0)          # about 20 m/s to the left corner, half way up
FOOT_Y = 0.11                      # the G1's foot is this far beside its pelvis


def kick(w, A, vel=None, vx=0.8, keep_walking=False, watch=None, shift=(0.0, 0.0, 0.0)):
    """Walk up to the ball with the right foot in line with it; at the first contact of the foot the ball's velocity
    is set to `vel` (None: left as the foot made it; shift: and the ball moved by this, clear of the foot). watch(w):
    called every step."""
    rest, done = w.robot.rest[12:], False
    while not w.done:
        _, y, _, yaw = w.pelvis()
        go = keep_walking or w.task.trackers["kick_t"] is None
        act(w, A, "walk", np.r_[vx if go else 0.0, float(np.clip(2.0 * (FOOT_Y - y), -0.3, 0.3)) if go else 0.0,
                                float(np.clip(-1.5 * yaw, -0.5, 0.5)), rest, 0, 0])
        if not done and w.task.trackers["kick_t"] is not None:
            done = True
            if vel is not None:
                w.put("ball", w.pos("ball") + shift, vel=vel)
        if watch is not None:
            watch(w)


def main():
    w, A = make(FAMILY)
    p, g = w.task.p, w.task.geometry()
    m = w.m
    assert g["goal_x"] - g["mark_x"] == 11.0 and p["goal_width_m"] == 7.32 and p["goal_height_m"] == 2.44
    # the official goal as built: the posts' inner faces 7.32 m apart, the bar's lower edge at 2.44 m, 0.12 m thick
    for tag, s in (("L", 1), ("R", -1)):
        post = m.geom(f"goal_post{tag}")
        assert abs(post.pos[1] - s * (3.66 + 0.06)) < 1e-9 and abs(post.size[0] - 0.06) < 1e-9, post.pos
    bar = m.geom("goal_bar")
    assert abs(w.d.geom_xpos[bar.id][2] - (2.44 + 0.06)) < 1e-6 and abs(bar.size[0] - 0.06) < 1e-9
    ballg = m.geom("ball")
    assert abs(ballg.size[0] - 0.11) < 1e-9 and abs(m.body("ball").mass[0] - 0.43) < 1e-9
    keeper = w.ref.geoms(names=["keeper"])

    hold(w, A)                                                             # nop
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [] and v["metrics"]["keeper_y_m"] == 0.0, v

    seen = {"max_v": 0.0, "moved_before": False, "touched": False}

    def watch(w):                                                          # the dummy: when and how fast it moves
        tr = w.task.trackers
        kv = abs(float(w.d.qvel[w.task.kv]))
        seen["max_v"] = max(seen["max_v"], kv)
        if kv > 0 and (tr["kick_t"] is None or w.ref.time < tr["kick_t"] + p["keeper_delay_s"] - 0.011):
            seen["moved_before"] = True
        seen["touched"] |= w.ref.touching(w.task.ball, keeper)

    w.reset(); kick(w, A, CORNER, watch=watch)                             # positive (injection, see the docstring)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["kick", "goal"], v
    assert not seen["moved_before"] and 0 < seen["max_v"] <= p["keeper_speed_m_s"] + 1e-6 and not seen["touched"], seen
    assert v["metrics"]["keeper_y_m"] > 0.3, v                             # it went the right way, and was too late
    sha, t_ok, ky = w.state_sha(), w.t, v["metrics"]["keeper_y_m"]
    w.reset(); kick(w, A, CORNER)
    assert w.state_sha() == sha                                            # the same run again: the same state

    seen.update(max_v=0.0, moved_before=False, touched=False)
    w.reset(); kick(w, A, (7.6, 2.24, 0.8), watch=watch)                   # the same corner at 8 m/s: the dummy is there
    v = verdict(w)
    assert not v["success"] and v["stages"] == ["kick"] and seen["touched"], (v, seen)
    assert v["failed"] in ("time", "the ball came to rest without a goal"), v
    saved = v["failed"]

    w.reset(); kick(w, A, (10.0, -0.8, 7.7))                               # chipped over the dummy, under the bar
    v = verdict(w)
    assert v["success"], v

    w.reset(); kick(w, A, (0.6, 0.0, 0.0))                                 # a weak kick: the ball stops short
    v = verdict(w)
    assert v["failed"] == "the ball came to rest without a goal" and v["stages"] == ["kick"], v

    w.reset(); kick(w, A, (19.0, 7.6, 2.0))                                # wide of the post
    v = verdict(w)
    assert v["failed"] == "the ball crossed the goal line outside the goal" and v["stages"] == ["kick"], v

    w.reset(); kick(w, A, (19.0, 3.0, 7.5))                                # over the bar
    v = verdict(w)
    assert v["failed"] == "the ball crossed the goal line outside the goal" and v["stages"] == ["kick"], v

    w.reset(); kick(w, A, (-3.0, -3.0, 0.0), shift=(0.0, -0.25, 0.0))         # kicked backwards (moved clear of the foot)
    v = verdict(w)
    assert v["failed"] == "the ball was not kicked forward" and v["stages"] == ["kick"], v

    w.reset(); kick(w, A, (1.0, 0.0, 0.0), keep_walking=True)              # a tap, and walking on into the ball (a dribble)
    v = verdict(w)
    assert v["failed"] == "second touch of the ball" and v["stages"] == ["kick"], v

    w.reset(); hold(w, A, 0.1)                                             # in without a kick
    w.launch("ball", (g["mark_x"], 0.0, 0.11), (19.0, 5.6, 2.0)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [], v

    w.reset(); hold(w, A, 0.1)                                             # played with the body
    w.launch("ball", (1.0, 0.0, 0.75), (-4.0, 0.0, 0.0)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "the ball was touched by something other than a foot" and v["stages"] == [], v
    print(f"injection: goal at t = {t_ok:.2f} s, the dummy had moved {ky:.2f} m; the 8 m/s shot was saved ({saved})")
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
