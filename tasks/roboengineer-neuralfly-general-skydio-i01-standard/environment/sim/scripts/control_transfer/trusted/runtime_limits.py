"""Operator-owned time and sampling bounds for whole-lap CPU evaluation."""

import math

LAP_AGENT_SECONDS = 129600
LAP_FAMILY = "control-transfer/anycar-circuit-lap-v2"


def runtime_limits(instance):
    if instance.get("task_variant") == "circuit-compact-lap/3":
        public, bank = instance["public"], instance["bank"]
        if (
            instance["family"] != "anycar"
            or type(public.get("horizon_s")) not in (int, float)
            or public["horizon_s"] != 30
            or public.get("route_revision") != "compact-30s/1"
            or len(bank["adaptation"]) != 3
            or len(bank["held_out"]) != 10
            or any(
                c.get("full_lap") is not True
                or c.get("track_id") != public["track_id"]
                or c.get("route_revision") != "compact-30s/1"
                for cases in bank.values()
                for c in cases
            )
        ):
            raise ValueError("Compact lap requires the frozen 30-second route and case bank")
        # Generous CPU wall deadlines, not simulated time or hardware guarantees.
        # Three cases per request; drain one request before ten rendered/replayed cases.
        return dict(
            worker_seconds=300,
            replay_seconds=120,
            extract_seconds=60,
            request_seconds=1200,
            collect_seconds=5520,
            uniform_images=False,
            max_images=48,
            max_video_frames=None,
        )
    if instance.get("task_variant") != "circuit-lap/2":
        return dict(
            worker_seconds=600,
            replay_seconds=600,
            extract_seconds=60,
            collect_seconds=1740,
            request_seconds=1800,
            uniform_images=False,
            max_images=48,
            max_video_frames=None,
        )
    public, bank = instance["public"], instance["bank"]
    horizon = public["horizon_s"]
    if (
        instance["family"] != "anycar"
        or type(horizon) not in (int, float)
        or not math.isfinite(horizon)
        or not 0 < horizon <= 4000
    ):
        raise ValueError("Full-lap horizon outside the frozen catalog bound")
    if len(bank["adaptation"]) != 3 or len(bank["held_out"]) != 10:
        raise ValueError("Full-lap bank cardinality")
    if any(
        c.get("full_lap") is not True or c.get("track_id") != public["track_id"]
        for cases in bank.values()
        for c in cases
    ):
        raise ValueError("Full-lap cases must match the declared public route")
    # CPU render margin, separate faster non-render replay budget, and FFmpeg decoding.
    worker = max(600, math.ceil(3 * horizon + 180))
    replay = max(600, math.ceil(0.5 * horizon + 120))
    extract = max(120, math.ceil(0.25 * horizon + 60))
    request = 3 * (worker + extract) + 120
    # Allow an in-flight adaptation round to drain before ten rendered/replayed cases.
    collect = request + 10 * (worker + replay) + 120
    if 3 * request + 1800 > LAP_AGENT_SECONDS:
        raise ValueError("Full-lap adaptation does not fit its declared cutoff")
    return dict(
        worker_seconds=worker,
        replay_seconds=replay,
        extract_seconds=extract,
        collect_seconds=collect,
        request_seconds=request,
        uniform_images=True,
        max_images=128,
        max_video_frames=math.ceil(horizon * 10) + 2,
    )
