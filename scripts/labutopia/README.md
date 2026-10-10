# scripts/labutopia

Sources of the LabUtopia tasks (`tasks/labutopia-<family>-i00-{privileged,standard}`); notes in `docs/benchmarks/labutopia.md`.

| file | what |
|---|---|
| `generate.py` | writes the 18 task directories from everything below (`--check`: `tasks/` is what it writes) |
| `families.json` | per family: LabUtopia's config and level, the instance's seed, the goal (privileged and standard wording), the scene, the inventory |
| `instances/<family>.json` | the frozen instance: seed, placement and start-state hashes, action layout, cameras, the rule, the reference's size and final-state hash (written by `make_facts.py`) |
| `oracles/<family>.npz` | the reference rows (`actions`, float32, 18 per row): LabUtopia's scripted controller, one row per 1/60 s control step |
| `make_facts.py` | runs in the image with a GPU: `--check` (instances, references in two fresh processes), `--controls` (parts of the reference and idling score 0; how often random motions and other families' references succeed), `--upstream DIR` (rebuild instances and references), `--scan SEEDS` (LabUtopia's controller and the rule, seed by seed) |
| `kill_test.sh` | crash-recovery acceptance test of one standard task (kill the service mid-episode, resume, grade) |
| `shared/rcb_labutopia.py` | the tooling, copied into every task: `Session` (privileged API, the grader's replay, the service's simulator), the rules, the arm's kinematics |
| `shared/grade.py`, `test.sh`, `solve.sh`, `oracle_replay.py` | privileged verifier and oracle |
| `shared/standard/server.py` | the eai-standard/2.2 adapter (the layer itself is `scripts/eai_standard/`) |
| `shared/standard/finalize.sh`, `grade.py`, `test.sh`, `solve.sh`, `oracle_stream.py` | standard collect hook, verifier and oracle |

## The image
`images/labutopia/`: LabUtopia at its pinned commit on Isaac Sim 6.1.0 with every pip package pinned, its scripted
controllers removed in the layer that clones it (`strip_solutions.py`), and a mirror of the 64 files that LabUtopia
and Isaac Sim would load from NVIDIA's asset server at run time (`nvidia_assets.sha256`: the Franka, a cabinet, four
materials). `BUILD_ONLY` (Isaac Sim may not be redistributed): each host builds it, about 25 minutes, 40 GB:

    docker build -f images/labutopia/Dockerfile -t ghcr.io/mll-lab-nu/eai-labutopia:$(cat images/labutopia/VERSION) .

## Checks (no checkout of LabUtopia needed; an RTX-class GPU is)
    python3 scripts/labutopia/generate.py --check
    docker run --rm --gpus all --shm-size 8g --network none -v $PWD/scripts/labutopia:/w:ro \
        ghcr.io/mll-lab-nu/eai-labutopia:$(cat images/labutopia/VERSION) \
        sh -c "python /w/make_facts.py --check && python /w/make_facts.py --controls"
    bash scripts/labutopia/kill_test.sh tasks/labutopia-pick-i00-standard

## Rebuilding instances and references
Needs LabUtopia at the image's commit **with** its controllers (the image has none), mounted read-only:

    git clone https://github.com/Rui-li023/LabUtopia /path/to/LabUtopia && git -C /path/to/LabUtopia checkout 8df7278
    docker run --rm --gpus all --shm-size 8g -v $PWD/scripts/labutopia:/w -v /path/to/LabUtopia:/upstream:ro \
        ghcr.io/mll-lab-nu/eai-labutopia:$(cat images/labutopia/VERSION) python /w/make_facts.py --upstream /upstream
    python3 scripts/labutopia/generate.py && (cd tasks && harbor add --scan .)

The container runs as root (Isaac Sim's caches are in its package directory): give `instances/` and `oracles/` back
to your user afterwards (`chown`). No LFS pull is needed for the mounted checkout: only its Python code is used, the
scene assets come from the image. Two rebuilds on one host give the same hashes and the same reference rows; only
`steps_per_s` (a wall-clock measurement, one significant digit) can differ.

## Adding a family
A family is a LabUtopia config whose scripted controller solves it through joint targets alone (the stirring tasks
do not: their controllers move the glass rod by writing its position). Write its rule as a class in
`shared/rcb_labutopia.py`, a copy of the success check in the controller, and add it to `FAMILIES`; write its texts in
`families.json`; pick the seed with `make_facts.py --scan` (the smallest on which the controller succeeds and the rule
agrees with its verdict); rebuild as above. Then run `make_facts.py --controls` and read its counts: a task that
random arm motions solve is not one (the two closing tasks were left out for that, `docs/benchmarks/labutopia.md`). A change to anything under `shared/` changes every task's digest:
regenerate and re-run the oracle and `nop` evidence.
