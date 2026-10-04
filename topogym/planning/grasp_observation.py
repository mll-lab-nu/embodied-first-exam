"""Passive explanations of backend reports and durable World-tick grasp events."""
from copy import deepcopy

import json
from topogym.utils.io import to_jsonable


def json_value(value):
    return json.loads(json.dumps(to_jsonable(value), allow_nan=False))


GRASP_EVENTS = {"grasp_acquired", "grasp_lost", "grasp_released", "grasp_rejected"}


def condition(value, threshold, *, minimum=False, source="backend_report"):
    known = value is not None and threshold is not None
    margin = (value-threshold if minimum else threshold-value) if known else None
    return dict(value=value, threshold=threshold, margin=margin,
                satisfied=None if margin is None else margin >= -1.e-12, source=source)


def explain_grasp(raw, *, hand=None):
    """Never reruns admission/health callbacks: they can modify backend caches."""
    raw = json_value(raw) if raw else {}
    config = raw.get("config", {})
    hands = raw.get("hands", {})
    if hand is not None and hands and hand not in hands:
        raise ValueError("Unknown grasp hand")
    targets = {t["entity"]: t for t in config.get("targets", ())}
    result = {}
    for name, state in hands.items():
        if hand is not None and name != hand:
            continue
        admission = raw.get("admission", {}).get(name, {})
        health = raw.get("health", {}).get(name, {})
        binding = state.get("binding")
        entity = binding["target"][0] if binding else admission.get("entity")
        target = targets.get(entity, {})
        measured = health if binding else admission
        gates = dict(
            closing_intent=dict(value=state.get("intent"), satisfied=state.get("intent") == "close",
                                source="manager_state"),
            stable_time_s=condition(state.get("stable_time_s"), config.get("stable_time_s"),
                                    minimum=True, source="manager_state"),
            bilateral_region_count=condition(admission.get("qualified_region_centers"), 1,
                                               minimum=True, source="last_admission_sample"),
            material_edge_ratio=condition(measured.get("max_material_edge_ratio"), target.get("max_strain_ratio"),
                                          source="last_health_sample" if binding else "last_admission_sample"),
            follow_error_m=condition(health.get("max_follow_error_m") if binding else None,
                                     config.get("max_translation_error_m"), source="last_health_sample"))
        gaps = admission.get("minimum_finger_distances_m")
        gates["finger_distance_m"] = [condition(v, target.get("contact_distance_m"),
            source="last_admission_sample") for v in gaps] if gaps is not None else None
        reason = state.get("rejection")
        detail = reason
        if reason == "no_bilateral_candidate":
            detail = admission.get("rejection") or (
                "no_nearby_material_vertices" if admission.get("nearby_vertices") == 0 else
                "no_qualified_material_region" if admission.get("qualified_region_centers") == 0 else reason)
        result[name] = dict(phase=state.get("phase"), intent=state.get("intent"),
            entity=entity, candidate=state.get("candidate"), binding=binding,
            reported_reason=reason, explanation=detail, conditions=gates,
            admission=admission, health=health,
            interpretation="unknown conditions remain null; cached admission is not a current contact-force measurement")
    return dict(enabled=bool(raw) and config.get("model", "none") != "none",
        model=config.get("model", "none"), active=raw.get("active", False), hands=result,
        physics_step=raw.get("physics_step"), events=raw.get("events", []),
        acquisition_evidence=raw.get("acquisition_evidence"),
        sampling_scope=raw.get("sampling_scope"), reaction_force=raw.get("reaction_force"),
        physical_grasp_without_assist="not determined by assist state")


class GraspTrace:
    """Collect transient events before the next World tick clears the manager."""
    def __init__(self, emit):
        self.emit = emit
        self.branch = None
        self.sequence = 0
        self.rejections = {}
        self.control_events = []

    def begin_control(self):
        self.control_events = []

    def observe(self, record):
        state, raw = record["state"], record["world"].get("grasp") or {}
        branch = (state["episode_id"], state["branch_id"])
        if branch != self.branch:
            self.branch, self.sequence, self.rejections = branch, 0, {}
            self.control_events = []
        rows = []
        for event in raw.get("events", ()):
            if event["sequence"] > self.sequence:
                rows.append(dict(name="grasp_"+event["event"], **json_value(event)))
        self.sequence = max(self.sequence, raw.get("event_sequence", 0))
        for hand, value in raw.get("hands", {}).items():
            rejection = value.get("rejection")
            if rejection and value.get("phase") != "lost" and rejection != self.rejections.get(hand):
                rows.append(dict(name="grasp_rejected", hand=hand, reason=rejection,
                    explanation=explain_grasp(raw, hand=hand)["hands"][hand]["explanation"],
                    source="observed_rejection_transition"))
            self.rejections[hand] = rejection
        for event in rows:
            row = dict(event, state=json_value(state))
            self.control_events.append(row)
            self.emit("grasp_event", **deepcopy(row))
        return rows
