"""Preserve independent full physical videos for all nine family representatives."""
from pathlib import Path
import shutil

from .family_pipeline import qualify_physics
from .long_stroke_archive import archive


def archive_one(folder):
    folder = Path(folder)
    q = qualify_physics(folder)
    for name in ("family_pipeline.py", "turnback_archive.py", "turnback.py"):
        shutil.copy2(Path(__file__).with_name(name), folder / ("snapshot_" + name))
    archive(variant=folder, run_id="2026-09-17_families_v1_" + folder.name,
            generator="family_variants",
            scope=f"{q['style']} 外形代表款；保留 {q['family']} 解锁机制，外形与碰撞网格一致。完整几何解法、关键动作对照和1 ms/0.5 ms物理执行通过。视频来自同一次实际物理轨迹；预抓取、接触后辅助抓持，分离后双臂保持。")
