"""Original same-direction key and retreat storyboard, with a fixed endpoint.

Derived from runs/staged_lock_nyx_pitch/source_v1: retain the original initial
state, D1/D2 slots and first ten actions. Move D3's 60-degree slot to 0 degrees
so the shallow correction can be followed by a single stroke into D3.
Retreat is a demonstrated legal route, not a mandatory success condition.
"""
from dataclasses import dataclass
from functools import partial

from demos.connectivity import _staged_lock_model as base
from demos.connectivity._staged_lock_model import (
    AXIS_Z, BORE_R, DISC_R, DISC_THICK, DISC_X, END_DEG, END_DEPTH, END_THICK,
    END_X, PITCH, SLOT_HALF_DEG, SLOT_R, TAB_HALF_DEG, TAB_PHASE_DEG, TAB_R,
    TAB_THICK, Beat, active_discs, active_tab, angular_error, tab_sweeps_plane,
)

VARIANT = "classic_endpoint"
SLOTS = (base.SLOTS[0],base.SLOTS[1],(0.,180.,300.))


@dataclass(frozen=True)
class Pose(base.Pose):
    disc_deg: tuple[float, float, float] = (60.,210.,60.)


slot_error=partial(base.slot_error,slots=SLOTS)
can_insert=partial(base.can_insert,slots=SLOTS)
geometry_errors=partial(base.geometry_errors,slots=SLOTS)
succeeded=partial(base.succeeded,slots=SLOTS)
transition=partial(base.transition,slots=SLOTS)

BEATS=(
    Beat("hold",0,3.0,"同向凸片 · 换槽、回退与贯穿","三个凸片始终朝同一方向；目标是让前端凸片进入后方固定朝上的锁孔。"),
    Beat("depth",1,2.1,"01  插入一级","前端凸片进入 D1，D2、D3 保持原位。"),
    Beat("turn",90,2.5,"02  单独旋转 D1","沿用原版动作：D1 从 60° 转到 150°。"),
    Beat("blocked",2,2.3,"03  当前方向不能进入二级","D1 已转动，但当前钥匙方向还没有对准 D2 的入口。"),
    Beat("depth",0,1.8,"04  完全退出，保留锁片角度","D1 保持 150°；钥匙退出后可以改换入口。"),
    Beat("turn",90,2.2,"05  只转钥匙，改用另一条槽","三个凸片一起转到 240°，锁片保持原位。"),
    Beat("depth",2,3.0,"06  沿新槽进入二级","两片凸片分别啮合 D1、D2；深度决定驱动范围。"),
    Beat("turn",60,2.5,"07  同时带动 D1 + D2","钥匙转到 300°，D1、D2 同步转动，D3 保持 60°。"),
    Beat("blocked",3,2.3,"08  当前方向不能进入三级","这条演示路线选择保留 D2 的角度，退回一级换槽。"),
    Beat("depth",1,1.8,"09  退回一级","解除对 D2 的驱动；D2 = 270°，D3 = 60° 保持不变。"),
    Beat("turn",120,2.8,"10  单独修正 D1 与钥匙","只转 D1，让钥匙到 60°；三个凸片仍保持同向。"),
    Beat("depth",3,3.5,"11  一次从一级推进到三级","此时三层都有相容入口，沿固定方向连续插入，中途不再旋转。"),
    Beat("blocked",4,2.0,"12  固定终点要求朝上","前端凸片当前朝向 60°；后方固定锁孔只接受朝上的方向。"),
    Beat("turn",-60,3.0,"13  三片联动，使钥匙朝上","保持已有通道的相容关系，把三个凸片共同转到 0°。"),
    Beat("depth",4,3.0,"14  贯穿并插入后方固定孔","前端凸片进入 END；后两片沿已对齐的中心槽继续通过。"),
    Beat("hold",0,3.2,"INSERTED  ·  同向钥匙到达终点","钥匙保持插入状态；圆盘只有中心驱动槽，目标由固定终点孔决定。"),
)


def timeline(fps=20):
    return base.build_timeline(Pose(),BEATS,transition,geometry_errors,fps)
