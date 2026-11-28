# Embodied First Exam task protocol

Embodied First Exam (EFE; [repository](https://github.com/mll-lab-nu/embodied-first-exam),
[site](https://www.embodied-first-exam.ai), [how to contribute](https://www.embodied-first-exam.ai/contribute/)) is a
set of Harbor tasks. In each task a coding agent controls a simulated robot in a frozen scene. A task runs in one of
three modes. In **privileged** mode the agent owns the simulator and hands in a trajectory or code, which a separate
verifier replays. In **standard** mode the robot is a service the agent cannot open: the agent reaches it over HTTP
(or through MCP tools), and the service grades the live episode. **Realtime** mode is standard mode on a clock that
does not stop. Every standard and realtime service speaks one wire protocol, `eai-standard/3.0`. What a service offers
beyond the base protocol is listed by the capabilities in its `/spec`.

The documents in this folder are the protocol:

| Document | What it covers |
|---|---|
| [invariants.md](invariants.md) | The eight invariants (H.1-H.8). They bind every task and every run. |
| [tasks.md](tasks.md) | The task format: directory layout, `task.toml`, `instruction.md`, `README.md`, modes, seeds, grading, `DIGEST`, and the CI check for each rule. |
| [eai-standard.md](eai-standard.md) | The `eai-standard/3.0` wire protocol, by endpoint and by capability, and the MCP tools. |
| [eai-standard.openapi.yaml](eai-standard.openapi.yaml) | The same HTTP interface as OpenAPI 3.1 (`x-eai-capability` marks what each part belongs to). |
| [resources.md](resources.md) | Resource caps per container: where they are written, how they are chosen, who enforces them. |
| [running.md](running.md) | Running evaluations: official runs, seeds, network, reruns, results, the agent's time. |
| [leakage.md](leakage.md) | Where answer keys survive in what a task ships, and how they are removed. |

Related documents:

- [../TAXONOMY.md](../TAXONOMY.md): the values of the `[metadata]` fields, task names and run ids.
- [../REVIEWING.md](../REVIEWING.md): how maintainers review a pull request.
- [../operations.md](../operations.md): podman hosts, base images and the usage gateway.
- [../../embodied_first_exam/standard/README.md](../../embodied_first_exam/standard/README.md): how the service layers
  implement the protocol.
- `tasks/<benchmark>/README.md`: each benchmark's own choices.

**What binds and what recommends.** The invariants in [invariants.md](invariants.md) bind. No task value, declaration
or benchmark document can override them. The required CI job `invariants` fails a pull request that breaks one, and
the runner refuses a run that would. Everything else in these documents is a convention. A task may depart from a
convention when it says so where its readers look (its `task.toml`, its README or `tasks/<benchmark>/README.md`). CI
reports such a departure as an advisory warning, never as a failure.

**Changing the protocol.** Open a protocol-change issue first. Then send one pull request that updates the documents,
the reference implementation and an example task.
