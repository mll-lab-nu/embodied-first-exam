"""Staggered tabs make one depth-two state require shallow reconfiguration.

The proof is conditional on entering D2 through the illustrated slot. It also
allows arbitrary free key rotation in axial gaps: D1/D2's next-tab acceptance
windows are disjoint until their relative disc angle is changed.
This remains a slot-driven kinematic model, not a contact-dynamics result.
"""
from dataclasses import dataclass

from demos.connectivity import _staged_lock_model as base
from demos.connectivity._staged_lock_model import (
    AXIS_Z, BORE_R, DISC_R, DISC_THICK, DISC_X, END_DEG, END_DEPTH, END_THICK,
    END_X, PITCH, SLOT_HALF_DEG, SLOT_R, TAB_HALF_DEG, TAB_R, TAB_THICK,
    Beat, active_discs, active_tab, angular_error,
)

VARIANT = "backtrack"
TAB_PHASE_DEG = (0., 60., 150.)  # front, middle, rear
SLOTS = ((0., 60., 150.), (0., 90., 150., 240.), (0., 60., 220.))


@dataclass(frozen=True)
class Pose(base.Pose):
    key_deg: float = 0.
    disc_deg: tuple[float, float, float] = (0., 0., 120.)


def tab_sweeps_plane(pose, depth, x, thickness, tab=None):
    tabs=range(3) if tab is None else (tab,)
    for j in tabs:
        a=pose.tip_x-j*PITCH
        b=(depth-1)*PITCH-j*PITCH
        half=(thickness+TAB_THICK)/2
        if min(a,b)<x+half and max(a,b)>x-half:
            return True
    return False


def slot_error(pose, disc, tab):
    return min(angular_error(pose.key_deg+TAB_PHASE_DEG[tab]-pose.disc_deg[disc],s)
               for s in SLOTS[disc])


def path_errors(pose, depth):
    errors=[]
    if not 0 <= depth <= END_DEPTH:
        errors.append("depth_outside_stroke")
    for j,phase in enumerate(TAB_PHASE_DEG):
        for i,x in enumerate(DISC_X):
            if tab_sweeps_plane(pose,depth,x,DISC_THICK,j):
                if slot_error(pose,i,j)+TAB_HALF_DEG >= SLOT_HALF_DEG:
                    errors.append(f"tab_{j}_vs_disc_{i+1}")
        if tab_sweeps_plane(pose,depth,END_X,END_THICK,j):
            if angular_error(pose.key_deg+phase,END_DEG)+TAB_HALF_DEG >= SLOT_HALF_DEG:
                errors.append(f"tab_{j}_vs_fixed_endpoint")
    return errors


def can_insert(pose, depth):
    return not path_errors(pose,depth)


def geometry_errors(pose):
    return path_errors(pose,pose.depth)


def succeeded(pose):
    return pose.tip_x >= END_X-1e-9 and not geometry_errors(pose)


def transition(pose, kind, value):
    if kind == "depth":
        errors=path_errors(pose,value)
        if errors:
            raise ValueError(errors)
        result=Pose(value,pose.key_deg,pose.disc_deg)
    elif kind == "turn":
        active=active_discs(pose)
        if geometry_errors(pose):
            raise ValueError("Cannot rotate from an invalid engagement")
        for j,phase in enumerate(TAB_PHASE_DEG):
            if tab_sweeps_plane(pose,pose.depth,END_X,END_THICK,j):
                offset=(pose.key_deg+phase-END_DEG+180)%360-180
                if max(abs(offset),abs(offset+value))+TAB_HALF_DEG >= SLOT_HALF_DEG:
                    raise ValueError("The fixed endpoint blocks the rotation")
        # Unlike the first presentation controller, rotation in axial gaps is
        # explicitly allowed. The trap proof must survive this extra freedom.
        result=Pose(pose.depth,pose.key_deg+value,
                    tuple(a+(value if i in active else 0) for i,a in enumerate(pose.disc_deg)))
    elif kind in ("hold","blocked"):
        if kind=="blocked" and can_insert(pose,value):
            raise ValueError("The proposed blocked request is actually passable")
        result=pose
    else:
        raise ValueError(kind)
    if geometry_errors(result):
        raise ValueError(geometry_errors(result))
    return result


def third_level_windows(pose):
    """Key angles that fit the rear tab in D1 and the middle tab in D2.

    Windows each have half-width SLOT_HALF_DEG - TAB_HALF_DEG (6 degrees).
    Their minimum center separation exceeding 12 degrees rules out every
    key azimuth, even while the key is free between discs.
    """
    first=[(pose.disc_deg[0]+s-TAB_PHASE_DEG[2])%360 for s in SLOTS[0]]
    second=[(pose.disc_deg[1]+s-TAB_PHASE_DEG[1])%360 for s in SLOTS[1]]
    separation=min(angular_error(a,b) for a in first for b in second)
    return dict(d1_rear_tab_centers=first,d2_middle_tab_centers=second,
                min_center_separation_deg=separation,
                combined_half_width_deg=2*(SLOT_HALF_DEG-TAB_HALF_DEG),
                overlap_possible=separation<2*(SLOT_HALF_DEG-TAB_HALF_DEG))


BEATS=(
    Beat("hold",0,3.0,"错相凸片 · 必须浅退的二层状态","前、中、后三片凸片朝向为 0° / 60° / 150°；终点孔仍固定朝上。"),
    Beat("depth",1,2.0,"01  进入一级","前端凸片进入 D1；下一次深入会换成中间凸片经过同一锁片。"),
    Beat("depth",2,2.0,"02  进入二级的当前入口","中间凸片啮合 D1，前端凸片啮合 D2。此时尚未形成三级通道。"),
    Beat("turn",30,2.5,"03  同时转动两片","D1、D2 一起转到 30°；它们的相对角度仍然没有改变。"),
    Beat("blocked",3,3.0,"04  继续旋转双盘也无法深入","下一步需后凸片过 D1、中凸片过 D2；当前没有共同通行方向。"),
    Beat("depth",1,2.2,"05  退回第一层，解除双盘耦合","D2 保留在 30°；钥匙重新只啮合 D1，获得单独修正前级的自由度。"),
    Beat("turn",90,3.5,"06  只转 D1 与钥匙 90°","D1 → 120°，D2 保持 30°。两片相对角度改变，下一组凸片可以通过。"),
    Beat("depth",3,4.5,"07  一次推进，直接进入第三层","沿 D2 的另一组槽通过；从一级连续插到三级，中途无需再旋转。"),
    Beat("blocked",4,2.0,"08  固定终点要求钥匙朝上","三层已经贯通；终点孔固定，当前 120° 朝向仍不可进入。"),
    Beat("turn",-120,4.0,"09  三片联动，把前端凸片朝上","共同旋转到钥匙 0°，保持已经构造的各层通行关系。"),
    Beat("depth",4,3.0,"10  插入固定终点","前凸片进入 END，中、后凸片分别通过 D3、D2 的对应槽。"),
    Beat("hold",0,3.3,"INSERTED  ·  浅退修正后贯穿","从这个二层状态出发必须解耦修正；事先选对入口则可能避开回退。"),
)


def timeline(fps=20):
    return base.build_timeline(Pose(),BEATS,transition,geometry_errors,fps)
