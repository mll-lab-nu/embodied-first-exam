"""End a limited-mode trial the moment the agent's session ends, however it ends.

A limited-mode task (docs/LIMITED_MODE_1_1.md) runs the robot in a `sim` sidecar that takes commands until it is
told the trial is over. The verifier's collect hook tells it, with SIGUSR1, but only once the verifier starts --
about 12 s after the agent's time is up -- and a script the agent left running drives the robot until then: one
reset and ran a whole episode after the deadline, and that was the episode graded. So the adapters send the same
signal themselves when the agent's run returns or is cancelled. Unlimited tasks have no sidecar; the call fails and
is ignored.
"""

from __future__ import annotations

STOP = "kill -USR1 $(cat /data/server.pid)"


async def end_trial(environment) -> None:
    try:
        await environment.service_exec(STOP, service="sim", timeout_sec=30)
    except Exception:  # noqa: BLE001 -- no sidecar here, or it is gone: the collect hook still ends the trial
        pass
