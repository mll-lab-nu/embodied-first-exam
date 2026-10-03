"""Offline check of the net cord (ITF Rule 25 a) in both tennis engines, run inside the sim image:

    docker run --rm -v tasks/<tennis task>/environment/sim:/srv:ro -v scripts/olympiad/tennis:/t:ro \
        ghcr.io/mll-lab-nu/eai-olympiad:0.1.0 python3 /t/test_net_cord.py [duel]

A ball is launched from just behind the hitter's service line so that it clips the net's top edge; the check: the
engine records a `cord` event, the ball then lands in the receiver's court and play goes on (single: the scripted
opponent returns it; duel: the point goes on until the idle receiver lets it bounce twice). The ball state is set by
hand here, so this is not a replayable match; determinism is checked by the Harbor runs."""
import sys
sys.path.insert(0, "/srv")
import numpy as np
import tn

P0 = (0.3, -3.0, 1.1)


def clip_shot(sign=+1.0):
    """A launch velocity (towards +y if sign > 0) whose flight touches the net's top edge and lands in court."""
    for vz in np.arange(-1.5, 0.5, 0.005):     # fine steps: the edge is touched over a few cm of height
        v = (0.0, 18.0 * sign, float(vz))
        p0 = (P0[0], P0[1] * sign, P0[2])
        P, V, W, ev = tn.predict(p0, v, (0.0, 0.0, 0.0))
        kinds = [e[1] for e in ev]
        if kinds[:1] == ["cord"] and "bounce" in kinds:
            b = ev[kinds.index("bounce")]
            if tn.in_court(sign * b[2], sign * b[3], +1):
                return p0, v, ev
    raise SystemExit("no net-cord launch found")


def single():
    m = tn.Match(1)
    m.precompute_serves()
    p0, v, ev = clip_shot()
    print("predicted events:", [(e[1], round(e[2], 2), round(e[3], 2)) for e in ev])
    leg = m.leg
    leg.update(state="to_opp", hit={"speed": float(np.linalg.norm(v)), "offcentre": 0.0}, launch=m.k)
    m.s.b_p, m.s.b_v, m.s.b_w, m.s.b_live, m.s.hit_enabled = p0, v, (0.0, 0.0, 0.0), True, False
    m.s.events = []
    m._opp_plan_k = m.k + int(round(m.lv["reaction_s"] / tn.CONTROL_DT))
    seen = []
    n_res = len(m.results)
    for _ in range(600):
        m.step(m._arm_target())
        seen += [e["kind"] for e in m.s.events if e["kind"] not in seen]
        if len(m.results) > n_res:
            break
    print("events:", seen, "| result:", m.results[-1]["summary"])
    assert "cord" in seen and m.results[-1]["returned"], "net cord ball not played on"
    print("single: OK (the ball touched the net, landed in and the opponent returned it)")


def duel_check():
    import duel
    g = duel.Duel()
    while not g.in_play() or g.rs["state"] != "live":
        g.rt_advance(1)
    p0, v, ev = clip_shot()                     # A's shot in the world frame (A plays towards +y)
    g.rs.update(hitter="A", expect="B", bounces=0, played_k=g.k)
    g.sides["A"].hit_enabled = False; g.sides["B"].hit_enabled = True
    g.b_p, g.b_v, g.b_w, g.b_live = p0, v, (0.0, 0.0, 0.0), True
    g.events = []
    n0 = len(g.points)
    kinds = []
    while len(g.points) == n0:
        kinds = [e["kind"] for e in g.events]          # the point's events (cleared when the next point starts)
        g.rt_advance(1)
    print("events:", kinds, "| point:", g.points[-1]["how"])
    assert kinds[0] == "cord" and kinds[1] == "bounce" and g.points[-1]["winner"] == "A" \
        and "bounce twice" in g.points[-1]["how"], "net cord ball not played on"
    print("duel: OK (net cord, bounce in B's court, play went on until B let it bounce twice)")


if __name__ == "__main__":
    duel_check() if sys.argv[1:] == ["duel"] else single()
