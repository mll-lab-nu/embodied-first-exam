"""Summarize preparation and checksum-matched smoke evidence; never dispatch trials."""
import collections,csv,json
from pathlib import Path
from common import ROOT,REGISTRY,read,write

def main():
 data=read(REGISTRY);proofs=[]
 for p in sorted((ROOT/'jobs').glob('two-modes-v3-smoke-*/*-lifecycle.json')):
  d=read(p);d['evidence_path']=str(p.relative_to(ROOT))
  if d.get('role')=='oracle' and '-unlimited' in d.get('task_id','') and d.get('result'):
   exit_file=(ROOT/d['result']).parent/'agent/exit-code.txt'
   if (exit_file.exists() and exit_file.read_text().strip()!='0') or not (exit_file.parent/'oracle.txt').exists():d['passed']=False
  proofs.append(d)
 counts=[];flat=[];physical={}
 for b in ('vlabench','metaworldplus','robocasa','robocasa365','robocasa-gr1'):
  rs=[r for r in data['instances'] if r['benchmark']==b]
  counts.append(dict(benchmark=b,families=len({r['family'] for r in rs}),instances=len(rs),unlimited_configured=sum(not r['modes']['unlimited']['blocked_reason'] for r in rs),limited_configured=sum(not r['modes']['limited']['blocked_reason'] for r in rs),unavailable_unlimited=sum(bool(r['modes']['unlimited']['blocked_reason']) for r in rs),unavailable_limited=sum(bool(r['modes']['limited']['blocked_reason']) for r in rs)))
  for r in rs:
   if r['instance_sha256']:physical.setdefault((b,r['instance_sha256']),[]).append(r['source_task_id'])
   for mode,m in r['modes'].items():
    evidence={}
    for role in ('oracle','nop'):
     candidates=[p for p in proofs if p['task_id']==m['task_id'] and p.get('role')==role and p.get('task_checksum')==m.get('task_checksum')]
     if candidates:evidence[role]=candidates[-1]
    admitted=all(evidence.get(k,{}).get('passed') for k in ('oracle','nop'))
    m['validation']='smoke_oracle_nop_passed' if admitted else 'unavailable' if m['blocked_reason'] else 'configuration_checked_not_dynamically_tested'
    m['smoke_evidence']={k:v['evidence_path'] for k,v in evidence.items()}
    flat.append(dict(benchmark=b,source_task_id=r['source_task_id'],mode=mode,path=m['path'],task_id=m['task_id'],seed=r['seed'],instance_sha256=r['instance_sha256'],status=m['validation'],reason=m['blocked_reason'],oracle=evidence.get('oracle',{}).get('passed'),nop=evidence.get('nop',{}).get('passed')))
 write(REGISTRY,data)
 report=ROOT/'docs/validation/two-modes-v3';report.mkdir(parents=True,exist_ok=True)
 with (report/'instances.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
 aliases=[dict(benchmark=b,instance_sha256=s,task_ids=ids) for (b,s),ids in physical.items() if len(ids)>1]
 write(report/'summary.json',dict(counts=counts,configured_modes=sum(c['unlimited_configured']+c['limited_configured'] for c in counts),unavailable_mode_records=sum(c['unavailable_unlimited']+c['unavailable_limited'] for c in counts),smoke_admitted_modes=sum(r['status']=='smoke_oracle_nop_passed' for r in flat),model_requests=0,physical_instance_aliases=aliases))
 lines=['# 统一 limited / unlimited 任务修订报告','','本轮只整理、配置检查及小规模无模型 smoke；没有运行模型评测。历史结果保持原版本身份。','','## 实际协议','','- Unlimited：privileged state，同实例任意 reset、探索；无单轨迹/累计步数、reset、token 或模型调用配额；agent 3600 秒。用户最新要求覆盖引用文档中“保留原生 horizon”条款。MetaWorld 的时长截断关闭，原生成功谓词和冻结物理状态不变。','- Limited：RGB、机器人自身状态及相机标定；单连续 episode，无 reset；四方法接口，私有 sim 完整记录；保留原任务 episode 上限（MetaWorld 500、VLABench 4000、RoboCasa 3000，旧导航1200 controls）。其中 VLABench/RoboCasa 数字是仓库轨迹协议上限，不宣称都是上游原生 horizon。','- 仿真和 agent 安装就绪后计时；60分钟独立 watchdog 停止 main，停止之后封存/收集/双重放单独计时。Unlimited 首个 Session 在可信 setup 阶段预初始化；随后 reset/新增 Session 计入探索时间。','- Limited online + 两次 fresh replay 必须成功且精确状态一致。超时不能被重放成功覆盖。Unlimited 只评分最后提交的轨迹；同容器 privileged runtime 的计数不具有 sidecar 级抗篡改性。','','## 覆盖','','| Benchmark | 任务族 | 实例 ID | Unlimited 已配置 | Limited 已配置 | 未就绪 U/L |','|---|---:|---:|---:|---:|---:|']
 for c in counts:lines.append(f"| {c['benchmark']} | {c['families']} | {c['instances']} | {c['unlimited_configured']} | {c['limited_configured']} | {c['unavailable_unlimited']}/{c['unavailable_limited']} |")
 lines+=['','VLABench 保留96个原生任务ID与8个历史视觉ID；91个有冻结实例，13个缺少冻结实例，两模式均保留不可运行记录。8组视觉/privileged别名对应同一物理实例，清单显式标注，不能将它们当作独立随机样本。MetaWorld limited 中原先不可观察目标的实例继续标为未就绪，不增加隐藏坐标提示。','','## 验证','','[配置检查](config-check.json)逐项检查 task ID、冻结实例字节、权限/网络配置、实际代码中的预算、解析及目录指纹。','[长轨迹 smoke](unbounded-metaworld/result.json)执行501个原生controls越过旧500 horizon，并在两个新进程重放，在线/重放精确一致。','[全量 CI 日志](ci-final.log)、[四项执行边界测试](unit-tests.log)、[源码与工具指纹](provenance.json)、[Harbor oracle 退出码语义审计](oracle-exit-code-audit.json)。',
 '实际 smoke 证据按当前任务 checksum 关联；旧版本通过不自动算新版通过。其余实例只声明配置检查完成，未全量重新仿真。','','| Benchmark | Mode | Oracle | Nop | 当前版本证据 |','|---|---|---|---|---|']
 for r in flat:
  if r['oracle'] is not None or r['nop'] is not None:
   lines.append(f"| {r['benchmark']} | {r['mode']} | {r['oracle']} | {r['nop']} | `{r['task_id']}`（suite 内 smoke_evidence） |")
 lines+=['','初期 smoke 的 nft 语法错误、目录迁移期间的路径故障以及 warm Session 与旧 oracle 的兼容故障均保留在各自 jobs 目录；修复后使用新 smoke 目录，不删除失败证据。','','## 目录与复现','','当前任务唯一入口为 `limited_tasks/<benchmark>/`、`unlimited_tasks/<benchmark>/`；原版本位于 `archive/task_versions/pre-unified-20260929/`。`tasks/`仅剩此次范围以外的任务。','清单：[逐实例 CSV](instances.csv)、[统一 registry](../../../suites/two-modes.json)、[迁移映射](../../../suites/task-path-aliases.json)。历史 jobs、视频及离线网页未重新评分/重命名。','运行命令见 [统一使用说明](../../TWO_MODES.md)。旧模型运行器仅保留历史 report 入口；新实验使用统一 runner。']
 lines+=['','## 未就绪记录','','以下记录保留在覆盖分母；本轮不重采样、不补造冻结实例。完整 source、seed 与哈希见统一 registry。','','| 实例 | 受影响模式 | 原因 |','|---|---|---|']
 for r in data['instances']:
  modes=[k for k,m in r['modes'].items() if m['blocked_reason']]
  if modes:
   reason='缺少已冻结的实例文件，不能保持原始初态进行可信重放' if any(r['modes'][k]['blocked_reason']=='missing_frozen_instance' for k in modes) else '原始目标在允许的视觉观测中不可确定；不添加隐藏目标坐标'
   lines.append(f"| `{r['source_slug']}` | {', '.join(modes)} | {reason} |")
 (report/'REPORT.md').write_text('\n'.join(lines)+'\n')
 print(json.dumps(counts,indent=2));print('Current checksum-matched smoke admissions:',sum(r['status']=='smoke_oracle_nop_passed' for r in flat))
if __name__=='__main__':main()
