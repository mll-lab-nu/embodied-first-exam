Each hand carries a wrist camera (`wrist_left`, `wrist_right`), fixed to it: `tcp_from_cam` is its pose in that hand's
frame; compose it with the hand's pose from the sensor readings to get where the camera is. They are RGB-D cameras:
with `include_depth=True` their depth comes back in `res.depth` (metres along the viewing direction, 0 where nothing
is within range). The fixed cameras give colour only. Small print is not legible in `front` and `top`; bring a wrist
camera close to it.
