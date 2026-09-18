"""Review the fixed-command baseline retained alongside trajectory variants."""
from html import escape
import json
from pathlib import Path


def write_review(output):
    output = Path(output)
    report = json.loads((output/"variants_report.json").read_text())
    rows = "".join(f'<tr><td>{escape(r["title_zh"])}</td><td>{r["radii"]}</td>'
        f'<td>{r["wire_radius"]}</td><td>{"通过" if r["passed"] else "拒绝"}</td>'
        f'<td><a href="variants/{r["id"]}/compatibility.json">报告</a></td></tr>' for r in report["results"])
    (output/"index.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>Horseshoe 固定 trace 对照</title><style>body{{max-width:1000px;margin:40px auto;font:17px/1.7 system-ui}}
td,th{{padding:10px;text-align:left;border-bottom:1px solid #ddd}}table{{border-collapse:collapse;width:100%}}</style>
<h1>固定 trace 对照基线</h1><p>该轮固定全部关节和时序，作为后续“轨迹变化 → 场景反推”的对照。
共 {report['qualified']}/{report['candidates']} 个离散变体通过几何与采样机器人检查；均未验证动力学执行。</p>
<p><a href="ik_trace.json">IK trace JSON</a> · <a href="ik_trace.csv">CSV</a> · <a href="variants_report.json">全部结果</a></p>
<table><tr><th>变体</th><th>链环中心线半轴 / 模板 mm</th><th>线半径 / 模板 mm</th><th>结果</th><th>证据</th></tr>{rows}</table>
<p>演示场景尺寸为模板两倍。通过离散候选不等于整个参数区间通过；直线正反向拉环失败，不是所有捷径都已排除。</p></html>''')
