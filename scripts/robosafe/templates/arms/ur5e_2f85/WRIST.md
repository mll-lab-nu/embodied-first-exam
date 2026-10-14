The wrist camera is fixed to the hand: `tcp_from_cam` is its pose in the hand's frame; compose it with the hand's pose
from the sensor readings to get where the camera is. It is an RGB-D camera: with `include_depth=True` its depth comes
back in `res.depth` (metres along the viewing direction, 0 where nothing is within its range). The fixed cameras give
colour only. Small print is not legible in `front` and `top`; bring the wrist camera close to it.
