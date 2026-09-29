# DexVerse

Tabletop dexterous manipulation with a multi-fingered hand: grasping, tool use, articulated objects, precision
insertion, bimanual and long-horizon tasks. Status: candidate, not integrated; only a subset would be taken.

| | |
|---|---|
| upstream | [DexVerse](https://github.com/ycyao216/DexVerse) ([arXiv 2607.08751](https://arxiv.org/abs/2607.08751), 2026-07), code BSD-3, assets CC-BY-4.0 on Hugging Face (not gated) |
| simulator | Isaac Sim 5.1 + Isaac Lab 2.3.2 (PhysX), the same stack as RoboLab; needs an RTX GPU even headless |
| robot | floating Shadow hand only (the paper's arm + other-hand combinations are not released): 28-D absolute joint targets (6 wrist, 22 finger), 56-D bimanual |
| control | 60 Hz, 20 s episodes (1200 steps) |
| score | a task-specific success predicate ends the episode; pass = it fires before the timeout |

## Tasks: 100 registered

| category | n | tasks |
|---|---|---|
| contact-rich | 8 | NutThread, InsertPeg, InsertPen, InsertPipette, PlugCharger, GearMesh, PickFromClutter, PickThinObjectFromContainer |
| non-prehensile | 5 | PushT, PushSphereUpSlope, PushSmallSphereObstacleSlope, PivotLargeCuboidAgainstWall, TakeBookOffShelf |
| functional | 10 | HammerStrike, DrillApply, PourMug, PourCan, PourWineGlass, RemoveCupFromRack, Grasp{Bleach, Cup, Kettle, Pan} |
| articulation | 22 | SlideUtilityKnife, SqueezeScissors, UnscrewCap, OpenLaptop, OpenFaucet, OpenMicrowave, OpenDrawer, … |
| grasping | 6 | PickCube, StackCube, PickUpStick, RelocateObject, RelocateSphere, GraspTwoItems |
| bimanual | 5 | Handover, Lift{Tray, Basket, Carton, DutchOven} |
| long-horizon | 5 | MakeCoffee, CookFoods, OvenBakeSalmon, MicrowaveRetrievePlace, TrashDrawerSortSimple |
| multi-goal | 39 | an articulation step followed by a pick/pour/relocate (e.g. OpenMicrowavePourMug) |

Upstream evaluated 19 tasks, imitation learning only (50 teleoperated demos each): mean success π0.5 0.34, DP3 0.34,
DP 0.32; SlideUtilityKnife and PushT are 0 for every method. The contact-rich insertion tasks other than InsertPen
have no published numbers.

## Fit for limited mode

- Sensors: a fixed third-person camera, a palm (wrist) camera, two optional side cameras, hand joint positions,
  fingertip contact; goal markers are always rendered.
- The floating hand is not a real robot; the arm + hand versions would fit better once released.

Measured (2026-09-28, RTX 4090, 16 tasks): all build, nop passes none; CPU physics 136–490 steps/s without cameras,
56–86 with them. A fresh process replays bit-exactly, but a replay after `reset()` in the same process drifts
(5 mm on CPU, cm on GPU), so a reset has to restart the simulator (~5–10 s warm; the first launch takes 71 s).
Isaac's cloud assets (materials, Factory nut and bolt) are fetched at runtime and must be cached for offline runs.

## Recommended tasks (limited)

| task | the hand must |
|---|---|
| NutThread | start a nut on a bolt and turn it at least 3/8 of a turn, centred |
| InsertPen | put a pen into a pen holder |
| PlugCharger | push a charger's prongs into a socket |
| GearMesh | slide a gear onto its shaft so it meshes with the others |
| PushT | push a T-block until it covers at least 90% of the goal T |
| SlideUtilityKnife | hold a utility knife with one hand and slide the blade out with the other |
| UnscrewCap | hold a centrifuge tube with one hand and unscrew its cap with the other |
| LongHorizon-MakeCoffee | take the mug, pour milk into it, set it under the machine, turn the switch |
