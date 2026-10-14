# roboEngineer compatibility with main

The authoritative contract is [PROTOCOL.md](../PROTOCOL.md), taken unchanged from main commit `418a4542f452d4ac5b3272c5698e299055951131` (2026-10-14 alignment). This branch's former policy-mode exception and long-lap budget exception are not part of that contract. The existing [policy interface document](../POLICY_MODE.md) describes experimental code, not an approved extension.

## Current status: preserve multi-round as an experimental proposal

Main is merged. The user selected preservation of the multi-round design as an experimental proposal. All 34 packages now live under [experimental/roboengineer/tasks](../../experimental/roboengineer/tasks/), outside the accepted task registry and dataset manifest. They declare `[metadata.seeds]` using main's normalization rules: the existing `instance_seed` is the sole allowed default seed, and the oracle seed list follows the declared oracle level. No new plant or episode is admitted. Frozen simulator/verifier instance bytes, policy ABIs, physics and recorded evidence are unchanged by this move and metadata update.

The protocol, shared checks, normalization rules, cutoff/resource tables and taxonomy use main's implementations. If explicitly passed an experimental package, main's protocol check still rejects its `eai-policy/1.x` declaration. The four long-lap packages exceed main's 14400-second cap; their budgets live only in proposal-local configuration. No shared allowlist or spelling change hides these differences. Use the [explicit proposal checks](../../experimental/roboengineer/README.md) for package integrity; accepted-suite CI intentionally does not admit the proposal.

## Differences requiring an implementation or scope decision

| Main rule | Current roboEngineer implementation | Required treatment |
|---|---|---|
| D1, §2.3, §4: standard tasks use `eai-standard/2.1`, `/2.2` or `/2.4` | `eai-policy/1.0` and `/1.1`, with `describe`, `deploy` and `seal` | Implement an accepted interface, or retain the current design only as an explicitly experimental protocol proposal. |
| §4.2–4.3: standard endpoints and RCB1 binary responses; no base64 images in JSON | Custom endpoints and JSON feedback containing base64 JPEGs | A real transport/client migration is needed; changing metadata alone is incorrect. |
| §4.1: no simulator/code in the agent container; GPU on `sim` only | Public nominal simulation in the agent container; G1 GPU training there | The existing training design requires a protocol extension or a redesigned topology. |
| §4.5: one continuing episode, resets only by documented capability/exception | Three deployments over a fixed adaptation bank followed by private held-out grading | Preserve this as a proposed capability, or explicitly redesign the task lifecycle. Do not silently replace the user's multi-round objective. |
| §2.2: no version tokens in task names; standard/privileged twin rules apply | Sixteen historical version-bearing package names; policy tasks have no privileged twins | Preserve these IDs only in the experiment's migration map. Any later accepted tasks must satisfy the naming and twin rules then in main. |
| §2.3/§2.12: maximum 14400 seconds except main's documented exceptions | Four long-lap tasks use 129600 seconds | Keep the long-budget experiment outside an accepted suite unless the upstream contract changes. Compact tasks do not require this exception. |
| §2.4: common client base, simulator sidecar image and build rules | Nominal/training agent images and task-built private sidecars | Audit and migrate Docker topology as part of the interface decision. Existing container-isolation evidence is not a waiver. |
| §2.13: declared seed policy | Previously missing metadata | Fixed using main's normalizer, retaining the existing frozen banks. |
| D6, CONTRIBUTING: shared protocol changes and benchmark tasks reviewed separately | One branch includes shared policy checks, task generators and task packages | Separate any proposed shared extension from the task contribution. Main's protocol stays authoritative until an extension is accepted there. |

## Evidence and preservation

Native Harbor, exact replay and reference-controller evidence describes the implementation/version on which it was collected. It does not establish compliance with a different interface. Old receipts, videos, source hashes and task identities remain historical evidence and must not be relabeled as runs of a migrated task.

The branch audit originally reported success under this branch's extended checks. That statement is historical: main's unmodified checks are now the conformance baseline and expose the incompatibilities above. A passing seed check is not a passing protocol review.

Two possible routes preserve an honest review boundary:

1. Keep multi-round nominal training as a proposed capability, with the current code and records explicitly experimental and no claim of accepted standard-mode compliance.
2. Redesign the tasks around the accepted `eai-standard/2.x` transport, topology and episode semantics, with new conformance tests and new validation evidence.

The first route was selected: preserve the experiment without changing main's contract. The package relocation and explicit generation/check commands implement that boundary. No protocol extension has been accepted, no tasks have been redesigned as `eai-standard/2.x`, and no new native validation is claimed.
