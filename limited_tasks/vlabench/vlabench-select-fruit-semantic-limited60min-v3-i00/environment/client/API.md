# Limited robot client

Use `import limited_client as robot`. The only public operations are:

- `robot.spec()`: actuator bounds, nine-dimensional action shape, fixed camera IDs, image size, step/time limits.
- `robot.observe(camera=2)`: RGB uint8 and metric depth arrays, intrinsic K, camera_to_world (optical X right/Y down/Z forward), and robot proprioception only. Cameras are fixed, 480x480. Save RGB with PIL.Image.fromarray(obs['rgb']).save('/app/output/view.png').
- `robot.step(action)`: ONE nine-element absolute actuator target, seven arm joint radians followed by two finger translations in metres. Each control is held 0.1 seconds / 100 physical substeps. Use spec bounds. Every attempted valid control, including failed motion, is permanently recorded by the server.
- `robot.status()`: active/ended, action and physical-step counts, remaining seconds. It does not reveal success, predicates or task progress.

Proprioception: joint_positions, joint_velocities, gripper_positions, tcp_position in world metres, tcp_quaternion_wxyz. RGB-D and camera calibration represent visible surfaces only. There is no object state, segmentation, semantic ground truth, object-ID skill, IK service, reset, restore, submit, scene access or file endpoint. You can write your own numeric/perception/control code using the observations. No scene simulator is installed in this container.

observe() also saves the requested RGB image under /app/output/limited-view-<camera>.jpg. Use the Codex native view_image tool to open the saved RGB file. They remain the last observed images until you call observe() again; there is no hidden automatic camera query. No depth or scene metadata is sent to the bridge.

One continuous episode, at most 4000 controls and 3600 seconds from activation. Observing, planning, coding, actions and debugging all consume this wall budget. Stop when status reports ended. Subsequent controls are rejected. You may finish early; protected evidence is sealed automatically after the agent stops. Your own trajectory/reward files do not participate in scoring. Place optional code/images under /app/output/.
