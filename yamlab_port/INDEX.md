# yamlab_port index

| path | what |
|---|---|
| `HANDOVER.md` | **start here**: goal, setup, per-family status and next steps, definition of done, gotchas |
| `README.md` | what this is, plan summary, status table |
| `YAMLAB_NOTES.md` | study of YAMLab: robot, backend, task anatomy, deformables, scripting, headless, hosts |
| `PLAN.md` | per-family feasibility, tiers, goal checks, oracles, risks |
| `yamlab/` | (not in the branch) clone of ARISE-Initiative/yamlab @ ec0455d (MIT), unmodified |
| `robotangle_v1_stl/` | old geometry package (STL/layouts/start states), subset for the five ported families |
| `ref/topogym_2dafa5f/` | (not in the branch) git worktree (detached) of robot_coding_bench @ 2dafa5f2b = dev/jianwen topogym simulator source of the old release; read-only |
| `ref/rcb_main_4ff51fa/` | (not in the branch) git worktree (detached) of robot_coding_bench main @ 4ff51fa5b, last pre-MuJoCo main; read-only |
| `setup/vast_install.sh`, `vast_syslibs.sh` | native YAMLab install on vast (venv) + user-space libs and `env.sh` |
| `setup/vast_smoke.sh`, `vast_physics_smoke.py`, `vast_rtx_probe.*` | smoke tests: physics-only works; RTX probe crashes on vast |
| `setup/render_states.py` | faithful videos by state playback (dump on the vast stack, render with cameras via scene.reset_to) |
| `setup/ws_*.sh`, `ws_vaststack.sh` | ws render path: container wrapper, overlay, vast-identical venv |
| `tasks/COMMON_BRIEF.md` | rules and deliverables given to every task agent |
| `tasks/<family>/` | one folder per ported family (task agents' work) |

Remote mirrors: vast `/workspace/yamlab_port/` (venv, deps, yamlab clone, per-task run dirs, logs).
