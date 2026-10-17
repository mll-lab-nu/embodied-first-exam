# Asset and reference provenance

## Product references

- Avery item 05806, official product page:
  https://www.avery.com/products/binders/05806
  Documents white cover, 1-inch round rings, 1.4-inch spine, two interior pockets,
  back-mounted rings and 5.5 by 8.5-inch paper.
- Avery mini-binder specification:
  https://www.avery.com/help/article/mini-binders
  Documents nominal 9 by 7-inch panels. The marketing photograph displays
  slightly larger outer dimensions; the reconstruction uses nominal panels.
- Official product photograph MEDIA03:
  https://img.avery.com/web/products/binders/77711-05806-00450_i2606%20MEDIA03
  Inspected ring halves, chrome backplate, rivets and two booster paddles.
- Standard toggle-plate/spring-housing mechanism description and figures:
  https://patents.google.com/patent/US2061676A/en
  The documented ordinary two-plate spring-cover toggle principle informs the
  reduced mechanism. The patent's additional locking improvements are not
  attributed to Avery 05806. Avery does not publish internal spring CAD or
  force-displacement measurements, so the precise internal linkage and spring
  calibration remain explicitly approximate.
- MuJoCo native flex and shell elasticity documentation:
  https://mujoco.readthedocs.io/en/3.3.6/XMLreference.html

Product photographs and downloaded HTML are evidence-only reference snapshots,
not licensed runtime texture assets. The binder and punched-paper topology are
original task-owned geometric reconstructions. No manufacturer mesh is copied.

## Existing licensed robot platform

Read-only imports use `scripts/everyday_dexterity/tianji_model.py` and
`hand_models.py`, with public project-prepared Tianji geometry and inertia
provenance in `images/everyday_dexterity/assets/tianji/PROVENANCE.json`.
The complete arm geometry comes from DexForce's public Tianji asset
(Apache-2.0) and public Genesis link inertias (MIT), as declared by that manifest.
Sharpa Wave hand geometry comes from `images/dexhand/assets/hand/right_hand.xml`
and its existing project license/provenance. Each hand keeps 22 genuine
articulated joints and 22 native actuator entries. The shared hand module
reflects the right-hand geometry for the left side.

Actual previously accepted Sharpa sweeping and paper-folding frames were
inspected for complete-arm geometry, background, materials and readable contact
framing. The old Robotiq coffee scene was inspected before the newest embodiment
correction and supplies only layout context. It cannot validate T37 morphology
or physics. Unused copied Robotiq preparation is preserved under the evidence
directory's `rejected-robotiq-preparation`; it is not imported by this scene.
