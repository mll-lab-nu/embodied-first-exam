# ALOHA 2 双臂资产

来源：[MuJoCo Menagerie / ALOHA](https://github.com/google-deepmind/mujoco_menagerie/tree/8161bba264d7fa7c99ca301e91e7fb44737676ad/aloha)，
固定 revision `8161bba264d7fa7c99ca301e91e7fb44737676ad`。
与用户提供的 [参考演示](https://qinengwang-aiden.github.io/demos/constraint_demos/methods.html)
声明的机器人版本相同。原始介绍保存在 [UPSTREAM_README.md](UPSTREAM_README.md)，
许可证见 [LICENSE](LICENSE)（Trossen Robotics，BSD-3-Clause）。

本目录包含未经修改的原始 MJCF、actuator/keyframe include 和全部 12 个网格。
[source.json](source.json) 记录逐文件 SHA-256，可离线复核，无运行时下载。
每臂 6 个转动关节和 2 个手指滑动关节；整机 16 DoF、14 个原生 actuator，
两对手指分别由 equality 约束联动。左右基座间距为 0.938 m。

`topogym.robot.assets.build_tabletop_aloha()` 在缓存中生成桌面适配 MJCF：

- 两个基座共同下移 20 mm，使安装面位于模型 z=0，再由共享 builder 放到桌面高度。
- 展开 include、使用绝对网格路径，移除原世界灯光和世界相机（由实验室统一提供）。
- 保留尺寸、连杆、惯量、关节限位、夹爪、腕部 D405 几何及 equality。
- 不加载上游 `scene.xml` 的桌子和铝型材架；复用 TopoGym 桌子及封闭实验室。

这不是两台 Panda 拼装，也没有替换为 Robotiq 夹爪。
Genesis 的碰撞网格近似、关节求解与 MuJoCo 不完全相同；导入成功不代表动力学等价或实机标定完成。
