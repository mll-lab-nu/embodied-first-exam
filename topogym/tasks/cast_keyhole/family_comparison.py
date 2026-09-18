"""Same-scale gray solid comparison and nine synchronized physical episodes."""
from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import subprocess

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial.transform import Rotation
from shapely.geometry import MultiPoint
from shapely.ops import unary_union

from .family_variants import OUTPUT, TITLES
from .inverse_variants import geometry_from_record, save, sha
from .long_stroke_archive import update_text
from .robot_motion import ROOT

PREFIX = "2026-09-17_families_v1"


def inspect_video(path):
    data = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=nb_read_frames,avg_frame_rate,duration,width,height", "-of", "json", str(path)]))["streams"][0]
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], check=True, capture_output=True)
    return dict(data, sha256=sha(path), decoded=True)


def main():
    metadata_root = ROOT / "runs/demo_metadata"
    meta = metadata_root / "cast_keyhole" / (PREFIX + "_comparison")
    video_root = ROOT / "runs/demos/cast_keyhole"
    if meta.exists():
        raise ValueError("Comparison archive already exists")
    working = OUTPUT / "comparison"; working.mkdir(exist_ok=True)
    sources = {}
    for style in TITLES:
        source = metadata_root / "cast_keyhole" / (PREFIX + "_" + style)
        manifest = json.loads((source / "archive_manifest.json").read_text())
        validation = json.loads((source / "archive_validation.json").read_text())
        if not validation["passed"]:
            raise ValueError("An individual physical archive is missing")
        path = (source / manifest["videos"]["detail"]["path"]).resolve()
        if sha(path) != manifest["videos"]["detail"]["sha256"]:
            raise ValueError("Source video changed")
        sources[style] = dict(video=str(path), video_sha256=sha(path), frames=validation["frames"],
                              geometry=str(source / "evidence/geometry.json"),
                              geometry_sha256=sha(source / "evidence/geometry.json"),
                              fps=validation["fps"], archive_manifest=str(source / "archive_manifest.json"))
    fps = 12; tile_w, tile_h = 640, 360; total = max(s["frames"] for s in sources.values())
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    with ExitStack() as stack:
        readers = {k: stack.enter_context(imageio.get_reader(v["video"], input_params=["-threads", "1"])) for k, v in sources.items()}
        writer = stack.enter_context(imageio.get_writer(working / "process_grid.mp4", fps=fps, codec="libx264", quality=8,
            macro_block_size=1, ffmpeg_params=["-threads", "2"], ffmpeg_log_level="error"))
        last = {}
        for i in range(total):
            canvas = Image.new("RGB", (1920, 1080))
            for j, (style, source) in enumerate(sources.items()):
                frame = min(i, source["frames"] - 1)
                if style not in last or last[style][0] != frame:
                    last[style] = (frame, readers[style].get_data(frame))
                tile = Image.fromarray(last[style][1]).resize((tile_w, tile_h))
                draw = ImageDraw.Draw(tile); draw.rectangle((0, 0, tile_w, 29), fill="#17212a")
                label = style + ("  final hold" if i >= source["frames"] else "  physical execution")
                draw.text((12, 2), label, font=font, fill="white")
                canvas.paste(tile, ((j % 3) * tile_w, (j // 3) * tile_h))
            writer.append_data(np.asarray(canvas))
    print("Nine physical episodes combined", flush=True)
    parts = {}
    for style, source in sources.items():
        _, cells = geometry_from_record(json.loads(Path(source["geometry"]).read_text()))
        parts[style] = [p.vertices * 1000 for p in cells[0]]
    views = [(0., 0.), (25., 35.), (25., -35.)]
    with imageio.get_writer(working / "shape_grid.mp4", fps=fps, codec="libx264", quality=8, macro_block_size=1,
                           ffmpeg_params=["-threads", "2"], ffmpeg_log_level="error") as writer:
        for index, (pitch, yaw) in enumerate(views):
            canvas = Image.new("RGB", (1920, 1440), "#f7f8fa")
            r = Rotation.from_euler("xy", [pitch, yaw], degrees=True).as_matrix()
            for j, (style, prisms) in enumerate(parts.items()):
                tile = Image.new("RGB", (640, 480), "#f7f8fa"); draw = ImageDraw.Draw(tile)
                silhouette = unary_union([MultiPoint((v @ r.T)[:, :2]).convex_hull for v in prisms])
                # All pieces use one metric scale and one camera, with no fitting per item.
                def points(ring):
                    return [(320 + float(x) * 1.45, 260 - (float(y) - 18) * 1.45) for x, y in ring.coords]
                for poly in getattr(silhouette, "geoms", [silhouette]):
                    draw.polygon(points(poly.exterior), fill="#72777d")
                    for hole in poly.interiors:
                        draw.polygon(points(hole), fill="#f7f8fa")
                draw.text((20, 10), f"{style}    view {index + 1}/3", font=font, fill="#1b2731")
                draw.text((20, 447), "same scale / same gray / actual solid", font=font, fill="#43515d")
                canvas.paste(tile, ((j % 3) * 640, (j // 3) * 480))
            canvas.save(working / f"gray_view_{index + 1}.png")
            for _ in range(fps * 4):
                writer.append_data(np.asarray(canvas))
    outputs = {name: inspect_video(working / (name + ".mp4")) for name in ("process_grid", "shape_grid")}
    if int(outputs["process_grid"]["nb_read_frames"]) != total or int(outputs["shape_grid"]["nb_read_frames"]) != 144:
        raise ValueError("Comparison frame count mismatch")
    meta.mkdir(parents=True)
    for path in working.glob("*.png"):
        shutil.copy2(path, meta / path.name)
    shutil.copy2(OUTPUT / "nine_silhouettes.png", meta / "nine_silhouettes.png")
    shutil.copy2(OUTPUT / "silhouette_distances.json", meta / "silhouette_distances.json")
    shutil.copy2(Path(__file__), meta / "family_comparison.py")
    for name, result in outputs.items():
        target = video_root / (PREFIX + "_" + name + ".mp4")
        if target.exists():
            raise ValueError("Refusing to overwrite a preserved comparison")
        shutil.copy2(working / (name + ".mp4"), target)
        if sha(target) != result["sha256"] or target.is_symlink():
            raise ValueError("Comparison copy failed")
        result["path"] = os.path.relpath(target, meta)
    for source in sources.values():
        for k in ("video", "geometry", "archive_manifest"):
            source[k] = os.path.relpath(source[k], meta)
    save(meta / "archive_manifest.json", dict(passed=True, classification="comparison_of_nine_verified_physical_episodes",
         counts_as_complete_robotics_demo=False, videos=outputs, sources=sources,
         process_alignment="common physical start; shorter episodes repeat their final actual frame",
         shape_views=dict(type="orthographic projections of actual convex collision solids", gray=True, scale_px_per_mm=1.45,
                          rotations_xy_deg=views, silver_geometry_shared=True),
         metadata_sha256={p.name: sha(p) for p in meta.iterdir() if p.is_file()}))
    relative = str(meta.relative_to(metadata_root))
    card = f'<section><h2>Cast Keyhole · 三个 family / 九款代表</h2><p><a href="../demos/cast_keyhole/{PREFIX}_shape_grid.mp4">九款灰色实体三视图</a> · <a href="../demos/cast_keyhole/{PREFIX}_process_grid.mp4">九款全过程对照</a> · <a href="{relative}/archive_manifest.json">来源与检查</a></p></section>'
    update_text(metadata_root / "index.html", lambda text: text.replace("<section><h2>本次暂未收录", card + "<section><h2>本次暂未收录"))
    row = f'| Cast Keyhole · 九款对照 | [外形](../demos/cast_keyhole/{PREFIX}_shape_grid.mp4) · [全过程](../demos/cast_keyhole/{PREFIX}_process_grid.mp4) | 2 | 三个 family；同尺度灰色三视图与九次已验证物理执行。 |\n'
    update_text(metadata_root / "README.md", lambda text: text.replace("\n\n保留全部既有 MP4", "\n" + row + "\n保留全部既有 MP4"))
    def catalog(text):
        data = json.loads(text)
        data.setdefault("comparisons", []).append(dict(task_id="cast_keyhole", directory=relative,
             manifest=relative + "/archive_manifest.json", counts_as_complete_robotics_demo=False))
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    update_text(metadata_root / "catalog.json", catalog)
    print(json.dumps(dict(passed=True, metadata=str(meta), videos=outputs), indent=2), flush=True)


if __name__ == "__main__":
    main()
