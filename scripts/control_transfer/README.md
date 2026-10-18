# roboEngineer Control Transfer

This implementation is roboEngineer's Control Transfer runtime ([docs/benchmarks/roboengineer.md](../../docs/benchmarks/roboengineer.md)), `eai-policy/1.1`, listed in `scripts/roboengineer/exported.toml`. `python3 -m scripts.control_transfer.gen_tasks render|check` writes the 26 Control Transfer tasks into `tasks/` (`roboengineer-<family>-iNN-standard`, names in `packaging.py`).

Neural Landing (`scripts/quadrotor_landing/`) has its own generator and service.

The shipped families are the Neural Fly variants, AnyCar tracking / compact-lap / drift variants and four Go2 objectives (G1, the full-lap and sector circuits are source only). They share bounded deployment adaptation with separate training and evaluation processes. Linearbot whole-body tracking, spacecraft rendezvous and YAM ball catching remain local prototypes, not generated task families.
Nominal model knowledge is public. Realized evaluation parameters, evaluator assets, seeds, contacts, true trajectories,
reference searches and scores are private. Public development seed banks are reproducibility examples, never secret test banks.

Training code executes in the agent container. Only validated data-only policies cross into the simulator.
The G1 proposal uses mjlab/MuJoCo Warp GPU training; deployment is native CPU MuJoCo.
This measures simulation transfer, not performance on physical hardware.

`components/` contains imported environments and subsequent implementation changes; `component-provenance.json` records original import hashes, not current source hashes.
Robot assets are prepared separately, never downloaded by a running trial. User-provided Linearbot assets and restricted
Neural-Fly flight data are not redistributed in this repository.
