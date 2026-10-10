# scripts/autobio

Sources of the AutoBio tasks (`tasks/autobio-<family>-i00-{privileged,standard}`); notes in `docs/benchmarks/autobio.md`.

| file | what |
|---|---|
| `generate.py` | writes the 18 task directories from everything below (`--check`: `tasks/` is what it writes) |
| `families.json` | the texts: per family the goal (privileged and standard wording), the scene, the inventory, AutoBio's level |
| `instances/<family>.json` | the frozen instance: seed, model and start-state hashes, action layout, cameras, the reference's size and final-state hash (written by `make_facts.py`) |
| `oracles/<family>.npz` | the reference rows (`actions`, float32): AutoBio's scripted expert, one row per 2 ms control step |
| `make_facts.py` | runs in the image: `--check` (hashes, references in two fresh processes), `--controls` (wrong trajectories score 0), `--upstream DIR` (rebuild instances and references) |
| `kill_test.sh` | crash-recovery acceptance test of one standard task (kill the service mid-episode, resume, grade) |
| `shared/rcb_autobio.py` | the tooling, copied into every task: `Session` (privileged API, the grader's replay, the service's simulator) |
| `shared/grade.py`, `test.sh`, `solve.sh`, `oracle_replay.py` | privileged verifier and oracle |
| `shared/standard/server.py` | the eai-standard/2.2 adapter (the layer itself is `scripts/eai_standard/`) |
| `shared/standard/finalize.sh`, `grade.py`, `test.sh`, `solve.sh`, `oracle_stream.py` | standard collect hook, verifier and oracle |

## The image
`images/autobio/`: AutoBio at its pinned commit with every pip package pinned, its scripted experts removed in the layer
that clones it (`strip_experts.py`). `BUILD_ONLY`: AutoBio states no licence, so each host builds the image from
AutoBio's public repository:

    docker build -f images/autobio/Dockerfile -t ghcr.io/mll-lab-nu/eai-autobio:$(cat images/autobio/VERSION) .

## Checks (no checkout of AutoBio needed)
    python3 scripts/autobio/generate.py --check
    docker run --rm --network none -v $PWD/scripts/autobio:/w:ro -e HOME=/tmp ghcr.io/mll-lab-nu/eai-autobio:$(cat images/autobio/VERSION) \
        sh -c "python /w/make_facts.py --check && python /w/make_facts.py --controls"
    bash scripts/autobio/kill_test.sh tasks/autobio-pickup-i00-standard

## Rebuilding instances and references
Needs AutoBio at the image's commit **with** its experts (the image has none), mounted read-only:

    git clone https://github.com/autobio-bench/AutoBio /path/to/AutoBio && git -C /path/to/AutoBio checkout 0850421
    docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v $PWD/scripts/autobio:/w -v /path/to/AutoBio:/upstream:ro \
        ghcr.io/mll-lab-nu/eai-autobio:$(cat images/autobio/VERSION) python /w/make_facts.py --upstream /upstream/autobio
    python3 scripts/autobio/generate.py && (cd tasks && harbor add --scan .)

Two rebuilds on one host give the same hashes and the same reference rows; only `steps_per_s` (a wall-clock
measurement, one significant digit) can differ.

## Adding a family
A family is an AutoBio task with a real `check()` and an expert: add it to `FAMILIES` in `shared/rcb_autobio.py`
(module, class, rule), write its texts in `families.json`, rebuild as above. A change to anything under `shared/`
changes every task's digest: regenerate and re-run the oracle and `nop` evidence.
