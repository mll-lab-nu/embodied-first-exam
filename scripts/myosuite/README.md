# scripts/myosuite — MyoSuite tasks (10 families x 2 modes)

```bash
python3 scripts/myosuite/generate.py            # render tasks/myosuite-*-i00-{privileged,standard} (standard library only)
python3 scripts/myosuite/generate.py --check    # exit 1 if tasks/ differs from a fresh render
# in the image (re-reads MyoSuite's code and parameters, re-checks every instance hash and reference):
docker run --rm --network none --user $(id -u):$(id -g) -e HOME=/tmp -v $PWD:/repo -w /repo \
    ghcr.io/mll-lab-nu/eai-myosuite:$(cat images/myosuite/VERSION) python scripts/myosuite/make_facts.py --oracles
```

| path | what |
|---|---|
| `instances/<family>.npz` | the frozen instance: the family's MyoSuite env after `seed(0)`, `reset(seed=0)` (`shared/rcb_myosuite.py make-instance`): MuJoCo integration state, the model arrays resets edit, the env's Python state, and its state hash |
| `instances/<family>.json` | the facts the task texts quote (`make_facts.py`, in the image) |
| `oracles/<family>.npy` | reference rows (key_turn, obj_hold, arm_reach): MyoSuite's NPG baseline policies (`myosuite/agents/baslines_NPG/`, in the MyoSuite wheel, removed from the image) rolled out from the instance and cut at the first success; float32-exact |
| `shared/rcb_myosuite.py` | the task tooling (privileged `Session`, replay CLI), copied into every task (privileged `environment/` and `tests/`, standard `environment/sim/`) |
| `shared/grade.py`, `test.sh`, `solve.sh`, `oracle_replay.py` | privileged verifier and oracle |
| `shared/standard/` | the eai-standard/2.2 adapter `server.py`, the collect hook `finalize.sh`, the verifier and the oracle stream |

The 2.2 layer itself (`rcb_limited.py`, `rcb_client.py`, `rcb1.py`, `run.sh`, the client image and pins) is copied
unchanged from `scripts/eai_standard/`. Benchmark notes, success rules and the human-review evidence:
[docs/benchmarks/myosuite.md](../../docs/benchmarks/myosuite.md).
