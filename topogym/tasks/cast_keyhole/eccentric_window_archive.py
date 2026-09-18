"""Archive the complete physical eccentric-window episode and its evidence."""
import json
from pathlib import Path

from .eccentric_window import OUTPUT
from .inverse_variants import sha
from .long_stroke_archive import archive


if __name__ == "__main__":
    proposal = json.loads((OUTPUT / "proposal.json").read_text())
    design = json.loads((OUTPUT / "design_result.json").read_text())
    if (not design["passed"] or design["variant"] != "eccentric_window"
            or design["generator_sha256"] != sha(Path(__file__).with_name("eccentric_window.py"))
            or design["certificate_sha256"] != sha(OUTPUT / "certificate.json")
            or not all(c["collision_found"] for c in design["negative_controls"].values())):
        raise ValueError("Missing or changed eccentric-window design evidence")
    x, y, _ = proposal["maximum_excursion_scene_mm"]
    archive(
        variant=OUTPUT,
        run_id="2026-09-17_eccentric_window_v1",
        generator="eccentric_window",
        scope=f"偏心转向窗型：顶部绕行最大右偏{x:g} mm、上移{y:g} mm（场景尺寸），由新IK扫掠体反推窗口及内侧挡肩；原IK与直拉对照发生碰撞。预抓取起点，双指接触后辅助抓持，完整分离后双臂保持。七路视频来自同一次物理执行；1 ms与0.5 ms时间步均通过独立检查。",
    )
