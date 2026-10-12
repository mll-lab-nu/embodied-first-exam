# Handover for pingyue

This branch (`dev/pingyue_handover`) holds two **separate** tasks for pingyue. They share nothing but the repository. Questions about either go to **Qineng**.

## 1. YAMLab port of the old RoboTangle tasks: [`yamlab_port/`](yamlab_port/)

Port the old, pre-MuJoCo RoboTangle task families (Genesis release `robotangle-r2`) into [YAMLab](https://github.com/ARISE-Initiative/yamlab): Isaac Sim 5.1 + Isaac Lab 2.3.2, bimanual YAM. The robot and its settings stay unchanged; only the tasks change; each tier needs a scripted oracle.

**Done**, each with an oracle from reset, bit-identical replays, failing nop/naive negatives and a video:
- fiber_bundling very_easy and easier;
- knot_untying very_easy and easier;
- cast_keyhole very_easy;
- buzz_wire_3d very_easy;
- rope_threading easy.

**Still open:** fiber easy, knot easy/medium, buzz easier, rope medium. cast_keyhole easier was closed as infeasible for the YAM.

**Start with [`yamlab_port/HANDOVER.md`](yamlab_port/HANDOVER.md).** It covers the goal and rules, setup on your machine, per-family status with next steps, the definition of done, and the gotchas.

## 2. Design consultation: RoboTangle knot_untying placement: [`knot_placement/`](knot_placement/)

This is a separate design question about the current, redesigned RoboTangle `knot_untying` task. It is not the YAMLab port. Once the rope is untied, how should the robot lay it into its goal strip, and should the goal region or curb design change so that placement is legal and reasonable without making the task trivial?

**Start with [`knot_placement/README.md`](knot_placement/README.md)** and open `viewer.html` in a browser. `params.json` holds every number. The packet is maintained by the RoboTangle knot work and may be refreshed in this branch.
