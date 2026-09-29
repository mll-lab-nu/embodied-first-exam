# Candidate benchmarks

Surveyed 2026-09-27/28 for what the current set lacks; limited mode is the priority. A benchmark gets its own page
here once we start on it.

| benchmark | group · venue | simulator | what it adds | limited fit | page |
|---|---|---|---|---|---|
| KinDER | Princeton (T. Silver), Georgia Tech, CMU · RSS 2026 | MuJoCo / PyBullet / Pymunk, CPU | physical reasoning: sweep, scoop, toss, balance, push obstacles | good (Dynamic3D) | [kinder.md](kinder.md) |
| DexVerse | UNC, HKU, Berkeley · arXiv 2026-07 | Isaac Lab 2.3.2, RTX | multi-fingered hand: threading, insertion | medium (floating hand) | [dexverse.md](dexverse.md) |
| RoboMME | Michigan (J. Chai), Stanford (C. Finn) · ICML 2026 | ManiSkill3 | memory: counting, object permanence, swaps | good | |
| Robot Air Hockey | TU Darmstadt (J. Peters) · NeurIPS 2024 D&B | MuJoCo, CPU | fast dynamics against an opponent, safety limits | good (mocap, as on the real robot) | |
| LSY Drone Racing | TUM (A. Schoellig) · Crazyflow 2026 | JAX + MuJoCo, CPU | aerial: minimum-time flight, gates revealed up close | good (mocap, as on the real robot) | |
| ActiveArena | PKU, Beihang · arXiv 2026-09 | RoboTwin 2.0 | active perception: move head and torso to find information | good | |
| Neverwhere | MIT (P. Isola), UCSD (X. Wang) · IROS 2026 | MuJoCo + Gaussian splats, CUDA | visual quadruped parkour in reconstructed real scenes | good | |
| DOMINO | ECCV 2026 | RoboTwin 2.0 | moving targets | medium (scripted motion) | |
| TriFinger (RRC) | MPI-IS · 2020–22 | PyBullet, CPU | camera-only dexterous rearrangement | good, but old | |
| LeHome | ICRA 2026 challenge | Isaac Sim 5.1 | garment folding on an SO-101 twin | good, heavy | |
| ManiSkill-ViTac 2025 · UniVTAC | CVPR 2025 workshop · arXiv 2026-02 | SAPIEN + IPC · Isaac Sim | touch-driven insertion | good | |
| PolaRiS | arXiv 2025-12 | Isaac Sim + Gaussian splats | photoreal DROID-Franka twin (6 scenes) | good | |

Full mode only: MyoChallenge 2025 and MSK-Bench (musculoskeletal control; the ball's state is privileged, no
camera), OopsieVerse (damage-aware success on BEHAVIOR and RoboCasa), Verti-Bench (off-road, Chrono).
Not now: IMBench, WireCraft (code unreleased), DynaBARN (ROS1, real-time Gazebo), Bench2Drive (saturated,
NC-ND). Related work, not to add: EmbodiedSWE-Bench (coding agents write `solve(env)` in Isaac Lab, 2026-09) and
CaP-X (the primitives our robosuite task uses).
