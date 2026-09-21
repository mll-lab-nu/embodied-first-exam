"""Synchronized views of this run's physical state, with task-specific labels."""
import json

from topogym.tasks.knot_untying.recording import PhysicalRecorder, validate_recording

PHASE_LABELS = (
    "初始静置", "右手接近绳端", "右手抓取", "抬升绳端", "绳端对齐", "左手接近另一端", "左手抓取",
    "抬升左端", "双手抬绳", "接近第一环", "第一环前调姿", "向第一环穿入", "左端前送", "左端绕行",
    "继续绕行", "左手制动", "松开左端", "自由端静置", "左手撤离", "左手接近换抓点", "左手换抓",
    "准备右手释放", "微调左抓位置", "收紧左夹爪", "右手解除抓持", "左手稳住绳子", "右手撤离",
    "接近第二环", "抬高接近姿态", "绕行至第二环", "第二环前调姿", "向第二环穿入", "右手接近出口",
    "右手出口换抓", "左手松手", "左手退出第二环", "接近第三环", "向第三环穿入", "沿切向移动",
    "右夹爪转动", "左手接近转交点", "左手接取", "右手松手", "右手后撤", "右手继续后撤",
    "重新接近绳端", "再次抓取绳端", "拉过第三环出口", "左手松手", "将绳端放回桌面", "最后松手、撤离与静置")


def stage_label(stage):
    feedback = dict(pivot="左手固定抓持点微转", transit="右手接近重新观测的绳尾",
        approach="右手对准实测绳端", close="等待双指接触并辅助抓持", dual_hold="双手共同持绳确认",
        unpinch="右手接稳后左手小幅松指", withdraw="左手沿轴向退出第二环",
        return_left="左手回到后续起始位", carry="右手携绳端绕行至第三环前")
    feedback.update(first_unpinch="左手保持实测姿态、右手小幅松指", first_withdraw="右手立即退出第一环",
                    first_left_join="右手退开后左手调姿", first_right_join="右手回到第二环前待机位")
    if stage.startswith("feedback_"):
        return feedback.get(stage.removeprefix("feedback_"), stage)
    if stage == "final_settle":
        return "释放后自然静置"
    if stage.startswith("reference_"):
        try:
            return PHASE_LABELS[int(stage.split("_")[-1])]
        except (ValueError, IndexError):
            pass
    return stage


class ThreadingRecorder(PhysicalRecorder):
    def __init__(self, task, output, *, fps, dt, metadata):
        import numpy as np
        from scipy.spatial.transform import Rotation
        # The source worm's-eye pose crops the raised ring apertures. Rotate
        # only this optical frame, retaining its original mounting position.
        camera = task.cameras['cam_low']
        original = np.asarray(camera.transform).copy()
        tilt = np.eye(4)
        tilt[:3, :3] = Rotation.from_euler('x', 20., degrees=True).as_matrix()
        camera.set_pose(transform=original@tilt)
        metadata = dict(metadata, cam_low_pitch_offset_deg=20.,
            cam_low_recording_adjustment=dict(original_transform=original.tolist(),
                adjusted_transform=np.asarray(camera.transform).tolist(),
                reason='Keep all raised ring apertures inside the low camera view'))
        super().__init__(task, output, fps=fps, dt=dt, metadata=metadata)

    def capture(self, step, time_s, actions):
        count = len(self.frames)
        super().capture(step, time_s, actions)
        if len(self.frames) == count:
            return
        frame = self.frames[-1]
        stage = frame['stage']
        if (stage == getattr(self, '_preview_stage', None)
                and time_s-getattr(self, '_preview_time', -1e9) < 1.):
            return
        # Reuse this timestamp's cached camera images; no physical step occurs
        # between video capture and these inspectable progress snapshots.
        from PIL import Image
        images = {}
        for name, camera in self.task.cameras.items():
            destination = self.output/f'latest_{name}.png'
            temporary = destination.with_suffix('.tmp.png')
            Image.fromarray(camera.render(force_render=False)[0].copy()).save(temporary)
            temporary.replace(destination)
            images[name] = destination.name
        temporary = self.output/'latest_frame.tmp.json'
        temporary.write_text(json.dumps(dict(frame=frame['frame'], physics_time_s=time_s,
            stage=stage, images=images, source='same physical state and cached camera pass as the video'),
            indent=2)+'\n')
        temporary.replace(self.output/'latest_frame.json')
        self._preview_stage, self._preview_time = stage, time_s

    def close(self, report):
        self.stack.close()
        self.metadata.update(fps=self.fps, frames=len(self.frames), cameras=list(self.writers),
            same_continuous_rollout=True, steps_between_camera_captures=0,
            full_threading_verified=bool(report.get("full_threading_verified")),
            exploratory=bool(report.get("exploratory")),
            full_task_observed=bool(report.get("full_task_observed")),
            reference_speed=report.get("reference_speed"), physical_state_replay=False)
        (self.output/"camera_rig.json").write_text(json.dumps(self.metadata, indent=2)+"\n")
        (self.output/"frames.json").write_text(json.dumps(self.frames)+"\n")
        validation = validate_recording(self.output)
        status = "完整穿环执行通过" if report.get("full_threading_verified") else "局部物理试跑；尚未通过完整穿环验收"
        if report.get("exploratory"):
            status = ("全流程探索试跑：任务动作与最终构型检查通过；完整物理资格仍待复验"
                      if report.get("full_task_observed") else "全流程探索试跑：尚未完成任务；完整物理资格仍待复验")
        phases = [dict(video_time_s=i/self.fps, physics_time_s=frame["physics_time_s"],
                       stage=frame["stage"], label=stage_label(frame["stage"]))
                  for i, frame in enumerate(self.frames)
                  if i == 0 or frame["stage"] != self.frames[i-1]["stage"]]
        (self.output/"video_phases.json").write_text(json.dumps(phases, ensure_ascii=False, indent=2)+"\n")
        execution_spec = json.loads((self.output/'validation_spec.json').read_text())
        settling = execution_spec['actuation']['minimum_post_release_s']
        lines = ["# 绳穿三环 · 实际物理执行", "", status,
            f"实际模拟 {report.get('simulated_seconds', 0):.3f} s；视频核对：{'通过' if validation['passed'] else '未通过'}。", "",
            "机械臂执行位置控制；绳子由 FEM+IPC 重新模拟。双指实际接触后启用显式辅助抓持，"
            "约束跟随机械臂的实际位姿，松手后解除。五路视角来自同一次连续执行。", ""]
        lines += [f"- [{name}]({name}.mp4)" for name in self.writers]
        lines += ["", f"参考动作速度倍率 {report.get('reference_speed')}；视频按实际模拟时间播放。"
            f"动作序列结束后继续自然静置 {settling:g} s，按末两秒窗口验收。"]
        if report.get("exploratory"):
            lines += ["试跑原因："+report['exploratory_reason'],
                "物理指标按原门槛记录。试跑不计为已通过完整物理资格的正式演示。"]
        if report.get("mode") == "full_threading":
            lines += ["末段放回沿参考路径平滑抬高右手目标 3 cm，以适配共享桌面。"
                      "绳子释放后自然落桌；参考绳体状态没有写入本次模拟。"]
        limits = report.get("actuation", {}).get("release_operating_limits")
        if limits:
            lines += [f"完全松手时释放点距桌面不超过 {limits['max_unsupported_height_m']*1000:g} mm；"
                f"高处松手须有材料距离 {limits['max_supported_material_span_m']*1000:g} mm 内的另一抓持支撑。"
                "先前无阻尼版本约 33 cm 高处完全释放未通过时间步对照；本演示不覆盖该工况。"]
        material = self.task.backend.rope_cfg.fem
        lines += [f"杨氏模量 {float(material.E)/1000:g} kPa，泊松比 {float(material.nu):g}，"
            f"密度 {float(material.rho):g} kg/m³。材料参数未经实物标定。"]
        if report.get('table_contact'):
            lines += [f"共面解析绳桌接触对摩擦系数 {report['table_contact']['rope_table_pair_friction']:.4f}；"
                "原生子步检查绳子距有限桌面边缘至少 1 cm；机器人使用实体桌面碰撞。"]
        if report.get('deformation_damping'):
            lines += [f"形变耗散系数 {report['deformation_damping']['rate_s_inv']:g} s⁻¹，剔除整体平移和转动；"
                "原生子步核对耗散功率、合力与合力矩。耗散参数未经实物标定。"]
        if report.get('error'):
            lines += ["", "运行错误："+report['error']]
        lines += ["", "[物理报告](report.json) · [接触与抓持](contact_trace.json) · "
            "[逐帧时间](frames.json) · [阶段时间](video_phases.json) · [视频核对](video_validation.json)", ""]
        (self.output/"README.md").write_text("\n".join(lines))
