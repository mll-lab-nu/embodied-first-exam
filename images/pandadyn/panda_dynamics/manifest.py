"""The sole authoritative public benchmark: exactly 12 single + 13 dual tasks.

Presence here is a design/registration fact, never a feasibility claim.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskSpec:
    code: str
    name: str
    title: str
    module: str
    mechanism: str
    priority: str = "standard"

    @property
    def key(self):
        return self.code + "-" + self.name

    @property
    def env_id(self):
        return f"PandaMultiStage/{self.key}-v0"

    @property
    def arms(self):
        return 1 if self.code.startswith("S") else 2


BENCHMARK = (
    TaskSpec(
        "S01",
        "CupRouteDelivery",
        "杯接轨道接力交付",
        "single.cup_route_delivery",
        "接取与重力轨道",
        "representative",
    ),
    TaskSpec(
        "S02",
        "PlateCatchTransportRelease",
        "平板接取运输卸载",
        "single.plate_catch_transport_release",
        "无边平板与滚动",
    ),
    TaskSpec(
        "S03",
        "ClearGateHockey",
        "击球清障再射门",
        "single.clear_gate_hockey",
        "碰撞与路线切换",
        "representative",
    ),
    TaskSpec(
        "S04",
        "ImpactReleaseRelay",
        "撞击解锁截获接力",
        "single.impact_release_relay",
        "机械闩锁与动量",
    ),
    TaskSpec(
        "S05",
        "SlidingReceiveAlignDeliver",
        "滑块承接定位交付",
        "single.sliding_receive_align_deliver",
        "惯性滑移与支撑转移",
        "representative",
    ),
    TaskSpec(
        "S06",
        "CubeFlipRouteRecover",
        "方块翻转轨道回收",
        "single.cube_flip_route_recover",
        "惯性翻转与滑道",
        "advanced",
    ),
    TaskSpec(
        "S07",
        "ConveyorLoadBrakeUnload",
        "传送抓取装载制动卸载",
        "single.conveyor_load_brake_unload",
        "物理抓取与车体制动",
    ),
    TaskSpec(
        "S08",
        "LoadSwitchRecover",
        "装载道岔切换回收",
        "single.load_switch_recover",
        "物理抓取与路线切换",
    ),
    TaskSpec(
        "S09",
        "TossRecatchDelivery",
        "接球抛起再接交付",
        "single.toss_recatch_delivery",
        "连续自由飞行",
        "advanced",
    ),
    TaskSpec(
        "S10",
        "SwingingLoadTransitDock",
        "摆动载荷运输入坞",
        "single.swinging_load_transit_dock",
        "被动摆动与抓取",
    ),
    TaskSpec(
        "S11",
        "CylinderRescueRouteDeliver",
        "滚柱截获导向交付",
        "single.cylinder_rescue_route_deliver",
        "柱体滚动与导轨",
        "advanced",
    ),
    TaskSpec(
        "S12",
        "MovingBridgePuckRelay",
        "运动桥接力限时射门",
        "single.moving_bridge_puck_relay",
        "运动机构与击打",
    ),
    TaskSpec(
        "D01",
        "ReciprocalCupRelay",
        "双杯往返空中接力",
        "dual.reciprocal_cup_relay",
        "连续自由飞行",
        "representative",
    ),
    TaskSpec(
        "D02",
        "StrikeCatchMerge",
        "击打接取双球汇合",
        "dual.strike_catch_merge",
        "击打与连续接取",
    ),
    TaskSpec(
        "D03",
        "CooperativePuckCourse",
        "双臂冰球多路线接力",
        "dual.cooperative_puck_course",
        "碰撞与路线切换",
    ),
    TaskSpec(
        "D04",
        "SharedTrayTransportDischarge",
        "共同托盘运输排球",
        "dual.shared_tray_transport_discharge",
        "共同承载与滚动",
        "representative",
    ),
    TaskSpec(
        "D05",
        "MovingRampRelay",
        "移动斜槽双路线接力",
        "dual.moving_ramp_relay",
        "接取与重力轨道",
    ),
    TaskSpec(
        "D06",
        "MovingBankRelay",
        "移动反弹板路线接力",
        "dual.moving_bank_relay",
        "运动反弹边界",
    ),
    TaskSpec(
        "D07",
        "SpringGateSwitchyard",
        "弹簧门协作调度",
        "dual.spring_gate_switchyard",
        "机械门与路线切换",
    ),
    TaskSpec(
        "D08",
        "PendulumEnergyRelay",
        "摆锤能量往返接力",
        "dual.pendulum_energy_relay",
        "被动摆动与动量",
    ),
    TaskSpec(
        "D09",
        "LeverLaunchCatchReload",
        "杠杆发射接取再装填",
        "dual.lever_launch_catch_reload",
        "被动发射机构",
    ),
    TaskSpec(
        "D10",
        "MovingGraspHandover",
        "运动抓取交接入槽",
        "dual.moving_grasp_handover",
        "双手物理抓握",
        "representative",
    ),
    TaskSpec(
        "D11",
        "MovingFixtureUnlock",
        "运动夹具插销解锁",
        "dual.moving_fixture_unlock",
        "相对插入与实体闩锁",
        "advanced",
    ),
    TaskSpec(
        "D12",
        "ReciprocalSlidingTransfer",
        "双托盘往返滑移",
        "dual.reciprocal_sliding_transfer",
        "惯性滑移与支撑转移",
    ),
    TaskSpec(
        "D13",
        "SupportedCubeFlipRelay",
        "移动支撑连续方块翻转",
        "dual.supported_cube_flip_relay",
        "惯性翻转与共同操作",
        "advanced",
    ),
)


def task_spec(value):
    for task in BENCHMARK:
        if value in (task.code, task.name, task.key, task.env_id):
            return task
    raise ValueError(
        f"Unknown canonical task {value!r}."
    )


def ensure_registered(value):
    from importlib import import_module
    from mani_skill.utils.registration import REGISTERED_ENVS, register_env

    spec = task_spec(value)
    if spec.env_id not in REGISTERED_ENVS:
        module = import_module("panda_dynamics.tasks." + spec.module)
        register_env(spec.env_id, max_episode_steps=4500)(getattr(module, spec.name))
    return spec
