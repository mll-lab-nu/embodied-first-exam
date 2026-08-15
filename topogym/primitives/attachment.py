from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from .physical_contact import entity_quat, quat_mul


def _quat_conj(q) -> np.ndarray:
    w, x, y, z = np.asarray(q, dtype=float)
    return np.array([w, -x, -y, -z], dtype=float)


def _quat_rotate(q, v) -> np.ndarray:
    """Rotate vector ``v`` by the (w, x, y, z) quaternion ``q``."""

    w, x, y, z = np.asarray(q, dtype=float)
    u = np.array([x, y, z], dtype=float)
    v = np.asarray(v, dtype=float)
    return v + 2.0 * np.cross(u, np.cross(u, v) + w * v)


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _xyz(value) -> np.ndarray:
    return _as_numpy(value).reshape(-1, 3)[0]


def yaw_quat(yaw: float) -> tuple[float, float, float, float]:
    half = 0.5 * float(yaw)
    return (float(np.cos(half)), 0.0, 0.0, float(np.sin(half)))


def rotate_z(offset, yaw: float) -> np.ndarray:
    offset = np.asarray(offset, dtype=float)
    c = float(np.cos(float(yaw)))
    s = float(np.sin(float(yaw)))
    return np.array(
        [
            c * offset[0] - s * offset[1],
            s * offset[0] + c * offset[1],
            offset[2],
        ],
        dtype=float,
    )


def parent_pos_for_child(child_pos, offset, yaw: float) -> np.ndarray:
    return np.asarray(child_pos, dtype=float) - rotate_z(offset, yaw)


def slerp(a, b, t: float) -> np.ndarray:
    """Shortest-arc interpolation between two (w, x, y, z) quaternions."""

    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    dot = float(np.dot(a, b))
    if dot < 0.0:
        # q and -q are the same orientation; pick the sign that turns the short way.
        b = -b
        dot = -dot
    if dot > 0.9995:
        result = a + float(t) * (b - a)
        return result / np.linalg.norm(result)
    theta = np.arccos(np.clip(dot, -1.0, 1.0))
    sin_theta = np.sin(theta)
    return (
        np.sin((1.0 - float(t)) * theta) / sin_theta * a + np.sin(float(t) * theta) / sin_theta * b
    )


@dataclass
class RigidAttachment:
    """Runtime state for a kinematic object attached to a moving parent.

    ``offset`` is the child origin in the parent's planar-yaw frame. For a
    Franka grasp demo this means: object_center = actual_hand_pos + Rz(yaw) *
    offset.
    """

    entity: Any
    parent_pos_fn: Callable[[], Any]
    offset: np.ndarray
    yaw: float = 0.0
    child_yaw_offset: float = 0.0
    # Hold this exact orientation instead of the yaw-only one.
    #
    # The yaw-only default assumes an upright child, which every rigid task here
    # has (blocks, plates, plugs standing in their sockets). It is not merely a
    # simplification for a child that is *not* upright: `sync` would force the
    # entity to a pitch-free, roll-free pose on the first synced step, snapping it
    # there in one frame. untangle_continuous grasps a plug that lies flat
    # (`euler=(0,-90,0)`), and that snap wrenched the rope particles welded to the
    # link through 90 degrees in a single step -- straight into the position-write
    # velocity amplification that PBD turns into a solver blow-up.
    quat: tuple[float, float, float, float] | None = None
    # Follow the parent's ORIENTATION too, not just its position.
    #
    # Without this the child holds whichever world orientation it had at
    # `attach()` while the parent turns underneath it -- which for a grasp means
    # the finger pads rotate around the held object. rope_winding rolls its wrist
    # +-135 degrees to track the orbit and throws it back twice a turn, and until
    # 2026-08-15 the plug sat through all of it: the pads swept the whole schedule
    # across a plug that never moved, and the rope's end band (welded to the
    # plug's link) was clamped in world orientation while the rope was wound twice
    # around a post.
    #
    # Given this, the child's pose relative to the parent is captured once at
    # `attach()` and restored every sync, so "the grasp is rigid" stops being a
    # property of the waypoint schedule and becomes one no code path can break.
    # Read the parent's ACTUAL pose rather than the commanded one, so IK tracking
    # error moves the pair together instead of shearing it.
    #
    # `ramp_to` still works under this: it turns the RELATIVE pose, so the child
    # can be re-oriented in the gripper's own frame (rope_winding pitches the plug
    # nose-down at the grasp) and then goes on following the hand rigidly.
    #
    # None keeps the position-only behaviour every other task was written
    # against.
    parent_quat_fn: Callable[[], Any] | None = None
    active: bool = False
    # Set by `ramp_to`: where `quat` is heading, and how many `sync` calls it has
    # left to get there. Untouched, these stay None/0 and `sync` is bit-for-bit
    # what it was.
    _ramp_from: np.ndarray | None = field(default=None, init=False, repr=False)
    _ramp_to: np.ndarray | None = field(default=None, init=False, repr=False)
    _ramp_step: int = field(default=0, init=False, repr=False)
    _ramp_steps: int = field(default=0, init=False, repr=False)
    # Child pose in the parent's frame, captured at `attach()`. Only used when
    # `parent_quat_fn` is set.
    _rel_quat: np.ndarray | None = field(default=None, init=False, repr=False)
    _rel_offset: np.ndarray | None = field(default=None, init=False, repr=False)

    def attach(self, *, yaw: float | None = None) -> None:
        if yaw is not None:
            self.yaw = float(yaw)
        if self.parent_quat_fn is not None:
            # Capture BEFORE the first sync, so what gets restored is where the
            # child actually is. Nothing moves on this call.
            parent_quat = np.asarray(self.parent_quat_fn(), dtype=float).reshape(4)
            inverse = _quat_conj(parent_quat)
            self._rel_quat = quat_mul(inverse, entity_quat(self.entity))
            self._rel_offset = _quat_rotate(
                inverse, _xyz(self.entity.get_pos()) - _xyz(self.parent_pos_fn())
            )
        self.active = True
        self.sync()

    def set_yaw(self, yaw: float) -> None:
        self.yaw = float(yaw)

    def ramp_to(self, quat, steps: int) -> None:
        """Turn the held child to ``quat`` gradually, over ``steps`` sync calls.

        Not `set_quat`-and-done, because the child's pose is not the child's
        alone: untangle_continuous welds rope particles to the held plug's link,
        so whatever this class writes, the rope is dragged through. Rewriting the
        orientation in one step wrenched those particles ~12 mm in a single 10 ms
        frame, and PBD reconstructs velocity as `(pos - ipos)/dt`, which turned
        that into the blow-up this ramp exists to avoid.

        ``steps`` counts **sync calls**, not simulation steps: `AttachmentManager`
        syncs both before and after `scene.step`, so a ramp meant to finish over N
        physics steps needs 2N here.
        """

        steps = max(1, int(steps))
        if self.parent_quat_fn is not None:
            # Following the parent, so what ramps is the pose RELATIVE to it.
            # `quat` is still a world target -- callers think in world axes -- so
            # it is converted here, once, against the parent's pose now. That is
            # exact while the parent is still, which is when this is used (the
            # plug is turned at the grasp, before the hand travels), and it means
            # the child keeps following the parent all the way through the turn
            # instead of being pinned to a world orientation for the duration.
            parent_quat = np.asarray(self.parent_quat_fn(), dtype=float).reshape(4)
            self._ramp_from = np.asarray(self._rel_quat, dtype=float)
            self._ramp_to = quat_mul(_quat_conj(parent_quat), np.asarray(quat, dtype=float))
            self._ramp_step = 0
            self._ramp_steps = steps
            return
        current = (
            np.asarray(self.quat, dtype=float)
            if self.quat is not None
            else np.asarray(yaw_quat(self.yaw + self.child_yaw_offset), dtype=float)
        )
        self._ramp_from = current
        self._ramp_to = np.asarray(quat, dtype=float)
        self._ramp_step = 0
        self._ramp_steps = steps

    def ramping(self) -> bool:
        return self._ramp_to is not None

    def sync(self) -> None:
        if not self.active:
            return
        if self.parent_quat_fn is not None:
            self._advance_ramp(relative=True)
            parent_quat = np.asarray(self.parent_quat_fn(), dtype=float).reshape(4)
            child_pos = _xyz(self.parent_pos_fn()) + _quat_rotate(
                parent_quat, self._rel_offset
            )
            child_quat = quat_mul(parent_quat, self._rel_quat)
            self.entity.set_pos(tuple(child_pos), zero_velocity=True)
            self.entity.set_quat(
                tuple(float(v) for v in child_quat), zero_velocity=True, relative=False
            )
            return
        self._advance_ramp()
        parent_pos = _xyz(self.parent_pos_fn())
        child_pos = parent_pos + rotate_z(self.offset, self.yaw)
        self.entity.set_pos(tuple(child_pos), zero_velocity=True)
        quat = (
            tuple(float(v) for v in self.quat)
            if self.quat is not None
            else yaw_quat(self.yaw + self.child_yaw_offset)
        )
        self.entity.set_quat(quat, zero_velocity=True, relative=False)

    def _advance_ramp(self, *, relative: bool = False) -> None:
        if self._ramp_to is None:
            return
        self._ramp_step += 1
        if self._ramp_step >= self._ramp_steps:
            reached = np.asarray(self._ramp_to, dtype=float)
            if relative:
                self._rel_quat = reached
            else:
                self.quat = tuple(float(v) for v in reached)
            self._ramp_from = None
            self._ramp_to = None
            self._ramp_step = 0
            self._ramp_steps = 0
            return
        fraction = self._ramp_step / self._ramp_steps
        turned = slerp(self._ramp_from, self._ramp_to, fraction)
        if relative:
            self._rel_quat = turned
        else:
            self.quat = tuple(float(v) for v in turned)

    def release(self, *, sync: bool = True) -> None:
        if sync:
            self.sync()
        self.active = False


class ParticleAttachment:
    """Weld an arbitrary band of PBD particles to a moving parent (assisted grasp).

    The PBD counterpart of ``RigidAttachment``: instead of driving a rigid body's
    pose, it drives a chosen set of particles. Which particles is the caller's
    business -- rope endpoints, a mid-rope band, a cloth corner -- so this class
    only takes indices.

    Two properties make it usable as a stand-in for a real grasp:

    - **Shape preserving.** Each particle's offset from the band centroid is
      captured at attach time and held, so the grasped stretch keeps its shape
      instead of collapsing to a point.
    - **No teleport on attach.** The band is welded where the material actually
      is, not where the parent is. The discrepancy at attach time is kept as a
      constant offset and carried, so the band follows the parent's *motion*
      from wherever it started. Without this, the first sync jumps the band by
      the whole attach error -- and PBD reconstructs velocity from position
      change, so a 13 mm jump in one 10 ms step becomes 1.3 m/s handed to a few
      particles whose neighbours are at rest, which is enough to blow up a stiff
      rope.
    """

    def __init__(
        self,
        entity: Any,
        indices,
        parent_pos_fn: Callable[[], Any],
        *,
        offset=(0.0, 0.0, 0.0),
        zero_velocity: bool = True,
        weights=None,
    ) -> None:
        self.entity = entity
        self.indices = np.asarray(indices, dtype=int)
        if self.indices.size == 0:
            raise ValueError("ParticleAttachment needs at least one particle index.")
        self.parent_pos_fn = parent_pos_fn
        self.offset = np.asarray(offset, dtype=float)
        self.zero_velocity = bool(zero_velocity)
        # Per-particle grip strength in [0, 1]. None means every held particle is
        # driven absolutely, which makes the band a rigid splint: the material
        # inside it cannot bend or even rotate, so all the deformation the motion
        # demands piles up at the two edges. Measured on a 4 mm-radius rope, that
        # pins the bend radius at 6-9 mm -- i.e. the rope is kinked to roughly its
        # own thickness, which no real cable does, and which drives Genesis'
        # rest-distance self-collision rule into firing inside the rope itself.
        # Tapering the grip to zero at the band edges removes the discontinuity.
        self.weights = (
            None if weights is None else np.clip(np.asarray(weights, dtype=float), 0.0, 1.0)
        )
        if self.weights is not None and self.weights.shape != self.indices.shape:
            raise ValueError(
                f"weights {self.weights.shape} must match indices {self.indices.shape}."
            )
        self.particle_offsets: np.ndarray | None = None
        self.anchor_offset = np.zeros(3, dtype=float)
        self.active = False

    def particles(self) -> np.ndarray:
        positions = _as_numpy(self.entity.get_particles_pos())
        if positions.ndim == 3:
            positions = positions[0]
        return np.asarray(positions[self.indices], dtype=float)

    def center(self) -> np.ndarray:
        """Current centroid of the band."""

        return self.particles().mean(axis=0)

    def attach(self) -> None:
        center = self.center()
        self.particle_offsets = self.particles() - center
        parent_center = np.asarray(_xyz(self.parent_pos_fn()), dtype=float) + self.offset
        self.anchor_offset = center - parent_center
        self.active = True
        self.sync()

    def drive_to(self, center) -> None:
        """Place the band so its centroid sits at ``center`` (parent-independent)."""

        if not self.active or self.particle_offsets is None:
            return
        center = np.asarray(_xyz(center), dtype=float)
        target = center[None, :] + self.particle_offsets
        if self.weights is None:
            positions = target
            velocities = np.zeros_like(target)
        else:
            # Blend toward where physics actually put each particle, by how firmly
            # it is gripped. A partially-gripped particle is written *closer* to
            # its solved position than a fully-gripped one, so tapering only ever
            # makes the position write gentler -- it cannot introduce the jump
            # that a hard write can.
            current = self._particles_at(self.indices)
            w = self.weights[:, None]
            positions = w * target + (1.0 - w) * current
            velocities = (1.0 - w) * self._velocities_at(self.indices)
        self.entity.set_particles_pos(positions, particles_idx_local=self.indices)
        if self.zero_velocity:
            # Without this the welded band keeps whatever velocity it had before
            # the weld and fights the kinematic drive when it is released. Under a
            # taper the edge particles keep theirs, which is the point: they are
            # only half-held and should still swing.
            self.entity.set_particles_vel(
                velocities, particles_idx_local=self.indices
            )

    def _particles_at(self, indices) -> np.ndarray:
        positions = _as_numpy(self.entity.get_particles_pos())
        if positions.ndim == 3:
            positions = positions[0]
        return np.asarray(positions[indices], dtype=float)

    def _velocities_at(self, indices) -> np.ndarray:
        velocities = _as_numpy(self.entity.get_particles_vel())
        if velocities.ndim == 3:
            velocities = velocities[0]
        return np.asarray(velocities[indices], dtype=float)

    def sync(self) -> None:
        if not self.active:
            return
        parent_center = np.asarray(_xyz(self.parent_pos_fn()), dtype=float) + self.offset
        self.drive_to(parent_center + self.anchor_offset)

    def release(self, *, sync: bool = True) -> None:
        if sync:
            self.sync()
        self.active = False


class AttachmentManager:
    """Keeps active attachments synchronized around every scene step."""

    def __init__(self, scene: Any):
        self.scene = scene
        self.attachments: list[RigidAttachment] = []
        self._original_step = None

    def create(
        self,
        *,
        entity: Any,
        parent_pos_fn: Callable[[], Any],
        offset,
        yaw: float = 0.0,
        child_yaw_offset: float = 0.0,
        quat=None,
        parent_quat_fn: Callable[[], Any] | None = None,
    ) -> RigidAttachment:
        attachment = RigidAttachment(
            entity=entity,
            parent_pos_fn=parent_pos_fn,
            offset=np.asarray(offset, dtype=float),
            yaw=float(yaw),
            child_yaw_offset=float(child_yaw_offset),
            quat=None if quat is None else tuple(float(v) for v in quat),
            parent_quat_fn=parent_quat_fn,
        )
        self.attachments.append(attachment)
        return attachment

    def sync(self) -> None:
        for attachment in self.attachments:
            attachment.sync()

    def __enter__(self) -> AttachmentManager:
        if self._original_step is not None:
            return self
        self._original_step = self.scene.step

        def wrapped_step(*args, **kwargs):
            self.sync()
            result = self._original_step(*args, **kwargs)
            self.sync()
            return result

        self.scene.step = wrapped_step
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._original_step is not None:
            self.scene.step = self._original_step
            self._original_step = None
