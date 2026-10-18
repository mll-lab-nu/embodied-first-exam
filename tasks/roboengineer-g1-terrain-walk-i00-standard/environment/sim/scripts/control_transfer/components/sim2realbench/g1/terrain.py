"""Operator-only terrain construction and frozen case banks. Never copy to the agent image."""

import math


KINDS = ("flat", "slope", "rough", "steps")


def make_spec(index):
    """Separate placements/noise on one fixed hidden plant, including twelve held-out cases."""
    if type(index) is not int or not 0 <= index <= 999:
        raise ValueError("Invalid instance")
    plant_seed = 10000 + index * 1000 + 100

    def bank(count, offset):
        return [
            {
                "plant_seed": plant_seed,
                "episode_seed": 170003 + index * 1000 + offset + i,
                "terrain": KINDS[i % 4],
                "duration": 20.0,
                "speed": (0.5, 0.6, 0.65)[i % 3],
            }
            for i in range(count)
        ]

    return {
        "schema": "control-transfer-instance/2",
        "transfer_track": "same-plant",
        "family": "g1",
        "index": index,
        "rounds": 3,
        "adaptation": bank(4, 0),
        "held_out": bank(12, 100),
    }


def terrain_parameters(kind, episode_seed):
    import numpy as np

    if kind not in KINDS:
        raise ValueError("Unknown terrain class")
    rng = np.random.default_rng(np.random.SeedSequence([episode_seed, 531]))
    return {
        "kind": kind,
        "slope": float(rng.uniform(0.04, 0.08)),
        "rough_amplitude": float(rng.uniform(0.012, 0.028)),
        "step_height": float(rng.uniform(0.025, 0.05)),
        "step_width": float(rng.uniform(0.6, 0.9)),
        "terrain_seed": int(rng.integers(0, 2**31)),
    }


def build_model(scene, terrain):
    """Flat preserves the source plane. Non-flat courses have a 1 m level starting area."""
    import mujoco
    import numpy as np

    spec = mujoco.MjSpec.from_file(str(scene))
    kind = terrain["kind"]
    if kind not in KINDS:
        raise ValueError("Unknown terrain class")
    for geom in spec.geoms:
        if geom.type == mujoco.mjtGeom.mjGEOM_PLANE:
            geom.group = 5
            geom.rgba = [0.36, 0.38, 0.36, 1]
            geom.material = ""
            if kind in ("rough", "slope"):
                geom.pos[2] = -0.08  # Avoid coincident plane/heightfield contacts in the launch area.
    if kind in ("slope", "rough"):
        # x covers [-3, 21], y [-3, 3]. MuJoCo columns are x, rows y.
        nx, ny = 481, 121
        x = np.linspace(-3, 21, nx)
        y = np.linspace(-3, 3, ny)
        xx, yy = np.meshgrid(x, y)
        if kind == "slope":
            heights = terrain["slope"] * np.clip(xx - 1, 0, 4)
        else:
            rng = np.random.default_rng(terrain["terrain_seed"])
            # Smooth random roughness with 0.2–0.6 m wavelengths and a level launch area.
            heights = np.zeros_like(xx)
            for _ in range(6):
                heights += np.sin(xx * rng.uniform(10, 30) + rng.uniform(0, 2 * math.pi)) * np.cos(
                    yy * rng.uniform(6, 22) + rng.uniform(0, 2 * math.pi)
                )
            heights *= terrain["rough_amplitude"] / 6 * np.clip((xx - 1) / 0.5, 0, 1)
        low, high = float(heights.min()), float(heights.max())
        scale = max(high - low, 1e-6)
        spec.add_hfield(
            name="terrain_course",
            nrow=ny,
            ncol=nx,
            size=[12, 3, scale, 0.1],
            userdata=((heights - low) / scale).ravel().tolist(),
        )
        spec.worldbody.add_geom(
            name="terrain_course",
            type=mujoco.mjtGeom.mjGEOM_HFIELD,
            hfieldname="terrain_course",
            pos=[9, 0, low],
            group=5,
            rgba=[0.46, 0.43, 0.38, 1],
            friction=[1, 0.005, 0.0001],
        )
        model = spec.compile()
        model.hfield_data[:] = ((heights - low) / scale).ravel()
    else:
        if kind == "steps":
            # Six ascent/descent risers, then level floor; real vertical faces, not a slope approximation.
            width, height = terrain["step_width"], terrain["step_height"]
            for i, level in enumerate((1, 2, 3, 3, 2, 1)):
                spec.worldbody.add_geom(
                    name=f"terrain_step_{i}",
                    type=mujoco.mjtGeom.mjGEOM_BOX,
                    pos=[1 + (i + 0.5) * width, 0, level * height / 2],
                    size=[width / 2, 3, level * height / 2],
                    group=5,
                    rgba=[0.46 + 0.03 * (i % 2), 0.43, 0.38, 1],
                    friction=[1, 0.005, 0.0001],
                )
        model = spec.compile()
    return model


def ground_height(model, data, x, y):
    """Privileged collision-geometry ray; used only for fall detection, never actor input."""
    import mujoco
    import numpy as np

    distance = mujoco.mj_ray(
        model,
        data,
        np.array([x, y, 5.0]),
        np.array([0.0, 0.0, -1.0]),
        np.array([0, 0, 0, 0, 0, 1], dtype=np.uint8),
        1,
        -1,
        np.array([-1], dtype=np.int32),
    )
    return 5.0 - distance if distance >= 0 else 0.0
