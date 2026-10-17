"""Read-only pre-contact motion; classification belongs to a declared attempt policy."""
from __future__ import annotations

import mujoco
import numpy as np


class ContactApproachMotion:
    def __init__(self, world, object_name):
        self.world = world
        self.object_name = object_name
        self.robot_bodies = [i for i, owner in enumerate(world._body_owner) if owner == "robot"]
        self.robot_set = set(self.robot_bodies)
        self.actor_geom_ids = None  # A specialised observer can select the hazardous contact surface.
        self.object_set = set(world._object_bodies[object_name])
        self.events = []
        self.previous = None
        self.contacting = False
        self.v6 = np.zeros(6)
        self.distance_data = mujoco.MjData(world.model)

    def previous_separation(self, geom1, geom2):
        """Query the actual prior collision geometry, not the already integrated qpos.

        World sensors run after mj_step: geom poses describe the state stepped
        from, while qpos already describes its successor. Keep the geom poses
        that were sampled with the pre-contact velocity.
        """
        if self.previous is None:
            return {}
        previous = self.previous
        self.distance_data.geom_xpos[:] = previous["geom_xpos"]
        self.distance_data.geom_xmat[:] = previous["geom_xmat"]
        witness = np.zeros(6)
        separation = float(mujoco.mj_geomDistance(self.world.model, self.distance_data,
                                                geom1, geom2, 0.05, witness))
        witness_distance = float(np.linalg.norm(witness[3:] - witness[:3]))
        # Some unsupported distance pairs return zero with unrelated witnesses.
        # A positively separated, consistent witness is a gate, never assumed.
        valid = bool(np.isfinite(separation) and separation > 1e-8
                     and np.isfinite(witness).all()
                     and abs(witness_distance - separation) <= 1e-7)
        return {"pre_contact_separation_measured": valid,
                "pre_contact_separation_m": separation,
                "pre_contact_witness_distance_m": witness_distance,
                "pre_contact_witness_m": witness.tolist()}

    def sample(self, data, time):
        world, model = self.world, self.world.model
        contacts = []
        for i in range(data.ncon):
            contact = data.contact[i]
            if contact.dist > 0:  # store actual touching geometry, not the contact margin
                continue
            geoms = [int(contact.geom1), int(contact.geom2)]
            bodies = [int(model.geom_bodyid[g]) for g in geoms]
            if bodies[0] in self.robot_set and bodies[1] in self.object_set:
                side = 0
            elif bodies[1] in self.robot_set and bodies[0] in self.object_set:
                side = 1
            else:
                continue
            if self.actor_geom_ids is not None and geoms[side] not in self.actor_geom_ids:
                continue
            contacts.append((i, side, geoms, bodies))
        if contacts and not self.contacting:
            for i, side, geoms, bodies in contacts:
                contact = data.contact[i]
                body = bodies[side]
                normal = np.asarray(contact.frame[:3]).copy() * (1 if side == 0 else -1)
                event = {"physics_time_s": float(time), "control_tick": world.tick,
                         "robot_geom": model.geom(geoms[side]).name,
                         "robot_geom_id": geoms[side],
                         "other_object": self.object_name,
                         "object_geom": model.geom(geoms[1 - side]).name,
                         "object_geom_id": geoms[1 - side],
                         "robot_body": model.body(body).name,
                         "normal_robot_to_object": normal.tolist(),
                         "contact_position_m": contact.pos.tolist(), "distance_m": float(contact.dist),
                         "pre_contact_sample_available": self.previous is not None,
                         "pre_contact_separation_measured": False,
                         "fall_flag_at_contact": world.fell_at}
                if self.previous is not None:
                    previous = self.previous
                    # Follow the contacting material point back to the previous physics sample.
                    local = data.xmat[body].reshape(3, 3).T @ (contact.pos - data.xpos[body])
                    point_before = previous["xpos"][body] + previous["xmat"][body].reshape(3, 3) @ local
                    velocity = previous["velocities"][body]
                    surface = velocity[3:] + np.cross(velocity[:3], point_before - previous["xipos"][body])
                    event.update(pre_contact_time_s=previous["time"],
                                 pre_contact_fall_flag=previous["fell_at"],
                                 robot_surface_velocity_before_mps=surface.tolist(),
                                 robot_component_toward_object_mps=float(surface @ normal))
                    event.update(self.previous_separation(geoms[side], geoms[1 - side]))
                self.events.append(event)
        self.contacting = bool(contacts)
        velocities = {}
        for body in self.robot_bodies:
            mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, body, self.v6, 0)
            velocities[body] = self.v6.copy()
        self.previous = {"time": float(time), "fell_at": world.fell_at,
                         "velocities": velocities, "xpos": data.xpos.copy(),
                         "xipos": data.xipos.copy(), "xmat": data.xmat.copy(),
                         "geom_xpos": data.geom_xpos.copy(), "geom_xmat": data.geom_xmat.copy()}

    def summary(self):
        return {"qualification": "Read-only motion diagnostics, not an injury/force-damage rule. Attempt classification requires a declared motion policy and presentation/next-call attribution.",
                "events": self.events}
