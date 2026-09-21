"""Reproducible geometry inspection and optional Genesis scene loading."""

import json
from pathlib import Path

import hydra
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation
import trimesh

from .geometry import BuzzWireLayout, capsule_mesh, generate_assets, transported_frames
from .verification import verify_route


def tube_mesh(points, radius, closed=False, sides=12):
    points = np.asarray(points)
    tangent = (
        np.roll(points, -1, axis=0) - np.roll(points, 1, axis=0)
        if closed
        else np.gradient(points, axis=0)
    )
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    frame = transported_frames(tangent)
    u, v = frame.apply([1, 0, 0]), frame.apply([0, 1, 0])
    theta = np.arange(sides) * 2 * np.pi / sides
    vertices = (
        points[:, None, :]
        + radius
        * (
            u[:, None, :] * np.cos(theta)[None, :, None]
            + v[:, None, :] * np.sin(theta)[None, :, None]
        )
    ).reshape(-1, 3)
    faces = []
    for i in range(len(points) if closed else len(points) - 1):
        j = (i + 1) % len(points)
        for a in range(sides):
            b = (a + 1) % sides
            faces.extend(
                [
                    [i * sides + a, j * sides + a, j * sides + b],
                    [i * sides + a, j * sides + b, i * sides + b],
                ]
            )
    return trimesh.Trimesh(
        vertices=vertices, faces=np.asarray(faces)[:, ::-1], process=False
    )


def meshes(wire):
    layout = wire.layout
    base = trimesh.creation.box(extents=layout.base_size_m)
    base.apply_translation([0, 0, layout.base_size_m[2] / 2])
    # Small coplanar faces prevent the static plot's painter ordering from
    # hiding endpoint mounts behind a single large base-top triangle.
    vertices, faces = trimesh.remesh.subdivide_to_size(
        base.vertices, base.faces, max_edge=0.09
    )
    base = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    rail = tube_mesh(wire.rail, layout.wire_radius_m)
    stops = [
        capsule_mesh(p, p, layout.end_stop_radius_m)
        for p in (wire.rail[0], wire.rail[-1])
    ]
    segments = layout.tool_capsules()
    loop = tube_mesh(
        np.array([s[0] for s in segments[:-2]]), layout.loop_tube_radius_m, True, 8
    )
    metal = trimesh.util.concatenate([loop, capsule_mesh(*segments[-2][:3])])
    grip = capsule_mesh(*segments[-1][:3])
    return [
        (base, "#b38045"),
        (rail, "#b8642e"),
        (stops[0], "#26977a"),
        (stops[1], "#dd6c36"),
    ], [(metal, "#c99235"), (grip, "#246592")]


def write_inspection(output, wire, proof):
    """Offline rotatable 3D view plus an exportable image of the actual dimensions."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    import plotly.graph_objects as go

    fixed, moving = meshes(wire)
    p, q = wire.pose(0.0)
    rot = Rotation.from_quat(q[[1, 2, 3, 0]])
    initial = fixed + [
        (
            trimesh.Trimesh(
                vertices=rot.apply(m.vertices) + p, faces=m.faces, process=False
            ),
            c,
        )
        for m, c in moving
    ]
    scene = trimesh.Scene()
    for i, (mesh, color) in enumerate(initial):
        mesh.visual.vertex_colors = trimesh.visual.color.hex_to_rgba(color)
        scene.add_geometry(mesh, node_name=f"part_{i}")
    scene.export(output / "scene.glb")
    half_x = wire.layout.base_size_m[0] / 2 + 0.04
    half_y = wire.layout.base_size_m[1] / 2 + 0.05
    top = float(wire.rail[:, 2].max()) + 0.15

    def draw_view(ax, title, elev, azim):
        el, az = np.deg2rad([elev, azim])
        eye = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
        triangles, colors = [], []
        for mesh, color in initial:
            faces = mesh.faces[mesh.face_normals @ eye > 1e-8]
            triangles.extend(mesh.vertices[faces])
            colors.extend([color] * len(faces))
        ax.add_collection3d(
            Poly3DCollection(
                triangles,
                facecolors=colors,
                linewidths=0,
                antialiased=False,
                shade=True,
                lightsource=matplotlib.colors.LightSource(azdeg=230, altdeg=55),
            )
        )
        ax.set(
            xlim=(-half_x, half_x), ylim=(-half_y, half_y), zlim=(0, top), title=title
        )
        ax.set_box_aspect((2 * half_x, 2 * half_y, top))
        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off()

    fig = plt.figure(figsize=(18, 6), layout="constrained", facecolor="#f4f6f7")
    for i, (title, elev, azim) in enumerate(
        [
            ("Horizontal folds / vertical folds / spiral", 26, -66),
            ("Front: vertical switchbacks", 0, -90),
            ("Top: horizontal switchbacks and spiral", 90, -90),
        ]
    ):
        draw_view(
            fig.add_subplot(1, 3, i + 1, projection="3d", proj_type="ortho"),
            title,
            elev,
            azim,
        )
    fig.savefig(output / "scene_views.png", dpi=180)
    plt.close(fig)
    fig = plt.figure(figsize=(11, 8), layout="constrained", facecolor="#f4f6f7")
    draw_view(
        fig.add_subplot(projection="3d", proj_type="ortho"), "3D Buzz Wire", 28, -66
    )
    fig.savefig(output / "scene_overview.png", dpi=160)
    plt.close(fig)

    def trace(mesh, color, vertices=None):
        xyz = mesh.vertices if vertices is None else vertices
        return go.Mesh3d(
            x=xyz[:, 0],
            y=xyz[:, 1],
            z=xyz[:, 2],
            i=mesh.faces[:, 0],
            j=mesh.faces[:, 1],
            k=mesh.faces[:, 2],
            color=color,
            flatshading=False,
            hoverinfo="skip",
            lighting=dict(ambient=0.65, diffuse=0.8, specular=0.3, roughness=0.5),
        )

    data = [trace(m, c) for m, c in initial]
    frames = []
    for i, u in enumerate(np.linspace(0, 1, 241)):
        p, q = wire.pose(float(u))
        r = Rotation.from_quat(q[[1, 2, 3, 0]])
        frames.append(
            go.Frame(
                name=str(i),
                data=[trace(m, c, r.apply(m.vertices) + p) for m, c in moving],
                traces=[4, 5],
            )
        )
    fig = go.Figure(data=data, frames=frames)
    fig.update_layout(
        height=650,
        margin=dict(l=0, r=0, b=0, t=20),
        paper_bgcolor="#f4f6f7",
        scene=dict(
            aspectmode="data",
            xaxis=dict(range=[-half_x, half_x], visible=False),
            yaxis=dict(range=[-half_y, half_y], visible=False),
            zaxis=dict(range=[0, top], visible=False),
            camera=dict(eye=dict(x=1.1, y=-1.6, z=0.95)),
            dragmode="orbit",
        ),
        updatemenus=[
            dict(
                type="buttons",
                direction="left",
                x=0.0,
                y=0.0,
                buttons=[
                    dict(
                        label="播放完整路径",
                        method="animate",
                        args=[
                            None,
                            dict(
                                frame=dict(duration=100, redraw=True),
                                transition=dict(duration=0),
                                fromcurrent=True,
                            ),
                        ],
                    ),
                    dict(
                        label="暂停",
                        method="animate",
                        args=[
                            [None],
                            dict(
                                mode="immediate",
                                frame=dict(duration=0, redraw=False),
                                transition=dict(duration=0),
                            ),
                        ],
                    ),
                ],
            )
        ],
        sliders=[
            dict(
                x=0.30,
                len=0.68,
                y=0.0,
                currentvalue=dict(prefix="路径帧 "),
                steps=[
                    dict(
                        label=str(i),
                        method="animate",
                        args=[
                            [str(i)],
                            dict(
                                mode="immediate",
                                frame=dict(duration=0, redraw=True),
                                transition=dict(duration=0),
                            ),
                        ],
                    )
                    for i in range(241)
                ],
            )
        ],
    )
    plot = fig.to_html(
        full_html=False,
        include_plotlyjs=True,
        auto_play=False,
        config={"displaylogo": False, "responsive": True},
    )
    clearance = proof["minimum_continuous_clearance_lower_bound_m"] * 1000
    description = (
        "参照用户提供的实物布局：左侧横向长回折 → 中部上下回折 → 右侧向内盘旋 → 下行终点。"
        if wire.layout.template_id == "spatial_maze_v2"
        else "第一版空间起伏路线。"
    )
    source_note = (
        "布局来源为本轮用户提供的照片；尺寸为自行设计，未模拟照片中的电子元件。盘旋末端会逐渐转动手柄，避开邻近导线。"
        if wire.layout.template_id == "spatial_maze_v2"
        else "保留的 spatial_slalom_v1 几何布局；尺寸为自行设计。"
    )
    html = (
        """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>3D Buzz Wire · 空间电流棒</title><style>body{max-width:1400px;margin:30px auto;padding:0 20px;background:#f4f6f7;color:#243443;font:16px/1.7 system-ui}img{width:100%}a{color:#17648b}</style>
<h1>3D Buzz Wire · 空间电流棒</h1>
"""
        + f"<p>{description}从绿色起点沿铜色导线前进，到达橙色终点。拖动画面可旋转查看，播放按钮展示环与手柄的完整参考路径。</p>"
        + f"<p>长方体底座 {wire.layout.base_size_m[0] * 100:.0f} × {wire.layout.base_size_m[1] * 100:.0f} cm。</p>"
        + f"<p>导线总长 {wire.length:.2f} m，可玩段 {wire.length - 2 * wire.layout.end_reserve_m:.2f} m；全程连续几何净空下界 {clearance:.1f} mm。</p>"
        + plot
        + """
<p>这是几何通行预演，环已预先穿在线上；尚未验证机器人抓取、物理跟踪或触线蜂鸣计分。闭环与手柄均纳入净空检查，两端防脱球大于环的内孔；支撑不占据中间路线。</p>
<p><a href="report.json">检查报告</a> · <a href="config.yaml">完整配置</a> · <a href="assets/reference_path.npz">参考位姿</a> · <a href="scene.glb">场景模型 GLB</a></p>
<img src="scene_views.png" alt="斜视、正视与俯视场景图">
"""
        + f"<p>{source_note}</p></html>"
    )
    (output / "index.html").write_text(html, encoding="utf-8")


@hydra.main(
    version_base="1.3",
    config_path=str(Path(__file__).resolve().parents[3] / "configs"),
    config_name="buzz_wire_3d_preview",
)
def main(cfg):
    if cfg.run.render and not cfg.run.build_scene:
        raise ValueError("Rendering requires run.build_scene=true")
    if cfg.run.build_scene and int(cfg.run.smoke_steps) < 1:
        raise ValueError("Scene loading check requires at least one physics step")
    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    layout = BuzzWireLayout(**OmegaConf.to_container(cfg.task.geometry, resolve=True))
    wire, geometry = generate_assets(output / "assets", layout)
    proof = verify_route(wire)
    report = dict(
        task_id="buzz_wire_3d",
        scope="spatial_scene_and_geometric_traversal",
        passed=proof["passed"],
        geometry=geometry,
        clearance=proof,
        genesis_scene_loaded=False,
        full_robot_task_verified=False,
        physical_traversal_verified=False,
        asset_sha256=json.loads((output / "assets" / "sha256.json").read_text()),
    )
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if not proof["passed"]:
        raise ValueError(f"Reference route rejected: {proof}")
    write_inspection(output, wire, proof)
    print(f"Geometry passed: {output / 'index.html'}", flush=True)
    if cfg.run.build_scene:
        import genesis as gs
        from .scene import BuzzWireSceneBuilder

        gs.init(
            backend=getattr(gs, str(cfg.env.genesis.backend)),
            logging_level="warning",
            seed=0,
        )
        cfg.env.cameras = OmegaConf.create(
            {
                name: OmegaConf.to_container(cfg.env.cameras[name], resolve=True)
                for name in ("overview", "front_oblique", "topdown")
            }
            if cfg.run.render
            else {}
        )
        task = BuzzWireSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
            asset_dir=output / "assets",
            show_viewer=bool(cfg.run.viewer),
            include_robot=bool(cfg.run.include_robot),
        )
        expected_p, expected_q = task.reference_pose(0.0)
        initial_p = task.wand.get_pos().detach().cpu().numpy().reshape(3)
        initial_q = task.wand.get_quat().detach().cpu().numpy().reshape(4)
        position_error = float(np.linalg.norm(initial_p - expected_p))
        orientation_error = float(
            (
                Rotation.from_quat(initial_q[[1, 2, 3, 0]]).inv()
                * Rotation.from_quat(expected_q[[1, 2, 3, 0]])
            ).magnitude()
        )
        if cfg.run.include_robot:
            from topogym.utils.franka import initialize_franka_controller

            initialize_franka_controller(
                scene=task.scene,
                manifest=task.tabletop.manifest,
                robot_cfg=cfg.robot_control,
                settle_steps=0,
            )
        render_error, rendered_cameras = None, []
        if cfg.run.render:
            from PIL import Image

            try:
                for name, camera in task.tabletop.cameras.items():
                    Image.fromarray(camera.render()[0]).save(
                        output / f"genesis_{name}.png"
                    )
                    rendered_cameras.append(name)
            except Exception as exc:
                render_error = f"{type(exc).__name__}: {exc}"
        # This intentionally does not hold the wand in the air with pose writes.
        # A free, prethreaded wand can fall onto the wire; this is only a load smoke check.
        for _ in range(int(cfg.run.smoke_steps)):
            task.scene.step()
        position = task.wand.get_pos().detach().cpu().numpy()
        finite = bool(np.isfinite(position).all())
        loaded_shapes = dict(wire=task.wire.n_geoms, wand=task.wand.n_geoms)
        expected_shapes = dict(
            wire=3 * (len(wire.rail) - 1) + 2, wand=3 * len(layout.tool_capsules())
        )
        shapes_match = loaded_shapes == expected_shapes
        report.update(
            genesis_scene_loaded=True,
            backend=str(cfg.env.genesis.backend),
            dynamic_wand_dofs=task.wand.n_dofs,
            smoke_steps=int(cfg.run.smoke_steps),
            finite_state=finite,
            loaded_collision_shapes=loaded_shapes,
            expected_collision_shapes=expected_shapes,
            collision_shapes_match=shapes_match,
            robot_present=bool(cfg.run.include_robot),
            position_writes_after_build=0,
            initial_position_error_m=position_error,
            initial_orientation_error_rad=orientation_error,
            rendered_cameras=rendered_cameras,
            rendering_error=render_error,
            passed=report["passed"]
            and finite
            and task.wand.n_dofs == 6
            and shapes_match
            and position_error < 1e-5
            and orientation_error < 1e-5
            and render_error is None,
        )
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)
        if not report["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
