# LIBERO-Pro adapter change register

Baseline RoboRSI: `6f0107219d73dcf549b19e585f884f6b3fc3dac6`.
The experiment measures four harnesses under a common versioned environment
contract. These adapters change the task/tool interface and instrumentation;
they do not represent the completely unconfigured defaults of those products.

| Component | Adaptation | Decision flow retained |
|---|---|---|
| Bare API | Ordinary Responses history, common catalog and observations | One model call, dispatch returned tools, append results/images, repeat |
| Codex | App Server provider/MCP configuration, isolated home/workspace, two initial images, preauthorized simulation MCP server | Native thread/turn, tool selection, context compaction, retries, completion |
| Pi | Native RPC provider/MCP configuration, isolated home/session, two initial images | Native agent loop, tools, compaction, retries, completion |
| RoboRSI Frozen | `ROBORSI_ROLE_SESSION=0`, frozen mode, borrowed prepared environment, common dispatch/schema/image serialization | Upstream `run_atomic_episode`, Planner/Engineer/Reviewer, reflection, replanning, round budgets and completion decisions |
| Planner bug fix | Direct API path sends the supplied image files as image content | Existing role prompt, planning and output parser |
| Role evidence | Planner/Reviewer initial/final evidence uses the common 256px head/wrist frames and JPEG settings | The native timing/selection of evidence and Reviewer evidence-reading loop |
| RoboRSI instrumentation | Scoped wrappers around role calls, skill dispatch, perception/solver/motion entry points and HTTP clients | Return values and control decisions |
| Common controller | Journal around the actual `OffScreenRenderEnv.step` boundary | Original JOINT_POSITION controller and published skill implementations |

Both request and motion journals use SQLite `PERSIST` rollback journals with
`synchronous=FULL`. This retains durable pre-execution intent while avoiding
per-step journal creation/deletion on GPFS. It does not batch away control steps
or weaken acknowledgement durability. An uncommittable result ends execution;
the pending request remains indeterminate and cannot be repeated.

Snapshot restoration reapplies saved integration inputs after simulator forward
and observation refresh, because those operations can overwrite MuJoCo's solver
warm-start cache. This fixes replay/rerun initialization and does not modify the
original rollout's commands or controller. Every physical replay also records
its own framework source identity, independently of the original run.

While the common gateway is active, its `127.0.0.1`/`localhost` addresses bypass
inherited cluster HTTP proxies. Existing proxy exclusions are preserved, and
external provider traffic still uses the configured cluster egress proxy.
This is transport configuration, without changing SDK retry or agent behavior.

The only change inside the RoboRSI checkout is recorded in
`patches/roborsi/0001-planner-direct-api-images.patch`. Other hooks live in the
benchmark adapter and are reverted when its context exits. The existing
HumanCLAW native driver adds a backward-compatible initial-image-list change and
uses the configured startup timeout for its pre-session Codex version probe.
The latter accommodates cold executable reads on shared storage; it does not
change the native agent's decisions, request timeouts or episode budget.

Every top-level physical tool request carries a unique `request_id` and the
`observation_id` used to decide it. The transport binds `run_id` to the session.
MCP/function declarations apply upstream's existing OpenAI array-schema
normalization once, then add those two protocol fields to the common schema;
they do not teach an arm a different manipulation recipe. Released
task wiki/seed-plan text is supplied to every arm. Catalog and source hashes,
actual model requests, generated native configuration, package versions and
asset revisions are recorded per run.

RoboRSI's `done` ends its Engineer round and remains under its native Reviewer
coordinator. The other arms' `done` ends their episode. This is an intentional
native orchestration difference. The common service caps executed environment
calls and actual controller steps; RoboRSI additionally retains its own
requested-call/round budget accounting. Rejected requests and native `done`
claims remain visible in raw model/workspace evidence.

RoboRSI's `_dispatch_with_timeout` boundary is routed to the common synchronous
owner-thread dispatcher. Its legacy per-tool timeout wrapper is therefore not
active in this adapter; all arms use the common control/call limits and the
declared outer wall-clock deadline. Interrupted physical execution is journaled
as indeterminate and the episode stops. This is an execution-protocol adaptation,
separate from preserving the native planning, review and replanning decisions.

The first server smoke configuration uses the same upstream local perception
and analytic grasp fallback for all arms. SAM3 and GraspGen servers are disabled;
PyRoKi is a separate pinned CPU solver. In particular, a released skill requiring
finite 6-DoF GraspGen candidates may report failure in this configuration. These
small capped runs validate the framework, not the published full-perception
benchmark score. A campaign must explicitly freeze its desired perception
services and rerun the shared preflight for all arms.

Native OS isolation is provided by a bubblewrap allowlist: native runtime,
system libraries and only that run's home/workspace/session are mounted. Dataset,
simulator, scorer and provider credential paths are absent. The child receives
only a short-lived proxy credential. A plain changed working directory is not
accepted as isolation for a live native run.

Recorded observability is bounded by actual evidence: public Codex/Pi events,
RoboRSI hook boundaries, HTTP requests and true control steps. Unexposed native
internals are not inferred. Returned reasoning-token usage is recorded; hidden
reasoning text unavailable from the API is not reconstructed.
