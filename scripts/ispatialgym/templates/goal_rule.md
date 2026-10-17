## Your task: make the scene look like a picture
`/app/goal.png` is what the robot's head camera (`robot_r1:zed_link:Camera:0`) sees once the task is done. It is the same
camera, resolution and intrinsics as the robot's own head camera. Change the scene so that it looks like the picture. No
sentence here names the objects that matter or what to do with them: the picture is the whole task. The robot does not have to
match the picture (its arms, grippers and base may be anywhere), and nothing the picture does not show is judged.

## When $who succeeds
$checks
After every control step it checks three conditions:
1. **Relations.** The objects the task is about stand in the relations the picture shows: what is on, in, under, next to
   or touching what, what is open, and which objects the robot holds or has let go of.
2. **Poses.** Every pose the task measures is within its tolerance of the pose in the picture:
$targets
3. **At rest.** Conditions 1 and 2 have both held at every one of the last **$settle_steps control steps** ($settle_s s of
   simulated time), and during those steps the objects the task is about and the robot itself are still:
   - at every step, each of them moves slower than 0.001 m/s and 0.005 rad/s, and each robot joint slower than 0.02 rad/s;
   - over the whole window, none of them drifts more than 0.01 m or 0.05 rad, and no robot joint more than 0.05.

$who_cap succeeds at the first control step where all three hold, which is the last step of that window. This text does
not say which objects the task is about: the picture shows them.

**Once the scene looks right, stop the robot and keep it still for at least $settle_steps control steps.** $hold_how
