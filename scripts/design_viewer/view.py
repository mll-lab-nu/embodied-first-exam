"""Interactive design viewer: MuJoCo Web Viewer bound to 127.0.0.1, plus a "TopoGym design" panel.

Design intuition only (soft contacts, convex pieces, a cable instead of the FEM cord):
not physics evidence, qualification or a success label.

    python -m scripts.design_viewer.view --scene hedgehog_in_cage_easy --port 18080

Forward the port in VS Code (Ports panel) and open http://localhost:<port>/.
Mouse: left-drag orbits, right-drag pans, scroll zooms. Double-click selects a body;
Ctrl+right-drag pulls it (add Shift: horizontal plane), Ctrl+left-drag turns it.
Space pauses. The panel and this terminal take the same commands (type `help`).
"""
from __future__ import annotations

import argparse
from pathlib import Path
import queue
import sys
import threading
import time

import mujoco
from mujoco.experimental.dear_imgui import dear_imgui as imgui
from mujoco.experimental.studio import launch_passive, messages, sim, step_control, viewer_app, viewer_protocol
from mujoco.experimental.studio.web import web_server
import numpy as np

from scripts.design_viewer import exit_check, mjcf, scenes, status

POSES = scenes.RUNS/"poses"
GRIP_GAP = .02  # m, finger pads to body before a grip weld is allowed

HELP = """commands (the panel buttons send the same text):
  scenes                          list registered scenes
  load <scene> [key=value ...]    switch scene, e.g. load hedgehog_in_cage_easy window_widths=28
  gripper on|off                  rebuild with / without the Robotiq 2F-85 (restarts the scene)
  place <azimuth_deg> [roll_deg]  gripper outside pointing at the ball / ring; roll 0 = fingers open up/down, 90 = sideways
  fingers <0-255>                 open (0) .. closed (255)
  grip <body>                     weld to the gripper as it is now (finger pads within 20 mm)
  pin <body>                      weld to the world as it is now (a second hand)
  release [body]                  drop welds (all when no body is given)
  check [lift_mm]                 hedgehog: FCL straight / one-turn exit check of the current pose
  save <name> | open <name>       pose files in runs/design_viewer/poses/<scene>/
  reset | help | quit"""


class Session:
    """Sim-side state and the command set; viewer-independent so tests can drive it."""

    def __init__(self, name, overrides=None, gripper=None, poses=POSES):
        self.poses, self.message, self.status_line = Path(poses), "", ""
        self.arrow, self.checking, self.quit = None, None, False
        self.load(name, overrides, gripper)

    def load(self, name, overrides=None, gripper=None):
        self.scene = scenes.build(name, overrides)
        self.gripper = self.scene.task_id == "hedgehog_in_cage" if gripper is None else gripper
        self._rebuild()

    def _rebuild(self, model=None, data=None):
        self.model = model or mjcf.build(self.scene, self.gripper)
        if data is None:
            data = mujoco.MjData(self.model)
            mujoco.mj_forward(self.model, data)
        self.data, self.status = data, status.Status(self.scene, self.model)
        self.gripper_bodies = [i for i in range(self.model.nbody) if self.model.body(i).name.startswith("g_")]
        self.arrow, self.changed = None, True
        self.refresh()

    def refresh(self):
        holds = mjcf.holds(self.model, self.data)
        self.status_line = f"{self.status(self.data)} | holds: {', '.join(holds) or 'none'}"

    def command(self, line):
        verb, *args = line.split() or [""]
        if not verb:
            return ""
        handler = getattr(self, f"_do_{verb}", None)
        try:
            reply = handler(*args) if handler else f"unknown command {verb!r}; type help"
        except (KeyError, ValueError, TypeError, OSError) as error:  # typed input: report and keep running
            reply = f"{verb}: {error}"
        if reply is not None:
            self.message = reply
        self.refresh()
        return self.message

    @messages.handler
    def _on_step(self, event: messages.StepEvent) -> bool:
        # Runs before StepControl steps. A mouse pull on a gripper link acts at the grabbed point;
        # re-apply the pull at the whole gripper's centre of mass so it translates without swinging.
        # Ctrl+left-drag turns it with a pure torque and is left as it is.
        force = self.data.xfrc_applied[self.gripper_bodies, :3].sum(axis=0)
        if force.any():
            w = self.model.body("wrist").id
            self.data.xfrc_applied[self.gripper_bodies] = 0
            self.data.xfrc_applied[w] = [*force, *np.cross(self.data.subtree_com[w]-self.data.xipos[w], force)]
        return False

    @messages.handler
    def _on_reset(self, event: messages.ResetEvent) -> bool:
        mjcf.release(self.model, self.data)  # browser Reset: restore contact bits before the data reset
        self.arrow = None
        return False

    def _do_help(self):
        return HELP

    def _do_scenes(self):
        return "\n".join(scenes.list_scenes())

    def _do_load(self, name, *sets):
        self.load(name, scenes.parse_sets(sets))
        return f"loaded {name} {scenes.parse_sets(sets) or ''}".strip()

    def _do_gripper(self, state):
        self.gripper = state == "on"
        self._rebuild()
        return f"gripper {'on' if self.gripper else 'off'}; scene restarted"

    def _need_gripper(self):
        if not self.gripper:
            raise ValueError("no gripper in this scene (gripper on)")

    def _do_place(self, azimuth="0", roll="0"):
        self._need_gripper()
        target = next(b.name for b in self.scene.bodies if b.name in ("ball", "target_ring"))
        for name in mjcf.holds(self.model, self.data):
            if name.startswith("grip_"):
                mjcf.release(self.model, self.data, name[5:])
        mjcf.place_gripper(self.model, self.data, self.data.xpos[self.model.body(target).id], float(azimuth),
                           roll_deg=float(roll))
        return f"gripper placed at azimuth {float(azimuth):.0f} deg, roll {float(roll):.0f} deg, pointing at {target}"

    def _do_fingers(self, value):
        self._need_gripper()
        self.data.ctrl[self.model.actuator("g_fingers_actuator").id] = np.clip(float(value), 0, 255)
        return f"fingers -> {float(value):.0f}"

    def _do_grip(self, body):
        self._need_gripper()
        gap = mjcf.finger_gap(self.model, self.data, body)
        if gap > GRIP_GAP:
            return f"finger pads are {gap*1e3:.0f} mm from {body}: too far (grip needs <= {GRIP_GAP*1e3:.0f} mm)"
        mjcf.hold(self.model, self.data, body, "grip")
        return f"holding: {', '.join(mjcf.holds(self.model, self.data))}"

    def _do_pin(self, body):
        mjcf.hold(self.model, self.data, body, "pin")
        return f"holding: {', '.join(mjcf.holds(self.model, self.data))}"

    def _do_release(self, body=None):
        mjcf.release(self.model, self.data, body)
        return f"released {body or 'all'}"

    def _do_reset(self):
        mjcf.release(self.model, self.data)
        mujoco.mj_resetData(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        self.arrow = None
        return "scene reset"

    def _do_check(self, lift_mm="0"):
        if self.scene.task_id != "hedgehog_in_cage":
            raise ValueError("hedgehog scenes only")
        if self.checking and self.checking.is_alive():
            return "a check is already running"
        pose = exit_check.ball_pose(self.model, self.data)
        held = "grip_ball" in mjcf.holds(self.model, self.data)
        gripper = exit_check.gripper_geometry(self.model, self.data) if held else None

        def run():
            result = exit_check.check(self.scene, *pose, gripper=gripper, lift=float(lift_mm)/1e3)
            best = (result.get("min_rotation") or {}).get("best_direction") or result.get("best_direction")
            self.arrow = (pose[0], np.asarray(best)) if best else None
            self.message = f"{exit_check.summary(result)}\nreport: {exit_check.save(result)}"
            print(self.message, flush=True)

        self.message = f"checking the current ball pose{' with the gripper' if held else ''} ..."
        self.checking = threading.Thread(target=run, daemon=True)
        self.checking.start()

    def _do_save(self, name):
        path = self.poses/self.scene.name/f"{name}.json"
        mjcf.save_pose(path, self.scene, self.gripper, self.model, self.data)
        return f"saved {path}"

    def _do_open(self, name):
        path = self.poses/self.scene.name/f"{name}.json"
        self.scene, model, data = mjcf.load_pose(path)
        self.gripper = mjcf.has_gripper(model)
        self._rebuild(model, data)
        return f"opened {path}"

    def _do_quit(self):
        self.quit = True
        return "bye"


class Panel:
    """Viewer-side ImGui window: reads Session strings, queues command text; never touches sim data."""

    def __init__(self, session, commands):
        self.session, self.commands, self.viewer = session, commands, None
        self.names, self.azimuth, self.roll, self.pose_name = scenes.list_scenes(), 0., 0., "p1"

    @messages.handler
    def _on_init(self, event: viewer_protocol.ViewerInitEvent) -> bool:
        self.viewer = event.viewer
        return False

    @messages.handler
    def _on_gui(self, event: messages.BuildGuiEvent) -> bool:
        s, send = self.session, self.commands.put
        imgui.SetNextWindowPos(imgui.Vec2(215, 30), imgui.Cond.FirstUseEver)
        imgui.SetNextWindowSize(imgui.Vec2(430, 420), imgui.Cond.FirstUseEver)
        if imgui.Begin("TopoGym design")[0]:
            index = self.names.index(s.scene.name) if s.scene.name in self.names else 0
            changed, index = imgui.Combo("scene", index, self.names)
            if changed:
                send(f"load {self.names[index]}")
            changed, on = imgui.Checkbox("Robotiq 2F-85 gripper", s.gripper)
            if changed:
                send(f"gripper {'on' if on else 'off'}")
            selected = self.viewer.model.body(self.viewer.perturb.select).name if self.viewer.perturb.select > 0 else ""
            free = selected in {b.name for b in s.scene.bodies if b.free}
            imgui.Text(f"selected: {selected or '- (double-click a body)'}")
            if imgui.Button("Pin selected") and free:
                send(f"pin {selected}")
            if s.gripper:
                imgui.SameLine()
                if imgui.Button("Grip selected") and free:
                    send(f"grip {selected}")
            imgui.SameLine()
            if imgui.Button("Release all"):
                send("release")
            if s.gripper:
                _, self.azimuth = imgui.SliderFloat("azimuth", self.azimuth, -180, 180, "%.0f deg")
                _, self.roll = imgui.SliderFloat("roll", self.roll, -90, 90, "%.0f deg")
                if imgui.Button("Place gripper"):
                    send(f"place {self.azimuth:.0f} {self.roll:.0f}")
                imgui.SameLine()
                if imgui.Button("Close fingers"):
                    send("fingers 255")
                imgui.SameLine()
                if imgui.Button("Open fingers"):
                    send("fingers 0")
            if s.scene.task_id == "hedgehog_in_cage" and imgui.Button("Check exit (FCL)"):
                send("check")
            _, self.pose_name = imgui.InputText("pose name", self.pose_name)
            if imgui.Button("Save pose"):
                send(f"save {self.pose_name}")
            imgui.SameLine()
            if imgui.Button("Open pose"):
                send(f"open {self.pose_name}")
            imgui.Separator()
            imgui.TextWrapped(s.status_line)
            imgui.TextWrapped(s.message)
            imgui.TextWrapped("Design aid only: not physics evidence.")
        imgui.End()
        self.viewer.extra_geoms[:] = [_arrow(*s.arrow)] if s.arrow is not None else []
        return False


def _arrow(start, direction, length=.2):
    geom = mujoco.MjvGeom()
    mujoco.mjv_initGeom(geom, mujoco.mjtGeom.mjGEOM_ARROW, np.zeros(3), np.zeros(3), np.eye(3).ravel(),
                        np.array([.1, .8, .2, 1], np.float32))
    mujoco.mjv_connector(geom, mujoco.mjtGeom.mjGEOM_ARROW, .006, start, start+length*direction)
    return geom


def _read_stdin(commands):
    for line in sys.stdin:
        commands.put(line.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scene", default="hedgehog_in_cage_easy")
    parser.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--gripper", choices=("on", "off"), help="default: on for hedgehog scenes")
    args = parser.parse_args()
    session = Session(args.scene, scenes.parse_sets(args.set), None if args.gripper is None else args.gripper == "on")
    # The stock viewer binds '::' (every interface of this shared machine); keep it on loopback.
    bind = web_server.bind_public_socket
    web_server.bind_public_socket = lambda host, port=0: bind("127.0.0.1", port)
    commands, stepper = queue.Queue(), step_control.StepControl()
    config = viewer_protocol.ViewerConfig(gfx="web", http_port=args.port, title="TopoGym design viewer")
    with launch_passive.launch_passive(config, viewer_plugins=[viewer_app.ViewerApp(), Panel(session, commands)],
                                       sim_plugins=[stepper, session]) as handle:
        print(f"open http://localhost:{args.port}/ after forwarding port {args.port}; "
              f"ignore the banner's 'Remote' line, the server listens on 127.0.0.1 only.\n{HELP}", flush=True)
        threading.Thread(target=_read_stdin, args=(commands,), daemon=True).start()
        refreshed = 0.
        while handle.is_running() and not session.quit:
            while not commands.empty():
                print(session.command(commands.get()), flush=True)
            if session.changed:
                handle.send_to_viewer(messages.ModelEvent(model=session.model, path=""))
                stepper.step_control, session.changed = sim.StepControl(), False
            model, data = handle.sync(session.model, session.data)
            if model is not session.model:  # the browser loaded another model (drop / reload): put ours back
                session.changed = True
            if time.monotonic()-refreshed > .5:
                session.refresh()
                refreshed = time.monotonic()
            time.sleep(.002)  # sync never sleeps; without this the loop spins a full core


if __name__ == "__main__":
    main()
