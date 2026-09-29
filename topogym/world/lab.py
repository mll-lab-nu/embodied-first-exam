"""The single compact laboratory layout and its Genesis entity construction."""

BACKGROUND_ID = "compact_lab"


def compact_lab_layout() -> list[dict]:
    """Enclosed 3.8 x 3.4 m room; cameras and lights remain inside its shell.

    The older two-wall backdrop works only from one corner. A complete shell
    prevents newly placed cameras from seeing the photographic HDRI horizon.
    Room lights are supplied by the presentation config, below the ceiling.
    """
    names = []

    def box(name, pos, size, color, roughness=0.7):
        name = f"lab_{name}"
        names.append(
            dict(
                name=name,
                pos=list(pos),
                size=list(size),
                color=list(color),
                metallic=0.0,
                roughness=roughness,
                collision=False,
            )
        )

    # A solid floor above the original ground plane, with restrained tile seams.
    box("floor", (0, 0, 0.012), (3.9, 3.5, 0.02), (0.32, 0.37, 0.39))
    for i in range(-3, 4):
        box(
            f"grout_x_{i}",
            (i * 0.5, 0, 0.0225),
            (0.003, 3.4, 0.001),
            (0.45, 0.49, 0.50),
        )
        box(
            f"grout_y_{i}",
            (0, i * 0.5, 0.0225),
            (3.8, 0.003, 0.001),
            (0.45, 0.49, 0.50),
        )
    for sign in (-1, 1):
        box(
            f"wall_x_{sign}",
            (sign * 1.9, 0, 1.30),
            (0.10, 3.5, 2.60),
            (0.73, 0.76, 0.76),
        )
        box(
            f"wall_y_{sign}",
            (0, sign * 1.7, 1.30),
            (3.9, 0.10, 2.60),
            (0.79, 0.78, 0.74),
        )
        box(
            f"skirting_x_{sign}",
            (sign * 1.842, 0, 0.085),
            (0.016, 3.4, 0.13),
            (0.31, 0.37, 0.39),
        )
        box(
            f"skirting_y_{sign}",
            (0, sign * 1.642, 0.085),
            (3.8, 0.016, 0.13),
            (0.31, 0.37, 0.39),
        )
    box("ceiling", (0, 0, 2.60), (3.9, 3.5, 0.10), (0.86, 0.86, 0.83))
    for i, x in enumerate((-0.60, 0.60)):
        box(
            f"ceiling_panel_{i}", (x, 0, 2.535), (0.50, 1.30, 0.025), (0.96, 0.96, 0.93)
        )

    # Shallow storage occupies the rear wall without encroaching on the table.
    for i, y in enumerate((-0.65, 0.0, 0.65)):
        box(f"cabinet_{i}", (-1.57, y, 0.46), (0.50, 0.62, 0.88), (0.30, 0.39, 0.42))
        box(f"door_{i}", (-1.309, y, 0.47), (0.018, 0.58, 0.79), (0.55, 0.61, 0.62))
        box(
            f"handle_{i}",
            (-1.289, y, 0.76),
            (0.024, 0.18, 0.014),
            (0.18, 0.21, 0.22),
            0.35,
        )
    box("counter", (-1.55, 0, 0.925), (0.56, 1.96, 0.04), (0.79, 0.80, 0.77), 0.45)
    box("raceway", (-1.836, 0, 1.17), (0.025, 2.10, 0.05), (0.88, 0.88, 0.84))
    for i, y in enumerate((-0.55, 0.25, 0.85)):
        box(f"outlet_{i}", (-1.816, y, 1.17), (0.015, 0.07, 0.07), (0.36, 0.41, 0.41))
    box("board_frame", (0, 1.638, 1.65), (1.20, 0.04, 0.74), (0.31, 0.37, 0.38))
    box("board", (0, 1.613, 1.65), (1.15, 0.012, 0.69), (0.89, 0.89, 0.84), 0.5)
    box("board_tray", (0, 1.57, 1.27), (1.20, 0.09, 0.018), (0.31, 0.37, 0.38))
    # A closed door provides scale on the other visible wall; no sky opening.
    box("door_frame", (0.65, -1.638, 1.10), (0.87, 0.025, 2.12), (0.40, 0.45, 0.45))
    box("room_door", (0.65, -1.615, 1.10), (0.80, 0.02, 2.04), (0.70, 0.73, 0.71))
    box(
        "door_handle",
        (0.95, -1.59, 1.02),
        (0.10, 0.04, 0.016),
        (0.24, 0.28, 0.28),
        0.35,
    )
    return names


def add_lab(scene, manifest):
    import genesis as gs

    names = []
    for item in compact_lab_layout():
        name = item["name"]
        manifest.add(
            name,
            scene.add_entity(
                gs.morphs.Box(
                    pos=item["pos"], size=item["size"], fixed=True, collision=False
                ),
                material=gs.materials.Rigid(needs_coup=False),
                surface=gs.surfaces.Plastic(
                    color=item["color"],
                    metallic=item["metallic"],
                    roughness=item["roughness"],
                ),
                name=name,
            ),
        )
        names.append(name)
    return names
