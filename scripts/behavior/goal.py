"""What a BEHAVIOR-1K goal means, in words, for task instructions (used by scripts/behavior/mk_tasks.py).

PREDICATES quotes OmniGibson v3.9.2's object states (omnigibson/object_states/*.py in the image) for every predicate the
built tasks use, with the thresholds that decide them. A task's instruction lists only the predicates its goal uses.
BDDL's `forn (N)` holds for exactly N (bddl/condition_evaluation.py NQuantifier: sum == N), and `forpairs` needs a
one-to-one matching; the task texts say so where it matters."""
import re

PREDICATES = {
    "inside": "`inside(A, B)`: the centre of A's axis-aligned bounding box lies within B's bounding box and within B's "
              "interior (container) volume.",
    "ontop": "`ontop(A, B)`: A touches B and B is directly below A (and not above it).",
    "nextto": "`nextto(A, B)`: the gap between A's and B's axis-aligned bounding boxes is at most one sixth of the mean of "
              "their summed box dimensions, and nothing lies between them along a horizontal axis.",
    "under": "`under(A, B)`: B is directly above A (and not below it).",
    "touching": "`touching(A, B)`: A and B are in physical contact.",
    "open": "`open(A)`: at least one of A's openable joints (door, drawer, lid) is more than 5% of the way from closed to "
            "fully open; closed (`not open`) means every such joint is within 5% of closed.",
    "toggled_on": "`toggled_on(A)`: A's switch is on. It flips when a robot finger touches A's toggle button for 5 "
                  "consecutive control steps; touch it again, after letting go, to flip it back.",
    "cooked": "`cooked(A)`: the highest temperature A has ever reached is at least its cooking temperature (70 °C by "
              "default). Heat comes from a heat source that is on (a stove burner, an oven: 200 °C) within 0.2 m of A; "
              "once cooked, A stays cooked.",
    "frozen": "`frozen(A)`: A's current temperature is at or below its freezing temperature (0 °C by default). Objects "
              "drift back towards the 23 °C room temperature, so A stops being frozen once it has warmed above 0 °C.",
    "on_fire": "`on_fire(A)`: A's temperature has reached its ignition temperature (250 °C by default); once lit, it stays "
               "on fire and heats what is near it.",
    "attached": "`attached(A, B)`: A is fixed to B through their attachment points; the joint forms by itself when A's "
                "attachment point is brought within 5 cm and 15° of a compatible one on B.",
    "covered": "`covered(A, S)`: at least one particle of the substance S (e.g. dust) is on A; A is clean of S (`not "
               "covered`) only when every particle of S has been removed from it.",
}


def goal_block(bddl: str) -> str:
    """The balanced (:goal ...) s-expression of a BDDL problem."""
    g0 = bddl.index("(:goal")
    depth, i = 0, g0
    while True:
        depth += {"(": 1, ")": -1}.get(bddl[i], 0); i += 1
        if depth == 0:
            return bddl[g0:i]


def used_predicates(bddl: str) -> list[str]:
    """The known predicates a goal uses, in PREDICATES order."""
    words = set(re.findall(r"\(\s*([a-z_]+)\s", goal_block(bddl)))
    return [p for p in PREDICATES if p in words]


def meanings(bddl: str) -> str:
    """Markdown bullets: what each predicate of this goal means."""
    return "\n".join(f"- {PREDICATES[p]}" for p in used_predicates(bddl))


def task_objects(bddl: str) -> list[str]:
    """The task's BDDL object instances, without floors, the agent and whole-category (`_*`) entries."""
    m = re.search(r"\(:objects(.*?)\)\s*\(:init", bddl, re.S)
    names = re.findall(r"\b([a-z_]+\.n\.\d+_\d+)\b", m.group(1) if m else "")
    return [n for n in names if not n.startswith(("floor.", "agent."))]
