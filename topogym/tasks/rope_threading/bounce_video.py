"""CPU-rendered diagnostic video of saved startup states; never a new rollout."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pair(suite):
    names = json.loads((suite/"cases.json").read_text())
    roots = [suite/names.get(name, name) for name in ("free_baseline", "free_halfdt")]
    arrays, initial = [], []
    for root in roots:
        with np.load(root/"trajectory.npz") as data:
            arrays.append((data["times"].copy(), data["centerlines"].astype(float)))
        with np.load(root/"mesh.npz") as data:
            initial.append(data["initial_nodes"][data["material_rings"]].mean(axis=1))
    clock, ia, ib = np.intersect1d(np.rint(arrays[0][0]*1e9).astype(np.int64),
        np.rint(arrays[1][0]*1e9).astype(np.int64), return_indices=True)
    selected = (clock > 0) & (clock <= 200_000_000)
    times = np.r_[0., clock[selected]*1e-9]
    a = np.concatenate((initial[0][None], arrays[0][1][ia[selected]]))
    b = np.concatenate((initial[1][None], arrays[1][1][ib[selected]]))
    if a.shape != b.shape or not np.allclose(np.diff(times), .02, atol=1e-10, rtol=0):
        raise ValueError("Expected paired 20 ms snapshots with identical material discretization")
    if len(times) != 11 or not np.allclose(initial[0], initial[1], atol=1e-9, rtol=0):
        raise ValueError("Expected matching initial states and a complete 0..0.2 s prefix")
    return roots, times, a, b


def build(suite, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    import imageio.v2 as imageio
    from PIL import Image

    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Choose a new diagnostic output directory")
    output.mkdir(parents=True, exist_ok=True)
    font = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({"font.family": font_manager.FontProperties(fname=font).get_name(),
        "font.size": 12, "axes.unicode_minus": False})
    roots, times, a, b = load_pair(suite)
    cfg = OmegaConf.load(roots[0]/"config.yaml")
    floor = float(cfg.env.world.table.pos[2]+cfg.env.world.table.size[2]/2)
    steps = [float(OmegaConf.load(root/"config.yaml").env.sim.dt)/int(
        OmegaConf.load(root/"config.yaml").env.sim.substeps) for root in roots]
    points = np.rint(np.linspace(0, a.shape[1]-1, 81)).astype(int)
    distance = np.linalg.norm(a[:, points]-b[:, points], axis=2)*1000
    rms = np.sqrt(np.mean(distance**2, axis=1))
    maximum = distance.max(axis=1)
    height = [(c[:, :, 2].mean(axis=1)-c[0, :, 2].mean())*1000 for c in (a, b)]
    colors = ("#1975c2", "#df721f")
    labels = ("子步 1.25 ms", "子步 0.625 ms")
    fps, slow, z_scale = 25, 50, 10
    fig = plt.figure(figsize=(16, 10), dpi=100, facecolor="#f3f6fa")
    fig.text(.045, .954, "绳子启动弹起 · 慢放对照", fontsize=26, weight="bold", color="#173044")
    fig.text(.045, .915, "启动时的自由静置 · 没有执行 IK 动作 · 两次已保存物理状态的同步对照", color="#526578", fontsize=14)
    clock_text = fig.text(.955, .953, "", ha="right", fontsize=24, weight="bold", color="#173044")
    fig.text(.955, .915, "50 倍慢放  /  每个实存状态保留 1 秒", ha="right", fontsize=13, color="#526578")
    limits = np.stack((a[0, :, :2].min(axis=0)-.045, a[0, :, :2].max(axis=0)+.045))*1000
    width, depth = limits[1]-limits[0]
    artists, counters = [], []
    display = []
    for j, c in enumerate((a, b)):
        relative = c.copy()*1000
        relative[:, :, 2] -= floor*1000
        display.append(relative)
        axis = fig.add_axes([.015+.5*j, .405, .47, .46], projection="3d", facecolor="#f3f6fa", computed_zorder=False)
        plane = [[limits[0, 0], limits[0, 1], 0], [limits[1, 0], limits[0, 1], 0],
                 [limits[1, 0], limits[1, 1], 0], [limits[0, 0], limits[1, 1], 0]]
        axis.add_collection3d(Poly3DCollection([plane], facecolors="#dce5eb", edgecolors="#becdd7", alpha=.55, zorder=1))
        axis.plot(*relative[0].T, color="#9aa8b3", ls="--", lw=1.5, alpha=.8, zorder=3)
        line, = axis.plot(*relative[0].T, color=colors[j], lw=4.5, solid_capstyle="round", zorder=4)
        artists.append(line)
        axis.set(xlim=limits[:, 0], ylim=limits[:, 1], zlim=(0, 22), xlabel="X / mm", ylabel="Y / mm",
                 zlabel="离桌面高度 / mm", zticks=[0, 5, 10, 15, 20])
        axis.set_box_aspect((width, depth, 22*z_scale))
        axis.view_init(elev=23, azim=-65)
        axis.tick_params(labelsize=9, pad=0)
        axis.xaxis.labelpad = axis.yaxis.labelpad = 1
        axis.zaxis.labelpad = 4
        fig.text(.265+.5*j, .873, labels[j], ha="center", fontsize=19, color=colors[j], weight="bold")
        counters.append(fig.text(.265+.5*j, .839, "", ha="center", fontsize=14, color=colors[j]))
    fig.text(.5, .424, "上图显示绳中心线；灰色虚线为初态。为看清毫米级运动，Z 方向放大 10 倍，刻度仍为真实毫米。",
             ha="center", fontsize=12, color="#526578")
    ax_height = fig.add_axes([.065, .15, .405, .245], facecolor="white")
    for j in range(2):
        ax_height.plot(times*1000, height[j], color=colors[j], lw=2, marker="o", ms=4, label=labels[j])
    ax_height.set(xlim=(0, 200), ylim=(-.5, 12), xlabel="实际物理时间 / ms", ylabel="相对初态的平均抬升 / mm")
    ax_height.grid(alpha=.18)
    ax_height.legend(loc="upper right", fontsize=10)
    height_cursor = ax_height.axvline(0, color="#385166", ls="--", lw=1.5)
    dots = [ax_height.plot([0], [0], "o", color=color, ms=9)[0] for color in colors]
    ax_error = fig.add_axes([.565, .15, .405, .245], facecolor="white")
    ax_error.plot(times*1000, rms, color="#804ba8", lw=2.5, marker="o", ms=4, label="81 个对应点的 RMS")
    ax_error.axhline(2, color="#c44e52", ls="--", label="验收门槛：2 mm")
    ax_error.set(xlim=(0, 200), ylim=(-.5, 9.5), xlabel="实际物理时间 / ms", ylabel="两次仿真的 RMS 差异 / mm")
    ax_error.grid(alpha=.18)
    ax_error.legend(loc="upper right", fontsize=10)
    error_cursor = ax_error.axvline(0, color="#385166", ls="--", lw=1.5)
    error_dot, = ax_error.plot([0], [0], "o", color="#804ba8", ms=9)
    stats = fig.text(.5, .067, "", ha="center", fontsize=16, weight="bold", color="#173044")
    fig.text(.5, .026, "诊断状态可视化 · 非仿真相机录屏 · 只播放已保存的 20 ms 采样，帧间没有补算或插值 · 末帧停留 2 秒",
             ha="center", fontsize=11, color="#657786")
    frames, samples = [], []
    peak = int(np.argmax(rms))
    path = output/"startup_bounce_comparison.mp4"
    with imageio.get_writer(path, fps=fps, codec="libx264", quality=8, macro_block_size=1,
            ffmpeg_params=["-threads", "2"], ffmpeg_log_level="error") as writer:
        for i, t in enumerate(times):
            clock_text.set_text(f"物理时间  {t*1000:03.0f} ms")
            for j in range(2):
                artists[j].set_data_3d(*display[j][i].T)
                counters[j].set_text(f"中心线平均抬升：{height[j][i]:.2f} mm")
                dots[j].set_data([t*1000], [height[j][i]])
            height_cursor.set_xdata([t*1000]*2)
            error_cursor.set_xdata([t*1000]*2)
            error_dot.set_data([t*1000], [rms[i]])
            stats.set_text(f"当前 RMS：{rms[i]:.2f} mm    ·    最大单点差异：{maximum[i]:.2f} mm"
                           + ("    ·    超过验收门槛" if rms[i] > 2 else ""))
            stats.set_color("#b34343" if rms[i] > 2 else "#173044")
            fig.canvas.draw()
            rgb = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy()
            if i == peak:
                Image.fromarray(rgb).save(output/"peak_60ms.png")
            if i == 0:
                Image.fromarray(rgb).save(output/"initial.png")
            copies = round((times[i+1]-t)*slow*fps) if i+1 < len(times) else 2*fps
            samples.append(dict(physical_time_s=float(t), video_time_s=len(frames)/fps,
                frame_count=copies, rms_mm=float(rms[i]), maximum_point_mm=float(maximum[i]),
                mean_lift_mm=[float(h[i]) for h in height]))
            for _ in range(copies):
                writer.append_data(rgb)
                frames.append(dict(frame=len(frames), physical_time_s=float(t)))
    plt.close(fig)
    with imageio.get_reader(path) as reader:
        properties = reader.get_meta_data()
        decoded_frames = sum(1 for _ in reader)
    if decoded_frames != len(frames) or properties["fps"] != fps:
        raise RuntimeError("Video decode or frame-rate check failed")
    manifest = dict(scope="diagnostic visualization of saved physical states; not original camera footage or a new rollout",
        same_physical_times=True, independent_runs=True, runtime_physics_steps=0, full_demo=False,
        native_time_steps_s=steps, physical_interval_s=[0., .2], saved_interval_s=.02,
        state_interpolation=False, initial_state_source="native mesh vertices at build time, averaged over material rings",
        displayed_material_points=int(a.shape[1]), rms_material_points=81,
        vertical_display_exaggeration=z_scale, slowdown=slow, final_hold_s=2,
        fps=fps, decoded_frames=decoded_frames, duration_s=decoded_frames/fps,
        samples=samples, source_sha256={str(p.relative_to(suite)): digest(p)
            for root in roots for p in (root/"trajectory.npz", root/"mesh.npz", root/"config.yaml")},
        video_sha256=digest(path), implementation_sha256=digest(Path(__file__)))
    (output/"manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
    (output/"frames.json").write_text(json.dumps(frames)+"\n")
    np.savez_compressed(output/"displayed_states.npz", times=times, baseline=a, half_step=b,
                        rms_mm=rms, maximum_point_mm=maximum, table_height_m=floor)
    (output/"index.html").write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>绳子启动弹起 · 慢放对照</title>
<style>body{font:16px/1.75 system-ui;max-width:1440px;margin:24px auto;padding:20px;background:#f3f6fa;color:#173044}
video,img{width:100%;border-radius:10px}button{font:inherit;padding:8px 16px;margin:4px;border:1px solid #bdcdd8;border-radius:7px;background:white;cursor:pointer}
a{color:#176aa6}.note{background:white;padding:14px 20px;border-radius:10px}</style>
<h1>仿真启动时的竖直弹起</h1><p>左：1.25 ms 子步；右：0.625 ms 子步。播放实际启动后的 0–0.2 s，50 倍慢放。
0.04 s 附近弹起较高，0.06 s 时两次绳形差异最大；机械臂没有执行 IK 动作。</p>
<video id="video" controls playsinline preload="metadata" poster="peak_60ms.png" src="startup_bounce_comparison.mp4"></video>
<p><button onclick="v.currentTime=0;v.play()">从头播放</button><button onclick="v.pause();v.currentTime=2">查看 40 ms 弹起</button>
<button onclick="v.pause();v.currentTime=3">查看 60 ms 最大差异</button></p>
<div class="note"><strong>这是已保存物理状态的可视化，不是当时的相机录屏。</strong>
只使用两次运行保存的真实中心线和初始网格，匹配相同物理时刻；每个 20 ms 状态保持 1 s，不插值、不重跑物理。
上方空间图将 Z 方向放大 10 倍以展示毫米级运动，坐标刻度及数值仍是真实毫米。末帧保持 2 s。
RMS 使用 81 个原始材料点计算，峰值约 7.76 mm，门槛为 2 mm。</div>
<p><a href="startup_bounce_comparison.mp4">直接打开 MP4</a> · <a href="peak_60ms.png">60 ms 对照截图</a> ·
<a href="manifest.json">来源、时间映射与文件校验</a> · <a href="../index.html">完整物理验收报告</a></p>
<script>const v=document.getElementById('video');</script></html>''')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=Path("runs/environment-solvability/rope_threading/physics_v5"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.suite.resolve(), args.output.resolve())
    print(json.dumps({key: result[key] for key in ("decoded_frames", "duration_s", "video_sha256")}, indent=2))


if __name__ == "__main__":
    main()
