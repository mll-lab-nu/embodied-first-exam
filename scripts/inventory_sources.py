"""Generate the whole-repository source inventory using text and AST only.

This program never imports project modules or executes tests, simulators, agent
clients, source snapshots, or shell scripts. Run it again after source edits.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import quote


EXTENSIONS = {
    ".py", ".pyi", ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    ".js", ".cjs", ".mjs", ".ts", ".cts", ".mts", ".jsx", ".tsx", ".html", ".htm",
    ".css", ".scss", ".sass", ".vue", ".svelte", ".ipynb", ".c", ".cc", ".cpp",
    ".cxx", ".h", ".hh", ".hpp", ".cu", ".cuh", ".rs", ".go", ".java", ".lua",
    ".r", ".rb", ".pl", ".awk", ".cmake", ".sql", ".jl", ".swift", ".kt", ".kts",
}
SCRIPT_NAMES = {"Makefile", "GNUmakefile", "Dockerfile", "CMakeLists.txt", "Justfile"}
EXCLUDED = {".git", ".external", "__pycache__", "node_modules", ".cache", ".pytest_cache",
            ".ruff_cache", ".mypy_cache", "__nyx_cache__", ".tox", ".nox", ".ipynb_checkpoints"}
HISTORY_ROOTS = {"runs", "legacy", "reports", "assets"}
TEST_DOCUMENT = "simulator_test_scripts_zh.md"
IMPLEMENTATION_DOCUMENT = "simulator_public_api_implementation_20260924_zh.md"
GROUPS = [
    ("config", "Config / Registry：配置、任务身份和构造规格"),
    ("simulator", "Simulator：公共入口、管理方与操作方接口、配置、生命周期和单条历史"),
    ("world", "World：Genesis 场景、积分、状态与视觉设置"),
    ("robot", "Robot：本体、关节命令与显式抓持"),
    ("solvers", "Solvers：FK / IK、碰撞和数值几何"),
    ("sensors", "Sensors：同状态观测、相机与标定"),
    ("tasks", "Task：实体、初态、目标与可恢复判据"),
    ("assets", "Assets：几何、物理材料、外观和资源定位"),
    ("planning", "Planning：无物理副作用的参考运动"),
    ("recording", "Recording：共享帧采样、编码与输出生命周期"),
    ("data", "Dataset：真实 transition 序列化"),
    ("evaluation", "Evaluation：布面测量与连续运动间隙证书"),
    ("utils", "Utils / 包入口：纯计算、快照、随机与 I/O"),
    ("tests", "Tests：合同、真实物理与运行证据，结果见测试报告"),
    ("tools", "工程工具与环境安装脚本"),
    ("examples", "公共接口示例与演示脚本"),
    ("documentation", "文档与界面源码"),
    ("deferred", "Agents / API：延期收录，不启用"),
    ("other", "其余现存脚本：未归入 simulator 运行模块"),
]
TASK_NAMES = {
    "cast_coil": "Cast Coil", "cast_keyhole": "Cast Keyhole", "blanket_flatten": "Blanket Flatten",
    "horseshoe_ring": "Horseshoe Ring", "hedgehog_in_cage": "Hedgehog in Cage",
    "interlocked_claws": "Interlocked Claws", "lock_picking": "Lock Picking",
    "buzz_wire_3d": "Buzz Wire 3D", "fiber_bundling": "Fiber Bundling",
    "rope_threading": "Rope Threading", "knot_untying": "Knot Untying",
    "orbits": "Orbits", "slotted_post_ring": "Slotted Post Ring",
}
DESCRIPTIONS = {
    'topogym/config/registry.py': '集中声明任务身份、实现状态及延迟构造入口',
    'topogym/simulator/config.py': '定义并校验任务、设备、时间、观察控制模式和特权授权配置',
    'topogym/config/scene.py': '从公共配置资源构造 Genesis 场景与机器人配置',
    'topogym/simulator/env.py': '管理方统一创建和重置环境，编排动作、观测、逐 tick 保存和截断回溯',
    'topogym/simulator/history.py': '定义 StateRef 与 Transition，维护当前 episode 唯一有效路径并作废旧未来',
    'topogym/simulator/api.py': '提供不初始化引擎的任务列表和统一 make 构造入口',
    'topogym/simulator/interaction.py': '向操作方开放 episode 绑定接口，普通及特权模式均不开放 reset',
    'topogym/simulator/privileged.py': '提供当前 episode 内回溯与白名单只读细节查询，不允许切换 seed',
    'topogym/robot/control.py': '将 JOINT_ABS/DELTA 和 EE_ABS/DELTA 转为同一机器人关节目标',
    'topogym/world/genesis_world.py': '集中拥有 Genesis 场景、唯一物理推进与完整状态保存恢复',
    'topogym/world/state.py': '复制和恢复引擎数值缓冲及随机状态供 episode 历史使用',
    'topogym/world/entities.py': '维护实体名称到 Genesis 句柄的运行时注册表',
    'topogym/world/tabletop.py': '构建公共桌面、机器人及可选相机的 Genesis 场景',
    'topogym/world/visuals/nyx.py': '把外观规则应用到 Genesis 实体的 Nyx 表面',
    'topogym/world/visuals/lighting.py': '把公共照明配置转换为 Genesis 可视化选项',
    'topogym/world/visuals/surfaces.py': '把外观参数转换为 Genesis 表面并保留渲染材质',
    'topogym/world/visuals/presentation.py': '配置公共场景外观并安装声明的渲染相机',
    'topogym/robot/joint_position.py': '按关节组统一校验控制目标及保存恢复两种机器人控制状态',
    'topogym/solvers/genesis_kinematics.py': '通过 Genesis 机器人实体提供共享 FK 与 IK 查询',
    'topogym/solvers/collision/box_compounds.py': '计算盒组合在刚体相对姿态下的 SAT 间隙下界',
    'topogym/solvers/collision/convex_compounds.py': '计算闭合凸网格组合的 SAT 分离、接触和重叠',
    'topogym/sensors/observation.py': '按 episode、branch 和 state 缓存不可变观测与 SensorFrame',
    'topogym/sensors/camera_info.py': '计算相机内参与明确坐标约定的外参元数据',
    'topogym/sensors/cameras.py': '集中创建相机、安装关系、动态位姿及诊断预览入口',
    'topogym/tasks/base.py': '定义 Task 实体声明、状态、观测与结果的公共接口',
    'topogym/assets/robot.py': '解析机器人模型资源位置并构造加载参数',
    'topogym/utils/geometry/rigid_motion.py': '统一刚体平移与旋转运动段、材料位移界及姿态插值',
    'topogym/recording/session.py': '消费单个 episode 分支的共享帧并管理同步视频输出',
    'topogym/recording/encoding.py': '通过公共流式 writer 调用 ffmpeg 编码及媒体探测',
    'topogym/recording/timeline.py': '根据源仿真时间计算媒体抽样序号与目标时间',
    'topogym/data/episode_dataset_writer.py': '流式保存真实动作和前后观测并记录历史恢复分支关系',
    'topogym/data/h5_schema.py': '声明实际 Transition 的数据版本及必需字段',
    'topogym/evaluation/cloth_metrics.py': '测量布面覆盖、拉伸和速度并应用显式阈值',
    'topogym/evaluation/motion_certificate.py': '对共享碰撞查询协议应用唯一自适应连续运动间隙证书',
    'topogym/utils/io.py': '统一文件哈希、JSON 转换、原子写入与来源元数据',
    'topogym/utils/snapshots.py': '深拷贝并冻结数值记录以及为状态拥有者创建可写副本',
    'topogym/utils/arrays.py': '明确数值数组转到主机后的复制与所有权语义',
    'topogym/utils/variant_rng.py': '由种子和用途名称派生可重复随机流',
    'topogym/utils/geometry/rigid_geometry.py': '提供刚体网格、截面或拓扑测量的公共数值工具',
    'topogym/utils/geometry/rope.py': '生成和处理绳中心线、管状网格与基础几何',
    'scripts/inventory_sources.py': '仅以文本和 AST 遍历全仓并生成当前脚本清单及历史路径索引',
    'scripts/prepare_nyx_studio.py': '下载并校验 Nyx 演示使用的 CC0 棚拍 HDRI 与木材贴图',
    'env_setup_gs121.sh': '建立 Genesis 1.2.1 环境并按脚本选项安装依赖和检查环境',
    'tests/conftest.py': '提供测试收集配置、能力选择与共享夹具',
    'tests/architecture/test_module_boundaries.py': '静态约束模块依赖、唯一物理入口与历史源码隔离',
    'tests/unit/test_configuration.py': '检查配置约束、机器人默认选择、唯一实验室及任务注册信息',
    'tests/unit/test_task_definitions.py': '检查任务声明、实体规格和任务身份的一致性',
    'tests/unit/test_task_state.py': '检查 Task 保存恢复的判据状态及结果语义',
    'tests/unit/test_collision_certificates.py': '检查盒与凸网格间隙、旋转运动及连续证书通过和碰撞拒绝',
    'tests/contracts/test_env_lifecycle.py': '检查公共 Env 生命周期、动作校验和终止行为',
    'tests/contracts/test_episode_rewind.py': '检查 episode 历史恢复、分支保留和身份约束',
    'tests/integration/test_task_lifecycle.py': '在显式选择时检查真实 Genesis 任务生命周期',
    'tests/integration/test_genesis_world_history.py': '在显式选择时检查真实引擎状态恢复和后续轨迹',
    'tests/integration/test_genesis_robot.py': '在显式选择时检查真实机器人目标控制与本体状态',
    'tests/recording_data/test_dataset_transitions.py': '检查六关节和单指轨道指令序列化、分支来源及 JSONL 或 HDF5 读回',
    'tests/recording_data/test_recording_branches.py': '用假 writer 检查多视角同步、分支边界和不完整产物',
    'tests/recording_data/test_snapshot_isolation.py': '检查数值快照隔离、不可变性及同 tick 状态恢复的缓存更新',
    'topogym/assets/library.py': '按清单校验静态资源并记录生成资产的路径与哈希',
    'topogym/assets/materials.py': '声明和校验刚体、PBD 与 FEM 物理材料参数',
    'topogym/assets/textures.py': '生成可复现的织纹、格纹条纹和彩色角点，并可写为纹理资产',
    'topogym/world/physics/pbd.py': '把公共 PBD 材料声明转换为 Genesis Cloth 或 Elastic',
    'topogym/world/physics/fem.py': '构造显式 FEM 体网格实体及材料，读取顶点、速度与材料索引',
    'topogym/world/physics/ipc.py': '桥接 Genesis 与原生 IPC，统一子步、永久连接及分支快照恢复',
    'topogym/assets/geometry/rope_volume.py': '从中心线生成对应的初始四面体管网格、直绳参考形与末端止挡',
    'scripts/test_base_tasks.py': '串行运行十三项基础环境和公共机制测试，保存源码、报告与真实录像',
    'tests/runtime_evidence.py': '保存阶段报告、状态数组与 IPC 指纹，并通过公共录制器采集测试帧',
    'tests/integration/test_base_task_runtime.py': '逐项检验基础任务的步进、观测、任意历史续跑和 seed 重建',
    'tests/integration/test_genesis_fem_ipc.py': '以小型 FEM 管检验永久连接、原生快照及恢复后续跑',
    'tests/integration/test_task_switch_runtime.py': '同进程切换刚体、FEM、PBD 和两种机器人并验证状态隔离',
    'tests/unit/test_world_diagnostics.py': '检查非有限物理数值报告的字段定位与空接触合法性',
    'topogym/robot/description.py': '定义共享关节组合同并选择 ALOHA 或 Panda＋Robotiq 描述',
    'topogym/robot/aloha/description.py': '声明 ALOHA 双臂、滑动夹爪、限位、home 与控制参数',
    'topogym/robot/panda_robotiq/description.py': '声明 Panda 七轴单臂与 Robotiq 两旋转驱动的组合',
    'topogym/robot/panda_robotiq/gripper.py': '定义 Robotiq 原生旋转驱动名称与弧度范围',
    'topogym/sensors/renderers/nyx.py': '创建 Nyx 相机传感器并转换为共享 RGB 和位姿接口',
    'topogym/solvers/collision/triangle_meshes.py': '对任意网格对与障碍表面执行 FCL 碰撞和间隙查询',
    'topogym/planning/motions/cast_coil.py': '生成 Coil 参考刚体和螺旋运动及采样点',
    'topogym/tasks/task_variations/__init__.py': '旧导入兼容转发，权威变体目录位于 config/registry.py',
    'tests/unit/test_task_support.py': '检查全部任务定义、操作缺口和不完整判据禁止宣称成功',
    'tests/unit/test_asset_library.py': '检查资源哈希、路径边界与允许无网格的生成记录',
    'tests/unit/test_material_specs.py': '检查物理材料参数并区分材料声明和运行资格',
    'tests/unit/test_task_variations.py': '检查变体差异合并、输入隔离及未知变体拒绝',
    'tests/unit/test_robot_descriptions.py': '检查双臂和单臂描述、原生单位、动作原子校验和控制状态',
    'tests/integration/test_genesis_seed_reset.py': '在显式选择时检查两种机器人的初态回溯及 seed A/B/A 重建',
    'topogym/world/lab.py': '声明唯一 compact_lab 布局并构建对应的 Genesis 布景实体',
    'topogym/assets/surfaces.py': '生成共享木纹表面并定义外观角色的粗糙度',
    'topogym/assets/geometry/buzz_wire_3d.py': '统一生成 Buzz Wire 的几何、支撑、木纹和玩具涂装素材',
    'topogym/assets/geometry/lock_picking.py': '统一生成 Lock Picking 的盘钥几何、配色和孔口描边素材',
    'scripts/import_rope_threading_reference.py': '把外部几何和首帧导出数据离线转换成 Rope Threading 参考参数 JSON',
}


def excluded_directory(name):
    return name in EXCLUDED or name.startswith(".venv")


def source_paths(root):
    """Include ignored source files while pruning environments before descent."""
    for folder, directories, filenames in os.walk(root, followlinks=False):
        directories[:] = sorted(name for name in directories if not excluded_directory(name)
                                and not (Path(folder) / name).is_symlink())
        for name in sorted(filenames):
            path = Path(folder) / name
            if path.is_symlink():
                continue
            if path.suffix.lower() in EXTENSIONS or name in SCRIPT_NAMES:
                yield path
            elif not path.suffix:
                try:
                    with path.open("rb") as stream:
                        if stream.read(2) == b"#!":
                            yield path
                except OSError:
                    pass


def classification(relative):
    parts = relative.parts
    if parts[0] in HISTORY_ROOTS:
        return "historical", parts[0]
    if parts[:3] == ("topogym", "agents", "deferred") or parts[:2] == ("topogym", "agents"):
        return "deferred", "deferred"
    if parts[0] == "tests":
        return "current", "tests"
    if parts[0] in {"scripts", "bash"} or len(parts) == 1 and relative.suffix in {".sh", ".bash"}:
        return "current", "tools"
    if parts[0] == "topogym":
        return "current", parts[1] if len(parts) > 2 and parts[1] in dict(GROUPS) else "utils"
    if parts[0] in {"examples", "demos"}:
        return "current", "examples"
    if parts[0] == "docs":
        return "current", "documentation"
    return "current", "other"


def first_sentence(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    return re.split(r"(?<=[。.!?])\s|(?<=。)", text, maxsplit=1)[0][:180].strip()


def content_metadata(data, suffix):
    text = data.decode("utf-8", errors="replace")
    result = dict(doc="", symbols=[], imports=[], direct_mujoco=False, parse_error=None)
    if suffix not in {".py", ".pyi"}:
        if suffix in {".html", ".htm"}:
            match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
            result["doc"] = first_sentence(match.group(1)) if match else ""
        return result
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as error:
        result["parse_error"] = str(error)
        return result
    result["doc"] = first_sentence(ast.get_docstring(tree))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            result["symbols"].append(dict(name=node.name, kind="function", line=node.lineno))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            methods = [child.name for child in node.body if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and not child.name.startswith("_")]
            result["symbols"].append(dict(name=node.name, kind="class", line=node.lineno, methods=methods))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = ["." * node.level + (node.module or "")]
        else:
            continue
        result["imports"].extend(names)
        result["direct_mujoco"] |= any(name == "mujoco" or name.startswith("mujoco.") for name in names)
    result["imports"] = sorted(set(result["imports"]))
    return result


def description(path, metadata, scope):
    value = path.as_posix()
    if scope != "historical" and value in DESCRIPTIONS:
        return DESCRIPTIONS[value]
    if path.name == "__init__.py":
        return "声明包命名空间并提供该模块的公开导出或说明"
    if len(path.parts) == 3 and path.parts[:2] == ("topogym", "tasks") and path.stem in TASK_NAMES:
        return f"定义 {TASK_NAMES[path.stem]} 的实体、初态和可保存恢复的任务判据"
    task = next((TASK_NAMES[name] for name in (*path.parts, path.stem) if name in TASK_NAMES), "任务")
    if value.startswith("topogym/assets/geometry/"):
        purpose = {"geometry": "几何模型", "gathered_geometry": "聚拢布料初态几何", "anchored_geometry": "固定端纤维几何",
                   "prepare_assets": "模型素材准备", "appearance": "模型外观", "supports": "支撑与夹具几何",
                   "templates": "几何基型", "family_geometry": "家族参数化几何", "family_models": "家族模型",
                   "ring_mount": "环安装几何"}.get(path.stem, "几何模型")
        return f"生成或准备 {task} 的{purpose}素材"
    if value.startswith("topogym/tasks/") and path.name == "common.py":
        return f"定义 {path.parent.name} 的共用实体、判据和状态协议"
    if value.startswith("topogym/tasks/task_variations/"):
        return f"兼容转发 {task} 的旧变体导入"
    if value.startswith("topogym/solvers/collision/"):
        return f"提供 {task} 所需的只读碰撞或间隙查询"
    if scope == "deferred":
        labels = {"runtime": "旧 agent 交互编排", "tool_runtime": "旧工具访问与试验服务", "env_sdk": "旧远程环境客户端",
                  "episode": "旧 episode 子进程管理", "session": "旧 agent 分段会话", "budget": "旧会话预算记账",
                  "token_budget": "旧 token 预算记账", "client": "旧 bridge 客户端", "server": "旧 bridge 服务端",
                  "local": "旧本地 agent worker 与监控", "openai_harness": "旧模型交互调用", "action_program": "旧动作脚本解释",
                  "evaluate": "旧 agent 试验调度与汇总", "initial": "旧 agent 初态审计", "media": "旧 agent 媒体发布",
                  "tool_policy": "旧工具访问规则", "package": "旧 agent 访问包导出", "agent_profiles": "旧 agent 访问模式配置",
                  "agent_suite": "旧 agent 评测配置与工厂", "agents": "旧决策客户端集合", "isolation": "旧进程访问隔离",
                  "budget_proxy": "旧预算代理", "register_openpi_config": "旧 OpenPI 训练配置注册",
                  "dashboard": "旧 agent 控制面板", "__main__": "旧 agent 命令行入口"}
        if "task_specs" in path.parts:
            return f"保存 {task} 的旧 agent 动作说明以供后续审阅"
        if "tests" in path.parts:
            return "保存旧 agent 接入、运行检查或试验脚本以供后续审阅"
        return f"保存{labels.get(path.stem, metadata['doc'] or path.stem)}以供后续审阅"
    if metadata["doc"]:
        return "源码说明：" + metadata["doc"]
    if path.suffix in {".html", ".htm", ".css", ".scss", ".sass"}:
        return "保存页面呈现、交互结构或样式"
    if path.suffix in {".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd"}:
        return "按脚本中的命令组织环境或作业执行"
    if metadata["symbols"]:
        return "提供下列源码中实际声明的计算或执行入口"
    return "保存顶层脚本语句或模块级数据定义"


def functional_summary(metadata, suffix, name):
    entries = []
    priority = ("reset", "step", "observe", "render", "close", "append", "finish", "sample", "declare", "bind",
                "update", "capture_state", "restore_state", "get_state", "set_state")
    for symbol in metadata["symbols"][:8]:
        entry = f"`{symbol['name']}`"
        methods = symbol.get("methods", [])
        if methods:
            selected = [item for item in priority if item in methods]
            selected += [item for item in methods if item not in selected]
            entry += "（" + "、".join(f"`{item}`" for item in selected[:5]) + ("等" if len(methods) > 5 else "") + "）"
        entries.append(entry)
    if entries:
        return "、".join(entries) + (f"；另有 {len(metadata['symbols']) - 8} 项顶层声明见 JSON" if len(metadata["symbols"]) > 8 else "")
    if name == "__init__.py":
        return "包标记／导出约定"
    if name == "h5_schema.py":
        return "`SCHEMA_VERSION`、`TRANSITION_FIELDS`"
    if suffix in {".html", ".htm"}:
        return "HTML 页面结构与内嵌脚本"
    if suffix in {".css", ".scss", ".sass"}:
        return "页面样式规则"
    if suffix in {".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd"}:
        return "shell／作业命令入口（本轮未执行）"
    return "顶层语句、常量或模块初始化"


def escape(value):
    return value.replace("\n", " ").replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")


def source_link(path):
    return f"[{escape(path)}](../../../{quote(path, safe='/._-')})"


def generate(root):
    files, contents = [], {}
    for path in source_paths(root):
        relative = path.relative_to(root)
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        # Parsing depends on suffix; byte-identical empty __init__ and shell
        # files must not accidentally share a different parser's metadata.
        key = digest + ":" + path.suffix.lower()
        if key not in contents:
            contents[key] = content_metadata(data, path.suffix.lower())
        scope, module = classification(relative)
        files.append(dict(path=relative.as_posix(), scope=scope, module=module,
                          sha256=digest, size_bytes=len(data), content_key=key,
                          description=description(relative, contents[key], scope)))
    files.sort(key=lambda item: item["path"])
    timestamp = datetime.now(timezone.utc).isoformat()
    main = [item for item in files if item["scope"] != "historical"]
    historical = [item for item in files if item["scope"] == "historical"]
    historical_groups, main_hashes = defaultdict(list), defaultdict(list)
    for item in historical:
        historical_groups[item["sha256"]].append(item)
    for item in main:
        main_hashes[item["sha256"]].append(item["path"])
    counts = dict(total=len(files), current=sum(item["scope"] == "current" for item in files),
                  deferred=sum(item["scope"] == "deferred" for item in files), main=len(main),
                  historical=len(historical), historical_unique_contents=len(historical_groups),
                  unique_contents=len({item["sha256"] for item in files}),
                  by_module=dict(sorted(Counter(item["module"] for item in main).items())),
                  historical_roots=dict(sorted(Counter(item["module"] for item in historical).items())),
                  direct_mujoco_by_scope={scope: sum(item["scope"] == scope and contents[item["content_key"]]["direct_mujoco"] for item in files)
                                          for scope in ("current", "deferred", "historical")})
    target = root / "docs/develop/dev-logs"
    target.mkdir(parents=True, exist_ok=True)
    scan = dict(schema_version=2, generated_at_utc=timestamp,
                generator="scripts/inventory_sources.py", method="filesystem bytes, SHA-256 and Python AST only; no project imports or execution",
                extensions=sorted(EXTENSIONS), special_names=sorted(SCRIPT_NAMES),
                excluded_directories=sorted(EXCLUDED) + [".venv*", "symbolic links"],
                counts=counts, files=files, contents=contents)
    (target / "script_inventory_20260923.json").write_text(json.dumps(scan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    render_main(target, timestamp, main, historical_groups, contents, counts)
    render_history(target, timestamp, historical_groups, main_hashes, contents, counts)
    print(json.dumps(counts, ensure_ascii=False, indent=2))


def render_main(target, timestamp, files, historical_groups, contents, counts):
    lines = ["# 当前全仓代码脚本清单：标准 simulator 模块与延期内容", "",
             f"扫描时间（UTC）：`{timestamp}`。本页按**当前实际路径和内容**更新，替代本文件此前移动前的旧路径清单。", "",
             f"全仓识别 **{counts['total']:,}** 个代码脚本：本页逐项列出 **{counts['main']:,}** 个非历史脚本（其中延期 agent/API **{counts['deferred']:,}** 个），另有 **{counts['historical']:,}** 个历史目录路径，按 **{counts['historical_unique_contents']:,}** 份完全相同内容分组列于[历史源码完整附录](script_snapshots_inventory_zh.md)。", "",
             f"当前实施边界见[本轮整理记录]({IMPLEMENTATION_DOCUMENT})；测试脚本的目标、条件与运行入口见[逐脚本测试说明]({TEST_DOCUMENT})，实际结果以对应 runs/test_results 报告为准。", "",
             "**数量是文件事实，不是运行资格。** 当前代码、辅助建模代码、已编写测试与延期 agent 分开列出；13 项 Task 均有定义，操作缺口与验证状态以 `config/registry.py` 为准，integrated 不等于可以运行或已经通过验证。", "",
             "本生成器只读取文件、计算 SHA-256 和分析 Python AST；没有导入项目、运行 pytest/collect、执行安装、仿真、录制或 API。历史副本仍存在，不因退出活动依赖而被写成‘已删除’。", "",
             "## 扫描口径", "",
             "- 范围是整个仓库，包括忽略的 runs、legacy、reports、根 assets 代码，以及 tests、scripts、根目录、文档内实际代码文件；不是只扫描 topogym。",
             "- 包含 Python、shell、JS/TS、HTML/CSS、notebook、C/C++/CUDA 等代码扩展名，以及无扩展名 shebang 和 Makefile/Dockerfile/CMakeLists 等脚本。",
             "- 排除 `.git`、`.venv*`、`.external`、node_modules 和明确缓存目录；不遍历符号链接，不展开 ZIP，不把 Markdown 代码块、YAML/JSON/XML 配置、URDF/MJCF、模型与视频计作代码脚本。",
             "- 文件 SHA-256、全部路径、AST 声明及完整排除规则见[机器可读扫描结果](script_inventory_20260923.json)；每条短哈希用于查询，不表示不同文件的行为等价。",
             "- 每个非历史文件只列一次，格式为‘链接 — 一句简介；功能入口；状态；SHA’；没有中文摘要的历史脚本使用源码首句，未凭文件名证明其行为。", "",
             f"本轮 AST 发现：当前脚本直接 MuJoCo import **{counts['direct_mujoco_by_scope']['current']}** 处文件，延期目录 **{counts['direct_mujoco_by_scope']['deferred']}**，历史目录 **{counts['direct_mujoco_by_scope']['historical']:,}**；第三方 Genesis 的库依赖不在这项项目源码计数中。", "",
             "## 模块导航", ""]
    for group, title in GROUPS:
        count = counts["by_module"].get(group, 0)
        if count:
            lines.append(f"- [{title}（{count}）](#module-{group})")
    lines += ["", "## 历史目录覆盖", "", "| 现存目录 | 代码路径数 | 索引 |", "|---|---:|---|"]
    for group, count in counts["historical_roots"].items():
        lines.append(f"| `{group}/` | {count:,} | [按完整 SHA 分组的全部路径](script_snapshots_inventory_zh.md) |")
    for group, title in GROUPS:
        selected = [item for item in files if item["module"] == group]
        if not selected:
            continue
        lines += ["", f'<a id="module-{group}"></a>', f"## {title}", "", f"本组 **{len(selected)}** 个文件。", ""]
        if group == "deferred":
            lines += ["以下保留作后续审阅，**不启用、不接入 simulator、不执行 API/agent 实验**；旧 import 未承诺可运行，发行应排除 deferred。", ""]
        for item in selected:
            meta = contents[item["content_key"]]
            suffix = Path(item["path"]).suffix
            purpose = functional_summary(meta, suffix, Path(item["path"]).name)
            status = "延期，不启用" if item["scope"] == "deferred" else "当前源码，未由清单证明可运行"
            if group == "tests":
                status = f"逐项执行状态见[测试说明]({TEST_DOCUMENT})及本轮实测报告"
            line = f"- {source_link(item['path'])} — {escape(item['description'])}；功能：{purpose}；状态：{status}；SHA-256：`{item['sha256'][:16]}`。"
            matching = historical_groups.get(item["sha256"])
            if matching:
                line += f" 历史目录有[同内容 {len(matching)} 路径](script_snapshots_inventory_zh.md#sha-{item['sha256']})。"
            if meta["direct_mujoco"]:
                line += " **静态直接 import MuJoCo。**"
            if meta["parse_error"]:
                line += " AST 未解析，详见 JSON 中的 parse_error。"
            lines.append(line)
    lines += ["", "## 如何刷新", "", "源码整理结束后运行以下文本清单生成器即可更新本页、附录和 JSON；该命令不执行项目代码或测试。", "", "```bash", "python scripts/inventory_sources.py", "```", ""]
    (target / "script_inventory_zh.md").write_text("\n".join(lines), encoding="utf-8")


def render_history(target, timestamp, groups, main_hashes, contents, counts):
    lines = ["# 历史目录的全量代码路径与内容分组", "", f"扫描时间（UTC）：`{timestamp}`。", "",
             f"本页列出 runs、legacy、reports、根 assets 中当前仍存在的 **{counts['historical']:,}** 个代码路径，按完整 SHA-256 分为 **{len(groups):,}** 组；每个路径恰好出现一次。", "",
             "这些路径是历史执行快照、旧代码、报告生成器或资产来源副本，**不是活动 simulator 的新增模块**；本次清单没有删除它们，也没有执行或导入其中源码。", "",
             "当前功能模块与全部非历史脚本见[主清单](script_inventory_zh.md)；每个文件的完整 SHA、大小及静态声明见[扫描 JSON](script_inventory_20260923.json)。内容哈希相同只证明字节相同，不证明不同版本能互换。", "",
             "## 目录计数", "", "| 目录 | 代码路径数 |", "|---|---:|"]
    for group, count in counts["historical_roots"].items():
        lines.append(f"| `{group}/` | {count:,} |")
    lines += ["", "## 完整路径分组", "", "组内保留所有路径，建议按文件名、任务名或 SHA 搜索；不会把同名不同内容的文件合在一起。", ""]
    ordered = sorted(groups.items(), key=lambda pair: (pair[1][0]["path"], pair[0]))
    for index, (digest, items) in enumerate(ordered, 1):
        representative = items[0]
        meta = contents[representative["content_key"]]
        lines += [f'<a id="sha-{digest}"></a>',
                  f"### {index}. `{escape(Path(representative['path']).name)}` · {len(items)} 路径", "",
                  f"- SHA-256：`{digest}`。",
                  f"- 简介：{escape(representative['description']).rstrip('。.')}。",
                  f"- 功能：{functional_summary(meta, Path(representative['path']).suffix, Path(representative['path']).name)}。"]
        if digest in main_hashes:
            lines.append("- 当前主清单同内容文件：" + "、".join(source_link(path) for path in main_hashes[digest]) + "。")
        if meta["direct_mujoco"]:
            lines.append("- 历史内容含直接 MuJoCo import；不代表活动包仍使用该实现。")
        if meta["parse_error"]:
            lines.append("- AST 解析未完成；路径及内容哈希仍完整收录，错误见 JSON。")
        lines += ["", *[f"- {source_link(item['path'])}" for item in items], ""]
    (target / "script_snapshots_inventory_zh.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    generate(args.root.resolve())


if __name__ == "__main__":
    main()
