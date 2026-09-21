"""Versioned access and interaction profiles, separate from model providers."""


def profile(agent):
    mode = agent.get("access_mode", agent.get("mode", "rgb"))
    if "mode" in agent and "access_mode" in agent and agent["mode"] != mode:
        raise ValueError("mode and access_mode disagree")
    if mode not in ("rgb", "simulator", "rgb_privileged"):
        raise ValueError("Unknown access mode")
    # Existing configurations keep their segment protocol. New simulator profiles
    # and explicit interaction=tools use the live SDK.
    interaction = agent.get("interaction", "tools" if mode == "simulator" else "segments")
    if interaction not in ("tools", "segments"):
        raise ValueError("interaction must be tools or segments")
    reset = agent.get("reset_policy", "same_preset" if mode == "simulator" else "disabled")
    if reset not in ("disabled", "same_preset"):
        raise ValueError("Unknown reset policy")
    if interaction == "segments" and (mode == "simulator" or reset != "disabled"):
        raise ValueError("Simulator access and reset require interaction=tools")
    if interaction == "tools" and mode == "rgb_privileged":
        raise ValueError("rgb_privileged is a legacy segment-only condition")
    return dict(access_mode=mode, interaction=interaction, reset_policy=reset)
