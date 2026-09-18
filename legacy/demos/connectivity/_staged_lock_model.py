"""Kinematic pitch model: three drive discs and a fixed upward endpoint slot.

There are no outer release gates or fence. Three equal-phase axial tabs drive
the discs they overlap. The goal is insertion into the fourth, fixed aperture.
Freely rotating discs admit monotone-depth solutions; backtracking is optional.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

VARIANT = "endpoint"
SLOTS = ((0., 90., 210.), (30., 150., 270.), (60., 180., 300.))
PITCH = .130
DISC_X = (0., PITCH, 2*PITCH)
DISC_R = .072
DISC_THICK = .012
BORE_R = .011
SLOT_R = .035
SLOT_HALF_DEG = 10.
TAB_R = .030
TAB_HALF_DEG = 4.
TAB_THICK = .005
TAB_PHASE_DEG = (0., 0., 0.)
AXIS_Z = 1.110
END_X = 3*PITCH
END_THICK = .022
END_DEG = 0.
END_DEPTH = 4.


def angular_error(a, b):
    return abs((a-b+180.) % 360.-180.)


@dataclass(frozen=True)
class Pose:
    depth: float = 0.
    key_deg: float = 60.
    disc_deg: tuple[float, float, float] = (60., 195., 80.)

    @property
    def tip_x(self):
        """Axial center of the leading tab; the round shaft projects beyond it."""
        return (self.depth-1)*PITCH


def slot_error(pose, disc, *, slots=SLOTS):
    return min(angular_error(pose.key_deg-pose.disc_deg[disc], s) for s in slots[disc])


def tab_sweeps_plane(pose, depth, x, thickness):
    half=(thickness+TAB_THICK)/2
    for j in range(3):
        a=pose.tip_x-j*PITCH
        b=(depth-1)*PITCH-j*PITCH
        if min(a,b)<x+half and max(a,b)>x-half:
            return True
    return False


def can_insert(pose, depth, *, slots=SLOTS):
    """Check every plate crossed by any tab, including on withdrawal."""
    if not 0 <= depth <= END_DEPTH:
        return False
    for i,x in enumerate(DISC_X):
        if tab_sweeps_plane(pose,depth,x,DISC_THICK) and slot_error(pose,i,slots=slots)+TAB_HALF_DEG >= SLOT_HALF_DEG:
            return False
    if tab_sweeps_plane(pose,depth,END_X,END_THICK):
        return angular_error(pose.key_deg,END_DEG)+TAB_HALF_DEG < SLOT_HALF_DEG
    return True


def active_discs(pose):
    return tuple(i for i,x in enumerate(DISC_X)
                 if tab_sweeps_plane(pose,pose.depth,x,DISC_THICK))


def active_tab(pose, disc):
    return next((j for j in range(3)
                 if abs(pose.tip_x-j*PITCH-DISC_X[disc])<(DISC_THICK+TAB_THICK)/2),None)


def geometry_errors(pose, *, slots=SLOTS):
    errors=[]
    if not 0 <= pose.depth <= END_DEPTH:
        errors.append("depth_outside_stroke")
    for i in active_discs(pose):
        if slot_error(pose,i,slots=slots)+TAB_HALF_DEG >= SLOT_HALF_DEG:
            errors.append(f"tab_vs_disc_{i+1}")
    if tab_sweeps_plane(pose,pose.depth,END_X,END_THICK):
        if angular_error(pose.key_deg,END_DEG)+TAB_HALF_DEG >= SLOT_HALF_DEG:
            errors.append("tab_vs_fixed_endpoint")
    return errors


def succeeded(pose, *, slots=SLOTS):
    # The leading fin must reach the middle of the fixed aperture. A bare
    # round shaft tip entering the bore early is insufficient.
    return pose.tip_x >= END_X-1e-9 and not geometry_errors(pose,slots=slots)


def transition(pose, kind, value, *, slots=SLOTS):
    if kind == "depth":
        if not can_insert(pose,value,slots=slots):
            raise ValueError("Insertion rejected: a crossed aperture does not fit the tab")
        result=type(pose)(value,pose.key_deg,pose.disc_deg)
    elif kind == "turn":
        if abs(round(pose.depth)-pose.depth)>1e-9:
            raise ValueError("This pitch controller rotates only at indexed depths")
        if tab_sweeps_plane(pose,pose.depth,END_X,END_THICK):
            # Check the whole turn, not merely equivalent endpoint angles:
            # a 360-degree turn would pass through the fixed socket walls.
            offset=(pose.key_deg-END_DEG+180)%360-180
            if max(abs(offset),abs(offset+value))+TAB_HALF_DEG >= SLOT_HALF_DEG:
                raise ValueError("Rotation rejected: the fixed endpoint constrains the key")
        active=active_discs(pose)
        result=type(pose)(pose.depth,pose.key_deg+value,
                    tuple(a+(value if i in active else 0) for i,a in enumerate(pose.disc_deg)))
    elif kind in ("hold","blocked"):
        if kind == "blocked" and can_insert(pose,value,slots=slots):
            raise ValueError("The proposed blocked example is actually passable")
        result=pose
    else:
        raise ValueError(kind)
    if geometry_errors(result,slots=slots):
        raise ValueError(geometry_errors(result,slots=slots))
    return result


@dataclass(frozen=True)
class Beat:
    kind: str
    value: float
    seconds: float
    title: str
    subtitle: str


BEATS=(
    Beat("hold",0,3.0,"三层锁片 → 固定终点孔","目标只有一个：让钥匙前端凸片进入最右侧、槽口朝上的固定孔。"),
    Beat("depth",1,2.0,"01  进入一级","D1 的槽口与前端凸片对齐；此时钥匙只带动第一片。"),
    Beat("blocked",2,1.8,"02  直接进入二级受阻","钥匙朝向 60°，与 D2 的任何一个入口都不相容。"),
    Beat("turn",45,3.0,"03  转动 D1，构造二级入口","钥匙转到 105°；D1 随动，尚未啮合的 D2、D3 保持角度。"),
    Beat("depth",2,2.0,"04  深入二级","两片凸片同时啮合 D1 + D2，驱动范围随深度改变。"),
    Beat("blocked",3,1.8,"05  三级入口尚未对齐","已有两级通道，但当前 105° 方向仍被 D3 挡住。"),
    Beat("turn",35,3.0,"06  两片联动，构造三级入口","共同转到 140°，使钥匙与 D3 的一个中心槽对齐。"),
    Beat("depth",3,2.0,"07  进入第三级","三片同时啮合。进入 D3 还没有到达固定终点。"),
    Beat("blocked",4,2.2,"08  终点只接受朝上方向","终点固定不转；钥匙当前朝向 140°，继续插入被拒绝。"),
    Beat("turn",-140,4.0,"09  三片共同旋转，钥匙朝上","保持三层通道的相容关系，把凸片转到终点要求的 0°。"),
    Beat("depth",4,3.0,"10  贯穿并插入固定终点","前端凸片进入终点孔；后两片沿 D2、D3 的已对齐槽继续通过。"),
    Beat("hold",0,3.2,"INSERTED  ·  到达固定终点","前端凸片到达终点。三片角度可不同，只需各自有槽与钥匙对齐。"),
)


def build_timeline(pose, beats, advance, check, fps):
    result=[]
    for index,beat in enumerate(beats):
        target=advance(pose,beat.kind,beat.value)
        for j in range(max(1,round(beat.seconds*fps))):
            u=(j+1)/max(1,round(beat.seconds*fps))
            u=u*u*(3-2*u)
            p=type(pose)(pose.depth+(target.depth-pose.depth)*u,
                   pose.key_deg+(target.key_deg-pose.key_deg)*u,
                   tuple(a+(b-a)*u for a,b in zip(pose.disc_deg,target.disc_deg)))
            errors=check(p)
            if errors:
                raise ValueError((index,j,errors,asdict(p)))
            result.append((index,p))
        pose=target
    return result


def timeline(fps=20):
    return build_timeline(Pose(),BEATS,transition,geometry_errors,fps)
