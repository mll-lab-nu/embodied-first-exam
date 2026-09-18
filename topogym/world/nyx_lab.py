"""Shared laboratory backdrops, outside the manipulation area.

All dressing is fixed and collision-free. The original ground collision remains.
"""

import genesis as gs


def add_lab(scene, manifest, background: str) -> list[str]:
    if background == "checker":
        return []
    if background == "compact_lab":
        return add_compact_lab(scene, manifest)
    if background != "lab":
        raise ValueError("env.presentation.background must be lab, compact_lab or checker")
    names = []

    def box(name, pos, size, color, *, metallic=0.0, roughness=0.65):
        name = f"lab_{name}"
        manifest.add(name, scene.add_entity(
            gs.morphs.Box(pos=pos, size=size, fixed=True, collision=False),
            material=gs.materials.Rigid(needs_coup=False),
            surface=gs.surfaces.Plastic(color=color, metallic=metallic, roughness=roughness),
            name=name,
        ))
        names.append(name)

    # Floor slightly above the existing plane avoids coplanar rendering artifacts.
    box("floor", (0, 0, -0.009), (8, 8, 0.02), (0.14, 0.20, 0.23), roughness=0.7)
    for i in range(-7, 8):
        box(f"grout_x_{i}", (i * 0.5, 0, 0.0015), (0.005, 8, 0.001), (0.32, 0.37, 0.38))
        box(f"grout_y_{i}", (0, i * 0.5, 0.0015), (8, 0.005, 0.001), (0.32, 0.37, 0.38))
    box("wall_x", (-2.5, 0, 1.5), (0.10, 8, 3), (0.62, 0.68, 0.72))
    box("wall_y", (0, 2.6, 1.5), (8, 0.10, 3), (0.76, 0.74, 0.69))
    box("skirting_x", (-2.442, 0, 0.065), (0.016, 8, 0.13), (0.23, 0.28, 0.31))
    box("skirting_y", (0, 2.542, 0.065), (8, 0.016, 0.13), (0.23, 0.28, 0.31))

    # Storage cabinets behind the robot. Handles and toe kicks provide scale.
    for i, y in enumerate((-0.65, 0.0, 0.65, 1.30)):
        box(f"cabinet_{i}", (-2.12, y, 0.48), (0.60, 0.63, 0.88), (0.23, 0.31, 0.35))
        box(f"door_{i}", (-1.81, y, 0.49), (0.02, 0.59, 0.79), (0.39, 0.49, 0.53))
        box(f"handle_{i}", (-1.785, y, 0.79), (0.028, 0.19, 0.016),
            (0.12, 0.14, 0.15), metallic=0.6, roughness=0.3)
    box("counter", (-2.10, 0.325, 0.945), (0.68, 2.63, 0.04), (0.76, 0.78, 0.77), roughness=0.4)
    box("raceway", (-2.433, 0.3, 1.19), (0.03, 3.0, 0.065), (0.82, 0.83, 0.80))
    for i, y in enumerate((-0.5, 0.3, 1.1)):
        box(f"outlet_{i}", (-2.412, y, 1.19), (0.015, 0.09, 0.075), (0.26, 0.29, 0.29))

    # One framed board, with a tray, rather than an empty infinite horizon.
    box("board_frame", (-0.3, 2.53, 1.63), (1.30, 0.045, 0.82), (0.23, 0.28, 0.31))
    box("board", (-0.3, 2.501, 1.63), (1.25, 0.012, 0.77), (0.83, 0.84, 0.79), roughness=0.4)
    box("board_tray", (-0.3, 2.46, 1.22), (1.30, 0.10, 0.02), (0.23, 0.28, 0.31))
    return names


def add_compact_lab(scene, manifest) -> list[str]:
    """Enclosed 3.8 x 3.4 m room; cameras and lights remain inside its shell.

    The older two-wall backdrop works only from one corner. A complete shell
    prevents newly placed cameras from seeing the photographic HDRI horizon.
    Room lights are supplied by the presentation config, below the ceiling.
    """
    names = []

    def box(name, pos, size, color, roughness=.7):
        name = f"lab_{name}"
        manifest.add(name, scene.add_entity(
            gs.morphs.Box(pos=pos, size=size, fixed=True, collision=False),
            material=gs.materials.Rigid(needs_coup=False),
            surface=gs.surfaces.Plastic(color=color, roughness=roughness), name=name))
        names.append(name)

    # A solid floor above the original ground plane, with restrained tile seams.
    box("floor", (0, 0, .012), (3.9, 3.5, .02), (.32, .37, .39))
    for i in range(-3, 4):
        box(f"grout_x_{i}", (i*.5, 0, .0225), (.003, 3.4, .001), (.45,.49,.50))
        box(f"grout_y_{i}", (0, i*.5, .0225), (3.8, .003, .001), (.45,.49,.50))
    for sign in (-1, 1):
        box(f"wall_x_{sign}", (sign*1.9, 0, 1.30), (.10, 3.5, 2.60), (.73,.76,.76))
        box(f"wall_y_{sign}", (0, sign*1.7, 1.30), (3.9,.10,2.60), (.79,.78,.74))
        box(f"skirting_x_{sign}", (sign*1.842,0,.085), (.016,3.4,.13), (.31,.37,.39))
        box(f"skirting_y_{sign}", (0,sign*1.642,.085), (3.8,.016,.13), (.31,.37,.39))
    box("ceiling", (0,0,2.60), (3.9,3.5,.10), (.86,.86,.83))
    for i,x in enumerate((-.60,.60)):
        box(f"ceiling_panel_{i}", (x,0,2.535), (.50,1.30,.025), (.96,.96,.93))

    # Shallow storage occupies the rear wall without encroaching on the table.
    for i,y in enumerate((-.65,0.,.65)):
        box(f"cabinet_{i}", (-1.57,y,.46), (.50,.62,.88), (.30,.39,.42))
        box(f"door_{i}", (-1.309,y,.47), (.018,.58,.79), (.55,.61,.62))
        box(f"handle_{i}", (-1.289,y,.76), (.024,.18,.014), (.18,.21,.22), .35)
    box("counter", (-1.55,0,.925), (.56,1.96,.04), (.79,.80,.77), .45)
    box("raceway", (-1.836,0,1.17), (.025,2.10,.05), (.88,.88,.84))
    for i,y in enumerate((-.55,.25,.85)):
        box(f"outlet_{i}", (-1.816,y,1.17), (.015,.07,.07), (.36,.41,.41))
    box("board_frame", (0,1.638,1.65), (1.20,.04,.74), (.31,.37,.38))
    box("board", (0,1.613,1.65), (1.15,.012,.69), (.89,.89,.84), .5)
    box("board_tray", (0,1.57,1.27), (1.20,.09,.018), (.31,.37,.38))
    # A closed door provides scale on the other visible wall; no sky opening.
    box("door_frame", (.65,-1.638,1.10), (.87,.025,2.12), (.40,.45,.45))
    box("room_door", (.65,-1.615,1.10), (.80,.02,2.04), (.70,.73,.71))
    box("door_handle", (.95,-1.59,1.02), (.10,.04,.016), (.24,.28,.28), .35)
    return names
