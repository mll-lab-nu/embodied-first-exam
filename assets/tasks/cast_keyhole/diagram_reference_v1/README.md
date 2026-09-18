# Cast Keyhole 结构重建模板

基线为 Hanayama Huzzle Cast Keyhole（HZ 4-11 / 515061，Vesa Timonen，4 / 6）。
厂家拆件照片和两页 16 步解法的链接、用途、假设见 [sources.json](sources.json)。
官方解法是实物可解的依据，不是本地模型的可解性证书。

[template.json](template.json) 中所有长度单位为 mm。26 × 69 mm 包络、3 mm 板厚、
6600 kg/m³ 密度均为明确的工程假设，不是厂家尺寸。轮廓按厂家正面照片比例重建，
保留金件开口叉及错列齿、银件封闭阶梯孔和独立底部外凹口。圆弧用 24 段折线离散，
尚未添加真实倒角、铸造拔模或表面文字。

默认初态 `perpendicular_lower_bore_v1` 为下部孔道穿插的候选工程位姿，
不是原厂出盒姿态，也未核实其在官方路径上的具体对应步骤。
模板原点在银件轮廓的参考中心；x/z 为银件面，y 为厚度方向。
金件绕 z 转 90°，沿 z 下移 47 mm。场景整体旋转后，长轴沿桌面、两件各倾斜 45°。

生成器以水平切片把两件分为 62 / 67 个不重叠凸棱柱，视觉外表面和碰撞使用同一实体。
URDF 每件只有一个自由 link；质量和惯量由实体积分产生。Genesis 加载后再核对凸块数量、
包络及体积，避免孔道在预处理时被改变。生成的 GLB、OBJ 和 URDF 位于运行目录，不提交缓存资产。

运行入口、实际结果和后续验证见 [任务说明](../../../../docs/develop/tasks/cast_keyhole_zh.md)。
## 路线候选

`route_candidates.json` 另外记录规范 XY 轮廓坐标中的顶部穿插初态、四分之一圈转动、
到第一槽的候选路点。长度单位 mm，旋转注明为 `Rz(yaw) @ Rx(-pi/2)`；检查时统一放大 3 倍。
它不是 bootstrap 的 `perpendicular_lower_bore_v1` 初态，也不是完整官方轨迹。
`python -m topogym.tasks.cast_keyhole.route_probe --output <目录>` 检查连续间隙并生成三投影诊断图。
后续换槽、两次翻转、退出以及机器人抓持尚未通过验收。
