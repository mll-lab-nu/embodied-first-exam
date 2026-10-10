A `final.json` that is missing, unreadable or without a verdict (the collect hook did not finish), and replays that could not
run (`gpu_lost`, a replay process without a result), are an infrastructure failure (`infra_error = 1`), not the agent's 0;
`sim_error = 1` marks an episode that a simulator error ended. The collect hook has 5400 s.
