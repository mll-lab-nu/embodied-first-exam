"""Declared solver permissions; the hosting harness enforces tool access."""


def tool_policy(allow_internet=True):
    if type(allow_internet) is not bool:
        raise ValueError("allow_internet must be a boolean")
    return dict(local_tools="unrestricted", reference_access="task_brief_current_episode_and_general_knowledge",
                allow_internet=allow_internet, enforcement="prompt_policy",
                forbidden_references=["repository implementation source", "existing solutions and demo videos",
                                      "other trials and trajectories", "private assets and simulator state",
                                      "external object reference images, CAD and precomputed target geometry"],
                network_scope="solver web/search/download/remote tools; localhost bridge and host model transport are exempt",
                environment_access="actions only through bridge; no reset, rollback, state/evaluator mutation or duplicate episode")


def policy_prompt(policy):
    network = ("Internet research, downloads and remote tools for general robotics knowledge and libraries are allowed; "
               "do not search for this task's existing solutions, demos, reference images, object geometry or implementation."
               if policy["allow_internet"] else
               "Internet research, downloads and remote tools are disabled. Localhost bridge access remains allowed.")
    return ("External solver tools are unrestricted by the benchmark: shell, Python/libraries, image/video analysis, "
            "local numerical/kinematic planning and general libraries may be used. Solve from scratch using the "
            "provided task brief, scene/robot/camera facts, and this episode's observations. Do not read repository "
            "implementation source, existing solutions/demo videos, other trials/trajectories, private assets or "
            "simulator state. Tool freedom does not grant access to these references. Record permitted sources used. "
            "Infer object configurations from this episode's camera frames and action feedback. No object reference "
            "images, CAD, precomputed shapes or target transforms are supplied or permitted as external references; "
            "you may build and test your own geometric hypotheses from the allowed observations. "
            "Available tools are supplied by your host harness. "
            + network + " This declaration is a prompt policy, not a network firewall. "
            "Only the bridge may advance the live environment; do not reset, rewind, clone the episode, "
            "mutate its state or change the evaluator. The restricted action-script language below applies "
            "only to code submitted to env.step, not to your external planning tools.\n")
