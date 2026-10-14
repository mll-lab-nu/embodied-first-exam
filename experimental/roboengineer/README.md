# roboEngineer multi-round policy proposal

This is an **experimental proposal**, outside the accepted `tasks/` registry and its dataset manifest. Main's [Task Protocol](../../docs/PROTOCOL.md) remains authoritative. The existing `eai-policy/1.x` interface is not an accepted alternative to `eai-standard/2.x`.

The proposal preserves nominal training, three deployment-feedback rounds, numeric-only policy admission, noisy observations/video, and private held-out evaluation. It includes 34 development packages and the prior task identities so recorded evidence stays traceable. Physics, controller ABIs and frozen instance banks are preserved. Metadata now includes main's seed declarations and an explicit experimental marker.

Read the [interface proposal](../../docs/POLICY_MODE.md), [compatibility matrix](../../docs/benchmarks/roboengineer-main-compatibility.md), and [embodiment roadmap](../../docs/benchmarks/roboengineer.md). Reference-controller success, Harbor runtime validation and admission to the accepted protocol are separate claims.

## Generate and check the experiment

From the repository root:

```bash
python3 -m scripts.control_transfer.gen_tasks render
python3 -m scripts.quadrotor_landing.gen_tasks render
python3 experimental/roboengineer/check.py
```

The generators default to this directory's `tasks/`. They refuse destinations under the repository's accepted `tasks/`. Control Transfer's optional `--output-root` can select another experimental export directory. `check.py` checks generated-package identity, seed metadata and the proposal's public/private boundary. It does **not** accept this interface into main or weaken main's checks.

For numerical and service tests, use the prepared CPU MuJoCo 3.5/NumPy environment with software rendering and the required operator assets:

```bash
python -m unittest discover -s scripts/control_transfer/tests -p 'test_*.py' -v
python -m unittest discover -s scripts/quadrotor_landing/tests -p 'test_*.py' -v
```

Tests report missing asset-dependent coverage explicitly. A local experimental Harbor run takes an explicit package path, for example `harbor run -p experimental/roboengineer/tasks/control-transfer-anycar-i00-standard -a oracle`. Image preparation and resource requirements still apply; this is not an official protocol-compliant run.

## Boundaries and history

- `cutoffs.toml` and `resources.toml` apply only to this proposal. In particular, the historical 129600-second long-lap budget is **not** an exception in main's cutoff table.
- `scripts/control_transfer/proposal.py` loads main's normalizer into a separate module instance with proposal-local configuration. It does not modify shared registries, allowlists or caps.
- `migration.json` maps each former `tasks/` path to its experimental location and records the preserved instance digest. Old task IDs, version tokens and evidence remain development history, not naming exceptions for future accepted tasks.
- Generated source copies and verifier cache-identity payloads remain self-contained. Runtime isolation and anti-cheating checks are retained.
- A future shared protocol proposal and its task contribution need separate review under CONTRIBUTING. Native acceptance and human-review requirements are not waived by this experimental directory.

## Remaining development work

The relocation does not fix the previously audited Neural Landing restart/cutoff recovery defects, the older operator validator's smoke/reference assumptions, or the missing version-selectable image build path. It does not remove inactive prototypes or unnecessary private circuit catalogs. These remain engineering work within the experiment. No new controller, physics, native Harbor, or GPU-training acceptance is claimed by separating the proposal from main.
