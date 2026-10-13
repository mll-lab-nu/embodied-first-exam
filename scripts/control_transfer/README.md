# Control transfer tasks

Neural Lander is the display name of `quadrotor-landing-*`; existing IDs and frozen run artifacts stay stable.

Five additional families share bounded deployment adaptation with separate training and evaluation processes:
Neural Fly, Linearbot whole-body tracking, spacecraft rendezvous, YAM ball catching, and G1 training and transfer.
Nominal model knowledge is public. Realized evaluation parameters, evaluator assets, seeds, contacts, true trajectories,
reference searches and scores are private. Public development seed banks are reproducibility examples, never secret test banks.

Training code executes in the agent container. Only validated data-only policies cross into the simulator.
GPU training uses MuJoCo Warp (Linearbot) and mjlab (G1); deployment is native CPU MuJoCo.
This measures simulation transfer, not performance on physical hardware.

`components/` contains a frozen copy of the existing environments; `component-provenance.json` records original hashes.
Robot assets are prepared separately, never downloaded by a running trial. User-provided Linearbot assets and restricted
Neural-Fly flight data are not redistributed in this repository.
