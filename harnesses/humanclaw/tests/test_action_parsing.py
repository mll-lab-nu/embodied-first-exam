"""Prevent model action parameters from changing silently at execution time."""

import json
from types import SimpleNamespace

from PIL import Image
import pytest

from humanclaw_bench.agent.planner import HumanClawBenchPSVPlanSkillPlanner
from humanclaw_bench.agent.skills import ACTION_PARSER_VERSION, normalize_action
from humanclaw_bench.experiments.integration import register_capabilities
from humanclaw_bench.experiments.recorder import TraceRecorder, span
from humanclaw_bench.experiments.report import read_events, summarize_run, validate_trace
from humanclaw_bench.harnesses.environment import EnvironmentBridge


@pytest.mark.parametrize("action_id,plain,canonical,skill,condition", [
    (0, "Walk forward slow", "Walk<forward><slow>", "walk_forward", [0, 0.2, 0]),
    (0, "Walk forward normal", "Walk<forward><normal>", "walk_forward", [0, 0.4, 0]),
    (0, "Walk forward fast", "Walk<forward><fast>", "walk_forward", [0, 0.6, 0]),
    (1, "Stop/Stand", "Stop/Stand", "stand", None),
    (2, "Turn right 90", "Turn<right><90>", "turn", -90),
    # A real coauthor r2 trace requested right 120 but executed left 120.
    (2, "Turn right 120", "Turn<right><120>", "turn", -120),
    (2, "Turn left 45.5", "Turn<left><45.5>", "turn", 45.5),
    (3, "Climb upstairs normal", "Climb upstairs<normal>", "step_climb_up", [0.28, 0.30]),
    (4, "Sit down 0.455", "Sit down<0.455>", "sit", 0.455),
    (5, "Step back 0.125", "Step back<0.125>", "step_back", [0, -0.125]),
    (6, "Side step right 0.255", "Side step<right><0.255>", "side_walk", -0.255),
    (6, "Side step left 0.25", "Side step<left><0.25>", "side_walk", 0.25),
    (7, "Walk downstairs normal", "Walk downstairs<normal>", "step_climb_down", [0.20, 0.40]),
])
def test_complete_plain_and_bracketed_actions_have_identical_semantics(
    action_id, plain, canonical, skill, condition,
):
    for action_name in (plain, canonical, "  " + plain.upper() + "  "):
        for supplied_id in (None, action_id, str(action_id)):
            action = normalize_action({"action_id": supplied_id, "action_name": action_name})
            assert action.skill == skill
            assert action.cond == condition
            assert action.action_name == canonical
            # Logging the canonical name must not round away the actual motion.
            assert normalize_action({"action_name": action.action_name}) == action


@pytest.mark.parametrize("action_name,canonical", [
    ("Walk < forward > < normal >", "Walk<forward><normal>"),
    ("Turn\tright\t90", "Turn<right><90>"),
    ("Stop", "Stop/Stand"), ("Stand", "Stop/Stand"),
    ("Stop / Stand", "Stop/Stand"), ("Stop Stand", "Stop/Stand"),
    ("Climb up normal", "Climb upstairs<normal>"),
    ("Sit .45", "Sit down<0.45>"), ("Back 2.5e-1", "Step back<0.25>"),
    ("Side walk right .25", "Side step<right><0.25>"),
    ("Sidestep left .25", "Side step<left><0.25>"),
    ("Climb down normal", "Walk downstairs<normal>"),
])
def test_only_unambiguous_formatting_and_aliases_are_normalized(action_name, canonical):
    assert normalize_action({"action_name": action_name}).action_name == canonical


@pytest.mark.parametrize("action_id,action_name", [
    (0, "Walk"), (0, "Walk<forward>"), (0, "Walk normal"),
    (0, "Walk backward normal"), (0, "Walk<right><fast>"),
    (0, "Walk<forward><turbo>"), (0, "Walk<forward><slow><fast>"),
    (0, "Walk forward normal then stop"), (0, "Walk<forward> normal"),
    (0, "Walk<<forward>><normal>"), (0, "Walk<forward><normal"),
    (1, "Don't stop"), (1, "Stop<normal>"), (1, "standby"),
    (2, "Turn 90"), (2, "Turn<right>"), (2, "Turn<up><90>"),
    (2, "Turn right left 90"), (2, "Turn<right><90> left"),
    (2, "Turn right -90"), (2, "Turn<right><0>"), (2, "Turn<right><nan>"),
    (2, "Turn right inf"), (2, "Turn right 1e309"),
    (2, "Turn<right><90abc>"), (2, "Turn<right><90/2>"),
    (3, "Climb upstairs"), (3, "Climb upstairs<fast>"),
    (4, "Sit down"), (4, "Sit down<-0.5>"), (4, "Sit down<0>"),
    (4, "Sit down<NaN>"), (4, "Sit down<height>"), (4, "Sit down<0.45><0.5>"),
    (5, "Step back"), (5, "Step back<-0.25>"), (5, "Step back<0.25m>"),
    (5, "Step back<.2.5>"), (6, "Side step<0.25>"),
    (6, "Side step<center><0.25>"), (6, "Side step left right .25"),
    (6, "Side step<left><-0.25>"), (7, "Walk downstairs"),
    (7, "Walk downstairs<slow>"),
    (0, "Turn<right><90>"), (2, "Walk forward normal"),
    (1, "Sit down 0.45"), (7, "Climb upstairs normal"),
    (None, "dance"), (None, ""), (None, None), (None, 123),
])
def test_missing_invalid_extra_or_conflicting_parameters_never_default(action_id, action_name):
    with pytest.raises(ValueError):
        normalize_action({"action_id": action_id, "action_name": action_name})


@pytest.mark.parametrize("action_id", [True, False, 0.0, 2.9, -1, 8, "2.0", "unknown", [], {}])
def test_invalid_supplied_ids_are_not_truncated_or_inferred(action_id):
    with pytest.raises(ValueError, match="action_id"):
        normalize_action({"action_id": action_id, "action_name": "Turn right 90"})


@pytest.mark.parametrize("raw,expected", [
    ("Turn right 999", "Turn<right><120>"), ("Turn left 1", "Turn<left><10>"),
    ("Sit down 99", "Sit down<0.85>"), ("Sit down .01", "Sit down<0.15>"),
    ("Step back 99", "Step back<0.60>"), ("Step back .01", "Step back<0.10>"),
    ("Side step right 99", "Side step<right><0.50>"),
    ("Side step left .01", "Side step<left><0.10>"),
])
def test_documented_positive_numeric_clamps_are_preserved(raw, expected):
    assert normalize_action({"action_name": raw}).action_name == expected


def test_invalid_actions_are_recoverable_before_any_environment_side_effect(tmp_path):
    executed = []
    image = Image.new("RGB", (8, 8))

    def execute(step, decision):
        executed.append(decision)
        with span(decision.action.skill, kind="tool", input=decision.action.to_json()):
            return image, False

    env = EnvironmentBridge(image, 10, execute, "Find the chair.")
    request = {"request_id": "a1", "observation_id": 0,
               "action_name": "Turn 90", "visible_state": "The chair is on the right."}
    with TraceRecorder(tmp_path, {}) as recorder:
        register_capabilities("codex")
        for tool, invalid in [("turn", "Turn 90"), ("turn", "Turn<left><-90>"),
                              ("stand", "Turn right 90"), ("turn", "Walk forward normal")]:
            failed = env.submit(tool, {**request, "action_name": invalid})
            env.drain()
            assert failed.result()["isError"]
            assert env.step == 0 and not env.done and env.failure is None
            assert not env.cache and not executed and env.image is image

        # Rejected requests executed nothing; native recovery can correct the
        # parameters using the same observation and request ID without a reset.
        corrected = {**request, "action_name": "Turn right 90"}
        accepted = env.submit("turn", corrected)
        env.drain()
        assert not accepted.result()["isError"]
        assert env.call("turn", corrected) == accepted.result()
        assert env.step == 1 and len(executed) == 1
        assert executed[0].action.cond == -90
        assert executed[0].raw_plan["action_name"] == "Turn right 90"

    assert validate_trace(recorder.directory)["ok"]
    events = read_events(recorder.directory)
    starts = [e for e in events if e["event"] == "span.start" and e["name"] == "action.normalize"]
    ends = {e["span_id"]: e for e in events if e["event"] == "span.end"}
    final = starts[-1]
    assert final["data"]["input"]["action_name"] == "Turn right 90"
    assert final["data"]["attributes"]["action_parser_version"] == ACTION_PARSER_VERSION
    assert ends[final["span_id"]]["data"]["output"]["action_name"] == "Turn<right><90>"
    assert ends[final["span_id"]]["data"]["output"]["cond"] == -90
    rejected = [e for e in events if e["event"] == "tool.rejected"]
    assert len(rejected) == 4
    assert rejected[0]["data"]["arguments"]["action_name"] == "Turn 90"
    entries = {(e["kind"], e["name"]): e for e in summarize_run(recorder.directory)["capabilities"]["entries"]}
    assert entries["tool", "turn"]["executed"] == 1
    assert entries["tool", "turn"]["rejected"] == 3
    assert entries["tool", "stand"]["executed"] == 0


def test_native_bridge_preserves_walk_speed_and_turn_direction(tmp_path):
    executed = []
    image = Image.new("RGB", (8, 8))

    def execute(step, decision):
        executed.append(decision.action)
        return image, False

    env = EnvironmentBridge(image, 10, execute, "Find the chair.")
    with TraceRecorder(tmp_path, {}):
        for step, (name, raw) in enumerate([
            ("walk_forward", "Walk forward normal"),
            ("walk_forward", "Walk<forward><normal>"),
            ("turn", "Turn right 90"),
        ]):
            result = env.call(name, {"request_id": str(step), "observation_id": step,
                                    "action_name": raw, "visible_state": "The lane is clear."})
            assert not result["isError"]
            assert json.loads(result["content"][0]["text"])["action"] == executed[-1].to_json()
    assert [action.cond for action in executed] == [[0, 0.4, 0], [0, 0.4, 0], -90]


def test_psv_uses_the_same_explicit_parameters_without_changing_its_decision_loop(tmp_path):
    class Model:
        calls = 0

        def respond(self, messages):
            self.calls += 1
            return json.dumps({"action_id": 2, "action_name": "Turn right 90"})

    model = Model()
    planner = HumanClawBenchPSVPlanSkillPlanner(model)
    planner.reset(SimpleNamespace(instruction="Face the chair."))
    with TraceRecorder(tmp_path, {}) as recorder:
        result = planner.act(Image.new("RGB", (8, 8)), [], [])
    assert model.calls == 1
    assert result.action.cond == -90
    assert result.action.action_name == "Turn<right><90>"
    assert result.planner_skill["action_name"] == "Turn right 90"
    assert validate_trace(recorder.directory)["ok"]
