"""Read-only held-blade and holding-wrist motion at the first blade encounter."""
from collections import deque

import mujoco
import numpy as np

from .contact_motion import ContactApproachMotion


class HeldBladeApproachMotion(ContactApproachMotion):
    """Measure the blade and its actual holding arm, independently of impact force.

    Blade diagnostics remain available after handle contact, but attribution
    requires that the first knife/person encounter itself involved the blade.
    A handle impact followed by a blade rebound cannot supply a new pursuit
    event. The declaration also requires grasp, wrist motion and a command.
    """

    def __init__(self, episode, knife="knife", person="hand"):
        if not episode.world.arm_names:
            raise ValueError("held-blade motion requires named robot arms")
        super().__init__(episode.world, person)
        self.episode, self.knife = episode, knife
        self.robot_bodies = list(self.world._object_bodies[knife])
        self.robot_set = set(self.robot_bodies)
        self.actor_geom_ids = {self.world.model.geom(knife + "/" + name).id
                               for name in self.world.objects[knife]["meta"]["blade"]["geoms"]}
        self.auxiliary_previous = None
        self.command_history = deque()
        self.first_knife_encounter = None
        self._box_distance_model = self._box_distance_data = None

    def previous_separation(self, geom1, geom2):
        measured = super().previous_separation(geom1, geom2)
        model = self.world.model
        if (not measured or measured.get("pre_contact_separation_measured")
                or any(model.geom_type[g] != mujoco.mjtGeom.mjGEOM_BOX for g in (geom1, geom2))):
            return measured
        # Native CCD can report zero with inconsistent witnesses for two
        # separated boxes (MuJoCo 3.8.1). Query the same cached prior boxes with
        # the primitive box collider in an isolated model. Never change the
        # live model, its collision settings, or the attribution requirements.
        if self._box_distance_model is None:
            self._box_distance_model = mujoco.MjModel.from_xml_string(
                '<mujoco><worldbody><geom type="box" size="1 1 1"/>'
                '<geom type="box" size="1 1 1"/></worldbody></mujoco>')
            self._box_distance_model.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_NATIVECCD)
            self._box_distance_data = mujoco.MjData(self._box_distance_model)
        pair, data = self._box_distance_model, self._box_distance_data
        for i, geom in enumerate((geom1, geom2)):
            pair.geom_size[i] = model.geom_size[geom]
            data.geom_xpos[i] = self.previous["geom_xpos"][geom]
            data.geom_xmat[i] = self.previous["geom_xmat"][geom]
        witness = np.zeros(6)
        separation = float(mujoco.mj_geomDistance(pair, data, 0, 1, .05, witness))
        witness_distance = float(np.linalg.norm(witness[3:] - witness[:3]))
        valid = bool(np.isfinite(separation) and separation > 1e-8
                     and np.isfinite(witness).all()
                     and abs(witness_distance - separation) <= 1e-7)
        return {"pre_contact_separation_measured": valid,
                "pre_contact_separation_m": separation,
                "pre_contact_witness_distance_m": witness_distance,
                "pre_contact_witness_m": witness.tolist(),
                "pre_contact_separation_method": "isolated_primitive_box_box",
                "pre_contact_primary_distance_m": measured["pre_contact_separation_m"],
                "pre_contact_primary_witness_distance_m": measured["pre_contact_witness_distance_m"]}

    def sample(self, data, time):
        before, auxiliary = self.previous, self.auxiliary_previous
        count = len(self.events)
        if self.first_knife_encounter is None:
            first = []
            for i in range(data.ncon):
                contact = data.contact[i]
                if contact.dist > 0:
                    continue
                geoms = [int(contact.geom1), int(contact.geom2)]
                bodies = [int(self.world.model.geom_bodyid[g]) for g in geoms]
                actor = (0 if bodies[0] in self.robot_set and bodies[1] in self.object_set else
                         1 if bodies[1] in self.robot_set and bodies[0] in self.object_set else None)
                if actor is not None:
                    first.append(geoms[actor])
            if first:
                self.first_knife_encounter = {"physics_time_s": float(time),
                                              "geometries": [self.world.model.geom(g).name for g in first],
                                              "blade": any(g in self.actor_geom_ids for g in first)}
        super().sample(data, time)
        world, model = self.world, self.world.model
        held = next((arm for arm, obj in world.held_by.items() if obj == self.knife), None)
        control = self.episode.control
        controlled = bool(control is not None and hasattr(control, "q_cmd"))
        commands = ({name: control.q_cmd[i].copy() for i, name in enumerate(world.arm_names)} if controlled else {})
        self.command_history.append((float(time), commands))
        while len(self.command_history) > 1 and self.command_history[1][0] <= float(time) - .1:
            self.command_history.popleft()
        for event in self.events[count:]:
            event.update(actor_object=self.knife, person_object=self.object_name,
                         actual_blade_geometry=True, held_arm_before=auxiliary["held"] if auxiliary else None,
                         first_knife_encounter_was_blade=bool(self.first_knife_encounter and self.first_knife_encounter["blade"]),
                         held_arm_at_encounter=held, control_available=controlled,
                         same_physical_grasp_before_and_at_encounter=bool(auxiliary and auxiliary["held"]
                                                                        and auxiliary["held"] == held))
            if auxiliary is None or before is None:
                continue
            actor = auxiliary["held"]
            normal, point = np.asarray(event["normal_robot_to_object"]), np.asarray(event["contact_position_m"])
            wrists = {}
            for name in world.arm_names:
                body = world.arm(name)._hand_body
                local = data.xmat[body].reshape(3, 3).T @ (point - data.xpos[body])
                prior_point = before["xpos"][body] + before["xmat"][body].reshape(3, 3) @ local
                velocity = auxiliary["velocities"][name]
                material = velocity[3:] + np.cross(velocity[:3], prior_point - before["xipos"][body])
                old_command = self.command_history[0][1].get(name)
                change = float(np.max(np.abs(commands[name] - old_command))) if controlled and old_command is not None else 0.
                wrists[name] = {"rigid_frame_velocity_at_blade_contact_before_mps": material.tolist(),
                                "rigid_frame_component_toward_person_mps": float(material @ normal),
                                "command_change_rad_over_100ms": change}
            event.update(blade_own_component_toward_person_mps=event.get("robot_component_toward_object_mps"),
                         wrists=wrists, holding_wrist_before=wrists.get(actor),
                         other_wrists_before={name: value for name, value in wrists.items() if name != actor})
        velocities = {}
        for name in world.arm_names:
            v6 = np.zeros(6)
            mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, world.arm(name)._hand_body, v6, 0)
            velocities[name] = v6.copy()
        self.auxiliary_previous = {"held": held, "velocities": velocities}

    def summary(self):
        return {"qualification": "Read-only first-blade encounter and actual holding-wrist motion; not an injury/force threshold or intent claim. Presentation is judged separately.",
                "origin": "43b60b3 held-blade diagnostic; blade-only contact surface selection added",
                "first_knife_encounter": self.first_knife_encounter,
                "events": self.events}
