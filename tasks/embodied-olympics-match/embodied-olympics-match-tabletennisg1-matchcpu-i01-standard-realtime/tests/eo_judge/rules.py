"""The judge's rules (ruleset eo-judge-rules/1): every fault in a verdict names the rule that produced it.

Sources: fw_pattern_1020.md §7 (five decisions, 10-20), principle 6 (validity and blame follow the delivered
evidence, "undetermined" allowed), §3.1 / §3.8 (the judge's inputs and checks); the coordinator's decision of 10-19
(a seat that never opened its session is the platform's); the IMPL-JUDGE brief of 10-20.
"""
from __future__ import annotations

RULESET = "eo-judge-rules/1"

RULES = {
    "R-COMPLETE": "Completion and validity are two things: a match the world finished is valid only if the platform "
                  "delivered the declared environment (no void fault); a completed match is never valid by itself "
                  "(fw_pattern §6 D2: '打完就有效' deleted).",
    "R-TERM": "The match ends by the sport's finite termination rule (completed), an explicit resignation, a no-show, "
              "the platform's wall-clock cap, a platform fault (aborted), or it never starts (§7 item 5).",
    "R-WALLCAP": "Hitting the wall-clock cap is a platform fault: the match is void and rerun, never settled by the "
                 "score at that moment (§7 item 5).",
    "R-REVIEW": "A missing review never loses (§7 item 3): the review window resumes the match at its deadline; "
                "WHY / PLAN missing, empty or a template go to the diagnostics. A Host that ended a match or retired "
                "a side because a review was late applied a rule the framework no longer has: a platform fault.",
    "R-EXIT": "A harness or session ending is only an event; the seat's system stays in the match until it ends "
              "(§7 item 3). A seat container that ends on its own is an event too, and one the kernel stopped for "
              "outgrowing the declared memory is the agent's own (recorded). A Host or runner that ended a match "
              "because the sessions ended (abandoned, collected before the end) cut it short: a platform fault.",
    "R-NOSHOW": "A seat that opened its session and had not sent start by the preparation deadline is absent: its "
                "side loses (retired, exit no_show), the agent's own doing (§7 item 3).",
    "R-NOSESSION": "A seat that never opened its session while the start barrier waited (the harness or its "
                   "container never came up) is the platform's failure (decision of 10-19).",
    "R-RESIGN": "An explicit resignation: that side loses (retired, exit resigned), the agent's own doing.",
    "R-CLOCK": "A turn-based side whose clock ran out loses by the time rule (dnf), the agent's own doing.",
    "R-NOCODE": "Direct play: a model that called a tool (no-code audit) is disqualified, the agent's own doing.",
    "R-PLUGIN": "An exception inside the sport plugin is a task fault (class plugin), never the agent's (principle "
                "6; core/sport.py parse_action used to blame the player).",
    "R-WORLD": "A failure of the world service (Host, renderer, practice gate, metering) is the platform's; an "
               "error the record cannot place between the plugin and the Host is undetermined.",
    "R-REPLAY": "The fresh-process replay must reproduce the live match (state, scores, winner, commands, source, "
                "steps); a mismatch voids the match: the plugin's when the platform's evidence is otherwise clean "
                "(fwspec 6.4), undetermined when the platform also failed.",
    "R-REPLAY-FP": "A replay is compared only under the run's execution fingerprint: one made with the match, or in "
                   "portable float mode, or in native mode on the same CPU model with the same MuJoCo / BLAS builds "
                   "and thread counts. Otherwise it is 'not comparable' (check n/a, recorded in diagnostics.replay), "
                   "never a failed replay (handoff/rlopp_inventory_1020.md: a native humanoid match diverges at step "
                   "372 on another CPU).",
    "R-API-CAUSE": "Model-call errors are blamed by cause, not by status alone: bad requests, the seat's own budget "
                   "and its own client going away are the agent's (recorded, never void); 401 / 403 / 402 / 404, "
                   "the platform account's 429 and failover errors are the platform's; 5xx, broken streams and "
                   "upstream connection errors are the external service's; the rest is undetermined (D2).",
    "R-API-OUTAGE": "Model access (decided 10-21, integrity/model_access_lost@1): a model-service failure is judged "
                    "only by the time a seat lost to it, never by error counts. A seat that lost more than "
                    "max(min_s, match_fraction x the session's actual duration, preparation + match) (Chi 10-21; "
                    "TaskSpec integrity.tolerance.model_access_lost, default max(120 s, 5 %)) voids the match, over "
                    "the sealed gateway log's calls started before the match end, the preparation's included; the "
                    "class is the cause's: the gateway platform, the "
                    "provider external, mixed or unplaced undetermined (gateway.py).",
    "R-INTEGRITY": "Real-time integrity (decided 10-21): a world reading over its tolerance (world lag p99 and its "
                   "single spike, late steps, render and plan misses, a miss fraction only with more late items than "
                   "its floor) is the platform's: void, rerun. A maximum or cumulative breach (the world lag spike, "
                   "a stalled world, a seat's lost model access past the Task's worst case) ends the match at once: "
                   "the Runner aborts it through the Host's management channel (integrity.abort = at_breach; "
                   "termination integrity_abort), the fault's class by where it happened.",
    "R-GATEWAY-LOG": "A model seat whose gateway log is missing, or whose gateway counted failures it never logged, "
                     "lacks the evidence for the outage rule: undetermined.",
    "R-PLATFORM-EVENT": "The backend could not deliver the match (environment start, seat setup, network, a backend "
                        "that failed before the match ended, an injected fault), or before the match was over the "
                        "world's container died or the platform stopped a seat's container: a platform fault. "
                        "Container events after the world's end are the backend tearing the match down; a harness "
                        "that exits or fails after its setup is only an event (R-EXIT).",
    "R-INPUT": "The judge checks its inputs (checks.py): a Run that executed another Task release or Fixture, other "
               "images, fewer resources, or a world beyond the integrity tolerance did not get the declared "
               "environment: a platform fault; sealed evidence that is missing or changed: undetermined.",
    "R-SCOPE": "Void faults void the whole match by default; only a Task that declares validity.unit = side, "
               "separable results and the test proving it voids one side (§7 item 5).",
    "R-JUDGE": "The judge itself failed on this evidence: void, the platform's (a trial never passes silently).",
    "R-OFFICIAL": "Official results need a valid verdict, a frozen release, an official Fixture with a hidden seed, "
                  "a certified backend and no runtime override (§3.3, §3.8).",
}

# what a void fault means for the Runner (Fixture.rerun.on_faults decides; this is the default)
DEFAULT_RERUN_ON = ("plugin", "platform", "external", "undetermined")

# legacy errors[].where (ro-final/1) -> (class, rule): the record does not say who raised it
LEGACY_ERROR_WHERE = {
    "observation": ("plugin", "R-PLUGIN"),          # the plugin's observation broke its declared whitelist
    "continuous_score": ("plugin", "R-PLUGIN"),     # the sport's scoring hook raised
    "devworld_gate": ("platform", "R-WORLD"),
    "replay": ("undetermined", "R-REPLAY"),         # the replay process failed (plugin or platform)
    "meter": ("platform", "R-WORLD"),
}

# Harbor exception types (legacy platform events)
SETUP_EXCEPTIONS = {"AgentSetupTimeoutError", "EnvironmentStartTimeoutError", "EnvironmentBuildTimeoutError",
                    "RuntimeError", "DockerError", "EnvironmentError"}
