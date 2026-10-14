# Experimental control-transfer tasks

This implementation belongs to the [roboEngineer multi-round proposal](../../experimental/roboengineer/README.md). It is not an accepted standard-mode protocol. Generated packages live under `experimental/roboengineer/tasks/`, outside the accepted dataset; the generator refuses the repository's `tasks/` directory. Main's `docs/PROTOCOL.md` and shared checks remain authoritative.

Neural Lander is the display name of `quadrotor-landing-*`; existing IDs and frozen run artifacts stay stable.

The active proposal covers Neural Fly variants, AnyCar tracking/circuit/drift variants, G1 training and transfer, and four Go2 objectives. They share bounded deployment adaptation with separate training and evaluation processes. Linearbot whole-body tracking, spacecraft rendezvous and YAM ball catching remain local prototypes, not generated task families.
Nominal model knowledge is public. Realized evaluation parameters, evaluator assets, seeds, contacts, true trajectories,
reference searches and scores are private. Public development seed banks are reproducibility examples, never secret test banks.

Training code executes in the agent container. Only validated data-only policies cross into the simulator.
The G1 proposal uses mjlab/MuJoCo Warp GPU training; deployment is native CPU MuJoCo.
This measures simulation transfer, not performance on physical hardware.

`components/` contains imported environments and subsequent implementation changes; `component-provenance.json` records original import hashes, not current source hashes.
Robot assets are prepared separately, never downloaded by a running trial. User-provided Linearbot assets and restricted
Neural-Fly flight data are not redistributed in this repository.
