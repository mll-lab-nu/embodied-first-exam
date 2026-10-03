"""Drag the puzzle pieces with the mouse in a browser (MuJoCo Web Viewer, CPU, 127.0.0.1 only).

    python -m design_viewer.view --scene hedgehog_in_cage_easy --port 18080

Forward the port in VS Code (Ports panel) and open http://localhost:<port>/. Game-style
controls; the key card in the top-right corner lists them.
"""
import argparse
import queue
import time

import mujoco
from mujoco.experimental.dear_imgui import dear_imgui as imgui
from mujoco.experimental.studio import launch_passive, messages, sim, step_control, ux, viewer_app, viewer_protocol
from mujoco.experimental.studio.web import web_server
import numpy as np

from design_viewer import model as models
from design_viewer import scenes

# Shown in the browser; the viewer's font has no CJK glyphs, so English.
KEYS = (("left-drag", "move piece"), ("Shift + left-drag", "move flat"), ("right-drag", "turn piece"),
        ("G", "hold / let go"), ("R", "let all go"), ("drag empty space", "camera"),
        ("wheel", "zoom"), ("Space / Backspace", "pause / reset"))
LEFT, RIGHT = imgui.MouseButton.Left, imgui.MouseButton.Right


class GameViewer(viewer_app.ViewerApp):
    """The stock Studio viewer with game-style controls: pressing on a piece drags it, pressing on
    empty space or a fixed part moves the camera; G holds the selected piece where it is, R lets
    all go. The sim loop writes scene, free and held; requests go back through a queue."""

    def __init__(self, names, requests):
        super().__init__(viewer_app.ViewerAppConfig(show_inspector=False))
        self.names, self.requests, self.grabbed = names, requests, False
        self.scene, self.free, self.held = names[0], set(), []

    def handle_mouse_events(self):
        io, pert = imgui.GetIO(), self.viewer.perturb
        left, right = imgui.IsMouseDown(LEFT), imgui.IsMouseDown(RIGHT)
        if not (left or right):
            self.grabbed = False
        elif not self.grabbed and (imgui.IsMouseClicked(LEFT) or imgui.IsMouseClicked(RIGHT)) \
                and not io.WantCaptureMouse and not io.KeyCtrl:
            self.grabbed = self._grab(io)
        if not self.grabbed:
            super().handle_mouse_events()  # camera, wheel, and the stock double-click / Ctrl-drag
            return
        dx, dy = io.MouseDelta.x/io.DisplaySize.x, io.MouseDelta.y/io.DisplaySize.y
        if dx or dy:
            move, turn = (mujoco.mjtMouse.mjMOUSE_MOVE_H, mujoco.mjtMouse.mjMOUSE_ROTATE_H) if io.KeyShift else \
                (mujoco.mjtMouse.mjMOUSE_MOVE_V, mujoco.mjtMouse.mjMOUSE_ROTATE_V)
            active = mujoco.mjtPertBit.mjPERT_TRANSLATE if left else mujoco.mjtPertBit.mjPERT_ROTATE
            if pert.active != active:
                ux.InitPerturb(self.model, self.data, self.viewer.camera, pert, active)
            ux.MovePerturb(self.model, self.data, self.viewer.camera, pert, move if left else turn, dx, dy)

    def _grab(self, io):
        """Select the movable body under the cursor; False on empty space or a fixed part."""
        m, d = self.model, self.data
        picked = ux.Pick(m, d, self.viewer.camera, io.MousePos.x/io.DisplaySize.x, io.MousePos.y/io.DisplaySize.y,
                         io.DisplaySize.x/io.DisplaySize.y, self.viewer.vis_options)
        if picked.body <= 0 or not m.body_jntnum[picked.body]:
            return False
        pert = self.viewer.perturb
        pert.select = picked.body
        pert.localpos = d.xmat[picked.body].reshape(3, 3).T@(np.asarray(picked.point)-d.xpos[picked.body])
        if m.body(picked.body).name in self.held:  # picking up a held piece lets it go
            self.requests.put(("hold", m.body(picked.body).name))
        return True

    def handle_keyboard_events(self):
        body = selected_body(self.model, self.viewer.perturb.select)
        if imgui.IsKeyPressed(imgui.Key.G, False):
            if body in self.free:
                self.requests.put(("hold", body))
        elif imgui.IsKeyPressed(imgui.Key.R, False):
            self.requests.put(("release", None))
        else:
            super().handle_keyboard_events()

    def build_gui(self):
        super().build_gui()
        imgui.SetNextWindowPos(imgui.Vec2(imgui.GetIO().DisplaySize.x-10, 30), imgui.Cond.Always, imgui.Vec2(1, 0))
        flags = int(imgui.WindowFlags.AlwaysAutoResize) | int(imgui.WindowFlags.NoCollapse)
        if imgui.Begin("TopoGym", None, flags)[0]:
            changed, index = imgui.Combo("##scene", self.names.index(self.scene), self.names)
            if changed:
                self.requests.put(("load", self.names[index]))
            if imgui.BeginTable("keys", 2):
                for key, action in KEYS:
                    imgui.TableNextColumn()
                    imgui.Text(key)
                    imgui.TableNextColumn()
                    imgui.TextDisabled(action)
                imgui.EndTable()
            imgui.Text(f"held: {', '.join(self.held) or '-'}")
        imgui.End()


def selected_body(model, select):
    """Name of the selected body; '' if none or if the index belongs to the previous model."""
    return model.body(select).name if 0 < select < model.nbody else ""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scene", default="hedgehog_in_cage_easy", help=", ".join(scenes.list_scenes()))
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()
    # The stock viewer binds '::' (every interface of this shared machine); keep it on loopback.
    bind = web_server.bind_public_socket
    web_server.bind_public_socket = lambda host, port=0: bind("127.0.0.1", port)

    requests, stepper = queue.Queue(), step_control.StepControl()
    app = GameViewer(scenes.list_scenes(), requests)
    requests.put(("load", args.scene))
    config = viewer_protocol.ViewerConfig(gfx="web", http_port=args.port, title="TopoGym design viewer")
    with launch_passive.launch_passive(config, viewer_plugins=[app], sim_plugins=[stepper]) as handle:
        print(f"open http://localhost:{args.port}/ after forwarding port {args.port}; the server listens on "
              "127.0.0.1 only (ignore the banner's 'Remote' line).", flush=True)
        model = data = None
        while handle.is_running():
            while not requests.empty():
                kind, arg = requests.get()
                if kind == "load":
                    print(f"loading {arg} ...", flush=True)
                    scene = scenes.build(arg)
                    model = models.build(scene)
                    data = mujoco.MjData(model)
                    mujoco.mj_forward(model, data)
                    app.scene, app.free = arg, {b.name for b in scene.bodies if b.free}
                    handle.send_to_viewer(messages.ModelEvent(model=model, path=""))
                    stepper.step_control = sim.StepControl()  # restart real-time pacing for the new model
                elif kind == "hold":
                    models.toggle_hold(model, data, arg)
                else:
                    models.release_all(model, data)
            if handle.sync(model, data)[0] is not model:  # the browser loaded another model (drop): put ours back
                requests.put(("load", app.scene))
            app.held = models.held(model, data)
            time.sleep(.002)  # sync never sleeps; without this the loop spins a full core


if __name__ == "__main__":
    main()
