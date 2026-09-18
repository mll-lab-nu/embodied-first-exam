"""cap-x robosuite (MuJoCo, Franka Panda) task families.

To add a family: register the cap-x exec-env class, its low-level env name and the privileged API
(see cap-x `capx/envs/tasks/__init__.py`), write a one-sentence `text`, then run
`python -m rcb.new_task --family <name> --seed N`. The oracle is cap-x's human-written reference code
(`<ExecEnv>.oracle_code`), so a family without one cannot ship (CI requires oracle reward 1).
"""
TASKS: dict[str, dict] = {
    "cube_stack": dict(
        exec_env="capx.envs.tasks.franka.franka_pick_place.FrankaPickPlaceCodeEnv",
        low_level="franka_robosuite_cubes_low_level",
        apis=["FrankaControlPrivilegedApi"],
        text="Stack the red cube on top of the green cube with the Franka arm, then release it so it stays stacked.",
        simulator="robosuite", robot="franka-panda", image="robosuite",
    ),
}
