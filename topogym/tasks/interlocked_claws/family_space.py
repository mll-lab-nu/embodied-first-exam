"""Audit and display the family design plan; no model synthesis or qualification."""
import argparse
import hashlib
from html import escape
import json
import math
import os
from pathlib import Path
import re

from .reference import ROOT

PLAN_PATH = ROOT / "assets/tasks/interlocked_claws/family_space_v1/plan.json"
DEFAULT_OUTPUT = ROOT / "runs/environment-solvability/interlocked_claws/family_space_plan_v1"


def audit(plan):
    if (plan["generator_implemented"] or plan["random_generation_enabled"]
            or plan["qualified_instance_ids"]):
        raise ValueError("This exporter only handles the unreleased design specification")
    families = plan["families"]
    if [f["id"] for f in families] != ["A", "B", "C"]:
        raise ValueError("Expected the three agreed categorical families")
    anchors = [r for f in families for r in f["representatives"]]
    if len(anchors) != 9 or len({r["id"] for r in anchors}) != 9:
        raise ValueError("Expected nine distinct representative targets")
    for family in families:
        if len(family["representatives"]) != 3:
            raise ValueError("Each family needs a base and two appearance representatives")
        for axis in family["appearance_axes"].values():
            lo, hi = axis["candidate_bounds"]
            if not (math.isfinite(lo) and math.isfinite(hi) and 0 < lo <= hi):
                raise ValueError("Invalid candidate bounds")
            if axis["validated_bounds"] is not None:
                raise ValueError("The current plan has no certified continuous parameter domains")
        for rep in family["representatives"]:
            if set(rep["parameters"]) != set(family["appearance_axes"]):
                raise ValueError(f"Missing or extra parameters: {rep['id']}")
            for name, value in rep["parameters"].items():
                lo, hi = family["appearance_axes"][name]["candidate_bounds"]
                if not lo <= value <= hi:
                    raise ValueError(f"Representative outside proposal bounds: {rep['id']} / {name}")
            if rep["release_eligible"]:
                raise ValueError("No representative has passed the complete release protocol")
            if rep["id"] != "A0" and any(v is not None for v in rep["checks"].values()):
                raise ValueError("An unbuilt representative cannot acquire test results")
            if family["id"] == "B":
                m = rep["target_motion"]
                if not math.isclose(m["advance_mm"], 40*rep["parameters"]["axial_ratio"]):
                    raise ValueError("Screw advance must follow axial size")
                if not math.isclose(m["equivalent_full_turn_lead_mm"], 360*m["advance_mm"]/m["turn_deg"]):
                    raise ValueError("Partial-turn advance is not full-turn lead")
            if family["id"] == "C":
                for motion, shape, base in (("push_mm", "cavity_depth_ratio", 30),
                                           ("transfer_mm", "window_offset_ratio", 40),
                                           ("rise_mm", "step_height_ratio", 25)):
                    if not math.isclose(rep["target_motion"][motion], base*rep["parameters"][shape]):
                        raise ValueError("Gate dimensions and target motion disagree")
    evidence = plan["current_evidence"]
    keys = ("baseline_assets", "baseline_motion", "baseline_review", "baseline_geometry_certificate",
            "concept_image", "concept_manifest")
    for key in keys:
        if not (ROOT / evidence[key]).exists():
            raise FileNotFoundError(evidence[key])
    baseline = json.loads((ROOT / evidence["baseline_review"]).read_text())
    geometry = json.loads((ROOT / evidence["baseline_geometry_certificate"]).read_text())
    concept = json.loads((ROOT / evidence["concept_manifest"]).read_text())
    if not (baseline["complete_physical_demo_passed"] and geometry["passed"]):
        raise ValueError("The plan's existing source evidence is no longer supported")
    if baseline["generic_contact_robustness_passed"] is not False:
        raise ValueError("Contact evidence changed; review and version the design plan")
    if concept["new_variants_meshes_created"] or concept["new_variants_ik_verified"]:
        raise ValueError("Concept provenance changed; review the plan status")
    return dict(schema_and_parameter_consistency_passed=True,
                cited_evidence_status_checked=True, family_count=3, representative_count=9,
                existing_reference_execution_count=1, unbuilt_representative_count=8,
                release_eligible_count=0, new_geometry_checks_run=False,
                new_ik_checks_run=False, new_physics_checks_run=False,
                scope="design specification and existing evidence consistency only")


def export(output=DEFAULT_OUTPUT):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    plan = json.loads(PLAN_PATH.read_text())
    result = audit(plan)
    result["plan_sha256"] = hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest()
    (output / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2)+"\n")
    (output / "plan_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")

    def relative(path):
        return os.path.relpath(ROOT / path, output)

    cards, parameter_tables = [], []
    for family in plan["families"]:
        for rep in family["representatives"]:
            parameters = " · ".join(f'{escape(family["appearance_axes"][k]["feature_zh"])} × {v:g}'
                                    for k, v in rep["parameters"].items())
            status = "已有参考执行；接触对照未通过" if rep["id"] == "A0" else "候选设计 · 未建模／未验收"
            cards.append(f'''<article data-family="{family['id']}"><p class="family">{family['id']} · {escape(family['name_zh'])}</p>
<h2>{rep['id']} {escape(rep['name_zh'])}</h2><span class="status">{status}</span>
<p>{escape(rep['visual_zh'])}</p><p class="params">{parameters}</p>
<p><strong>对应动作：</strong>{escape(rep['ik_zh'])}</p><code>{rep['ik_id']}</code></article>''')
        rows = "".join(f'<tr><td>{escape(a["feature_zh"])}</td><td><code>{escape(k)}</code></td><td>{a["candidate_bounds"][0]:g}–{a["candidate_bounds"][1]:g}</td><td>尚无已验证范围</td></tr>'
                       for k, a in family["appearance_axes"].items())
        parameter_tables.append(f'<section data-family="{family["id"]}"><h2>{family["id"]} · 候选参数空间</h2><p>{escape(family["motion_signature_zh"])}</p><div class="scroll"><table><tr><th>特征</th><th>参数</th><th>候选倍率</th><th>验证范围</th></tr>{rows}</table></div></section>')
    concept = relative(plan["current_evidence"]["concept_image"])
    spec = relative("docs/develop/tasks/interlocked_claws_zh.md")
    baseline = relative("runs/demo_metadata/interlocked_claws/2026-09-17_reference_full_v1/reliability.html")
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claw · 三个 Family 与九个代表</title><style>
*{{box-sizing:border-box}}body{{margin:35px auto;padding:0 24px;max-width:1440px;background:#f0f3f5;color:#25313c;font:16px/1.75 system-ui}}
h1{{font-size:32px}}h2{{font-size:21px;margin:8px 0}}a{{color:#226d87}}section,article{{background:white;border:1px solid #dde3e7;border-radius:12px;padding:22px;margin:18px 0}}
.note{{background:#fff0ce;padding:18px 22px;border-radius:10px}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}article{{margin:0}}
.family{{color:#527180;font-size:14px;margin:0}}.status{{display:inline-block;background:#fff0ce;padding:3px 8px;font-size:13px;border-radius:5px}}
.params{{color:#52616b;font-size:14px}}code{{font-size:13px;overflow-wrap:anywhere}}button{{padding:10px 18px;border:1px solid #bbcbd3;background:white;border-radius:7px;cursor:pointer;margin:4px}}
button.active{{background:#234959;color:white}}img{{display:block;width:100%;border-radius:10px}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #dde3e7}}.scroll{{overflow:auto}}
.flow{{display:flex;gap:10px;flex-wrap:wrap;align-items:center}}.flow span{{background:#e8f0f3;padding:10px 15px;border-radius:6px}}
details>summary{{cursor:pointer}}[hidden]{{display:none!important}}@media(max-width:1050px){{.grid{{grid-template-columns:1fr}}}}</style>
<p>TOPOGYM / INTERLOCKED CLAWS / DESIGN SPACE v1</p><h1>三个动作 Family × 三个代表构型</h1>
<p>顶层选择解锁动作与结构机制；各 family 内改变轮廓、层次、跨度和深度，并重新求匹配的双臂 IK。</p>
<p class="note"><strong>当前为规划。</strong>原版 A0 已完成声明的理想辅助抓持参考执行，但接触对照仍未通过。其余八个实例尚未建模或验证。本页不宣称九个实例已经有解，随机生成器尚未启用。</p>
<section><details><summary>展开三种基础构型概念图（不代表九个已生成模型）</summary><a href="{concept}"><img src="{concept}" alt="三个动作家族的结构概念图"></a></details></section>
<nav aria-label="Family 筛选"><button class="active" data-filter="all">全部 9 个代表</button><button data-filter="A">A · 圆杆回钩</button><button data-filter="B">B · 螺旋冠</button><button data-filter="C">C · 正交双窗</button></nav>
<p>数值是首轮设计目标。每个 family 内的倍率以自己的基型为参考；B/C 的实际 CAD 尺寸尚待建模确定。</p>
<div class="grid">{''.join(cards)}</div>{''.join(parameter_tables)}
<section><h2>随机生成机制</h2><div class="flow"><span>均衡选择 family</span>→<span>选择已验收代表</span>→<span>联合提案形状与运动</span>→<span>IK + 扫掠反推</span>→<span>几何／物理／视觉验收</span>→<span>入合格库后随机抽样</span></div>
<p>先完成三个基型，再完成九个代表，然后探索各代表的局部条件参数域。区间的笛卡尔积不等于可解空间；失败只在原 family 内重试，耗尽预算时返回明确拒绝。颜色与光照另行随机化。</p></section>
<section><h2>必须同时通过</h2><p>实体连通与水密、连续解锁路径、关键省略动作的阻挡对照、双臂与桌面碰撞、肉眼可辨、完整受力执行与半时间步复测、落架释放后的稳定性。新形状不继承旧录像的物理通过状态。</p>
<p><a href="{spec}">完整设计规范与实施顺序</a> · <a href="plan.json">机器可读参数规划</a> · <a href="plan_audit.json">规划一致性检查</a> · <a href="{baseline}">原版实际物理证据</a></p></section>
<script>document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{{const id=b.dataset.filter;document.querySelectorAll('[data-family]').forEach(c=>c.hidden=id!=='all'&&c.dataset.family!==id);document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));}}));</script></html>'''
    (output / "index.html").write_text(page)
    for url in re.findall(r'(?:href|src)="([^"#]+)', page):
        if not (output / url).exists():
            raise FileNotFoundError(f"Broken plan link: {url}")
    result["review_local_links_passed"] = True
    (output / "plan_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    print(export(parser.parse_args().output))
