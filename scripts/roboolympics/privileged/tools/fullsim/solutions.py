"""The twins' solutions: generator side only (scripts/roboolympics/privileged/generate.py), never copied into a
task's simulator (the #282 review, H.2: the agent's copy names no oracle). Each: the program solution/program.py,
the files it needs beside it in solution/, and the oracle evidence of task.toml [metadata]."""

SOLUTIONS = {
    "badminton": {"program": "tools/fullsim/oracles/badminton.py", "files": ('sports/badminton/builtin_players.py',),
        "evidence": None},
    "soccer": {"program": "tools/fullsim/oracles/soccer.py", "files": (),
        "evidence": "full-state reference program (solution/): the screening's truth reference (the frozen scripted coach at the reference level: both robots go for the ball, in-walk kick) as a program reading the declared truth; in step timing it reproduces the in-world truth reference bit for bit; its results at levels 2 and 3 and on this instance are in the RoboOlympics privileged report (soccer section)"},
    "soccer_ssl": {"program": "tools/fullsim/oracles/soccer_ssl.py", "files": ('sports/soccer_ssl/builtin_players.py',),
        "evidence": "full-state reference program (solution/): the sport's reference team (the camera-only reference player's decision code) fed the true state; its formal S = 10 results and its results across levels 1-3 against the camera reference are in the RoboOlympics privileged report (tools/fullsim/calibrate.py)"},
    "tabletennis": {"program": "tools/fullsim/oracles/tabletennis.py", "files": ('sports/tabletennis/builtin_players.py',),
        "evidence": None},
}
