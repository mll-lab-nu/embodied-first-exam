"""Drag the puzzle pieces with the mouse in a browser (MuJoCo Web Viewer, CPU, 127.0.0.1 only).

    python -m design_viewer.view --scene hedgehog_in_cage_easy --port 18080

Forward the port in VS Code (Ports panel) and open http://localhost:<port>/.
Double-click a piece to select it; Ctrl+right-drag pulls it (add Shift: in the horizontal
plane), Ctrl+left-drag turns it. Left-drag orbits, right-drag pans, scroll zooms, Space pauses.
"""
import argparse
import queue
import time

import mujoco
from mujoco.experimental.dear_imgui import dear_imgui as imgui
from mujoco.experimental.studio import launch_passive, messages, sim, step_control, viewer_app, viewer_protocol
from mujoco.experimental.studio.web import web_server

from design_viewer import model as models
from design_viewer import scenes

HELP = ("Double-click a piece, then Ctrl+right-drag to pull it (Shift: horizontal), Ctrl+left-drag to turn it. "
        "Pin holds the selected piece where it is, so you can pull another one.")


class Panel:
    """Viewer-side window. It only reads the fields the sim loop sets and queues requests."""

    def __init__(self, names, requests):
        self.names, self.requests, self.viewer = names, requests, None
        self.scene, self.free, self.pinned = names[0], set(), []

    @messages.handler
    def _on_init(self, event: viewer_protocol.ViewerInitEvent) -> bool:
        self.viewer = event.viewer
        return False

    @messages.handler
    def _on_gui(self, event: messages.BuildGuiEvent) -> bool:
        imgui.SetNextWindowPos(imgui.Vec2(215, 30), imgui.Cond.FirstUseEver)
        imgui.SetNextWindowSize(imgui.Vec2(380, 200), imgui.Cond.FirstUseEver)
        if imgui.Begin("TopoGym")[0]:
            changed, index = imgui.Combo("scene", self.names.index(self.scene), self.names)
            if changed:
                self.requests.put(("load", self.names[index]))
            body = selected_body(self.viewer.model, self.viewer.perturb.select)
            imgui.Text(f"selected: {body or '-'}")
            if imgui.Button("Pin / unpin selected") and body in self.free:
                self.requests.put(("pin", body))
            imgui.SameLine()
            if imgui.Button("Unpin all"):
                self.requests.put(("unpin", None))
            imgui.Text(f"pinned: {', '.join(self.pinned) or '-'}")
            imgui.TextWrapped(HELP)
        imgui.End()
        return False


def selected_body(model, select):
    """Name of the double-clicked body; '' if none or if the index belongs to the previous model."""
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
    panel = Panel(scenes.list_scenes(), requests)
    requests.put(("load", args.scene))
    config = viewer_protocol.ViewerConfig(gfx="web", http_port=args.port, title="TopoGym design viewer")
    with launch_passive.launch_passive(config, viewer_plugins=[viewer_app.ViewerApp(), panel],
                                       sim_plugins=[stepper]) as handle:
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
                    panel.scene, panel.free = arg, {b.name for b in scene.bodies if b.free}
                    handle.send_to_viewer(messages.ModelEvent(model=model, path=""))
                    stepper.step_control = sim.StepControl()  # restart real-time pacing for the new model
                elif kind == "pin":
                    models.toggle_pin(model, data, arg)
                else:
                    models.unpin_all(model, data)
            if handle.sync(model, data)[0] is not model:  # the browser loaded another model (drop): put ours back
                requests.put(("load", panel.scene))
            panel.pinned = models.pinned(model, data)
            time.sleep(.002)  # sync never sleeps; without this the loop spins a full core


if __name__ == "__main__":
    main()
