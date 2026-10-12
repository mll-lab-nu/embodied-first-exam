# Probe whether Isaac Sim's RTX renderer starts on this host. argv[1:] = extra kit args.
import sys
from isaaclab.app import AppLauncher
extra = " ".join(sys.argv[1:])
app = AppLauncher(headless=True, enable_cameras=True, kit_args=extra).app
import isaaclab.sim as sim_utils
sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=1/120))
sim_utils.GroundPlaneCfg().func("/World/ground", sim_utils.GroundPlaneCfg())
from isaaclab.sensors import CameraCfg, Camera
cam = Camera(CameraCfg(prim_path="/World/cam", height=120, width=160, data_types=["rgb"],
                       spawn=sim_utils.PinholeCameraCfg(), offset=CameraCfg.OffsetCfg(pos=(0,0,2), rot=(1,0,0,0), convention="world")))
sim.reset()
for _ in range(5):
    sim.step()
cam.update(1/120)
print("RTX_PROBE_OK", cam.data.output["rgb"].shape, float(cam.data.output["rgb"].float().mean()))
app.close()
