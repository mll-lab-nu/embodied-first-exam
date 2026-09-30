# Limited Meta-World robot client

Use `import limited_client as robot`. The only public operations are:

- `robot.spec()`: action shape/bounds and semantics, control rate, the 500-control cap, the
  60-minute budget, camera names, image size and the hand-controller (mocap) target bounds.
- `robot.observe(camera='corner')`: a dict with
  - `rgb`: uint8 (480, 480, 3) and `depth_m`: float32 (480, 480), metric depth along the optical
    axis, rendered from the native Meta-World scene (all natively visible geometry and site markers);
  - `intrinsic`: 3x3 pinhole K (pixel u right, v down; principal point at the image centre);
  - `camera_to_world`: 4x4 pose of the OpenCV optical frame (x right, y down, z forward) in the
    MuJoCo world frame (metres, +Z up);
  - `robot`: `joint_names`, `joint_positions` (7 arm joints in rad, 2 finger slides in m),
    `joint_velocities`, `hand_position` (world m), `hand_quaternion_wxyz`, `tcp_position`
    (midpoint between the finger pads), `gripper_opening` (finger separation normalised to 0..1),
    `mocap_target_position` (the hand controller's current XYZ target).
  Cameras: `topview`, `corner`, `corner2`, `corner3`, `corner4` are fixed; `behindGripper` and
  `gripperPOV` move with the hand. Images are raw camera renders: several fixed cameras are
  mounted rolled, so an image can appear upside down; the calibration describes the pixel
  geometry exactly.
- `robot.step(action)`: ONE control `[dx, dy, dz, grip]`, four finite numbers in [-1, 1]. The
  hand controller target moves by 0.01 m per unit (world frame, clipped to the mocap bounds in
  spec) and the hand follows; the wrist is fixed. grip > 0 closes, < 0 opens. Each control runs
  5 physics steps of 2.5 ms (80 Hz). Requests are validated strictly and rejected (HTTP 400),
  never clipped. Every accepted control is permanently recorded by the service.
- `robot.status()`: active/ended, action count, cap, physics steps, remaining seconds. It does
  not reveal success, predicates or task progress.

There is no object state, goal coordinate, segmentation, semantic ground truth, IK service,
reset, restore, submit, scene or file endpoint, and no simulator in this container. numpy,
scipy and Pillow are installed; write your own perception and control code.

`observe()` also saves the RGB image as /app/output/limited-view-<camera>.jpg. Use your native
view_image tool to open that file after observing. Images are not attached to your turns
automatically, and a saved image is only as recent as the last observe() of that camera.

One continuous episode: at most 500 controls and 3600 seconds from activation. Observing,
thinking, coding and controlling all consume this wall budget. When status().ended is true,
stop sending controls and finish your response immediately. Protected evidence is sealed
automatically after you stop; your own trajectory or reward files are not used for scoring.
