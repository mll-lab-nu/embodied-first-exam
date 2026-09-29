"""Task goals are curated public text, not copies of evaluator/scene state."""
GOALS = {'blanket_flatten': 'Unfold and spread the blanket flat on the table. Remove folds, rolls and self-overlaps '
                    'so the fabric covers its unfolded footprint without excessive stretching. Release the '
                    'blanket, withdraw the grippers and let it settle flat and still on the tabletop.',
 'buzz_wire_3d': 'Guide the handheld metal loop along the entire wire from its starting end to the finish, '
                 'keeping the wire inside the loop opening throughout traversal. Do not let the metal loop '
                 'touch the wire. Reaching the finish by taking the loop off the route is not completion. '
                 'Place the tool on the finish support, release it, withdraw the gripper and let it settle.',
 'cast_coil': 'Assemble the separated gold and silver Cast Coil pieces into their interlocking, alternating '
              'four-layer target configuration. Align both pieces fully; contact or grasping alone is not '
              'completion. Release both pieces, withdraw the grippers and leave the assembled puzzle stable '
              'on the table.',
 'cast_keyhole': 'Separate the silver keyhole piece from the gold piece. Place the entire silver piece '
                 'inside the green dashed goal area and hold it still briefly. Keep the gold piece outside '
                 'the area on the puzzle/system side. Holding the target with the gripper is allowed.',
 'cube_pick_place': 'Pick up the cube, hold it at least 5 cm above the table for at least 0.2 s, place it '
                    'back at its original position, open the gripper, withdraw at least 5 cm and let it '
                    'settle. Merely reaching or closing the gripper is not completion.',
 'fiber_bundling': 'Manipulate the thick sheath with the robot gripper to pass every fine fiber through the '
                   'fixed copper ring, tip first and in tip-to-root material order, until all roots and the '
                   'front sheath have passed and cleared the ring. The rear terminal stays anchored and must '
                   'not pass through the ring. Any gripper contact with a fine fiber ends the task in '
                   'failure. Avoid sharp bends and collisions; passing only the tips is not completion. Keep '
                   'the completed configuration stable.',
 'hedgehog_in_cage': 'Extract the spiked hedgehog ball from the cage. Place the whole ball, including every '
                     'spike, inside the green dashed goal area and hold it still briefly. Keep all cage '
                     'components outside the area on the puzzle/system side. Holding the target with the '
                     'gripper is allowed.',
 'horseshoe_ring': 'Free the removable ring from the horseshoes and chains. Place the entire ring inside the '
                   'green dashed goal area and hold it still briefly. Keep the horseshoes and chains outside '
                   'the area on the puzzle/system side. Holding the target with the gripper is allowed.',
 'interlocked_claws': 'Separate the brown claw piece from the other claw. Place the entire brown piece '
                      'inside the green dashed goal area and hold it still briefly. Keep the other piece '
                      'outside the area on the puzzle/system side. Holding the target with the gripper is '
                      'allowed.',
 'knot_untying': 'Untie the knot and spread the rope on the table so that nonadjacent rope segments have no '
                 'crossings or overlaps when viewed from above. Do not stretch or damage the rope to bypass '
                 'the knot. Release it, withdraw the grippers and leave the whole rope still on the '
                 'tabletop.',
 'lock_picking': 'Insert the tabbed key through the lock plates. Rotate and translate the key to negotiate '
                 'the rotor slots until its leading tab clears the final plate and the shaft reaches the '
                 'insertion goal. Keep the key aligned with the bores; the rotor pins must remain '
                 'constrained by their physical slots. Do not force the key or tabs through solid plates. '
                 'Hold the completed configuration still.',
 'orbits': 'Free the complete cord and wooden handle from the fixed ring-and-post assembly. Place the entire '
           'cord and handle inside the green dashed goal area and hold them still briefly. Keep the rings, '
           'posts and other fixed components outside the area on the puzzle/system side. Holding the target '
           'is allowed; placing only the handle in the area is not completion.',
 'rope_threading': 'Thread the rope through the cyan ring, then the green ring, then the purple ring, '
                   'following the rope from its material start to material end. Pass fully through each '
                   'aperture without extra crossings, intersecting ring material, or damaging the rope. Keep '
                   'the threaded rope still. This task currently lacks a qualified complete scoring '
                   'predicate and is exported for development.',
 'slotted_post_ring': 'Free the removable metal ring from the slotted post and cord assembly. Place the '
                      'entire ring inside the green dashed goal area and hold it still briefly. Keep the '
                      'post, cord, beads, discs and other puzzle components outside the area on the '
                      'puzzle/system side. Holding the target with the gripper is allowed.'}


def instances(*, task=None, all_variants=False, seeds=(0,)):
    from topogym.simulator import env_list
    rows = env_list(details=True)
    if task == "cube_pick_place":
        rows = [dict(task_id=task,base_variation="base",variation_details=[dict(variation_id="base",status="integrated")])]
    elif task is not None:
        rows = [r for r in rows if r["task_id"] == task]
        if not rows:
            raise ValueError(f"Unknown task: {task}")
    result, excluded = [], []
    for row in rows:
        variants = row["variation_details"] if all_variants else [dict(variation_id=row["base_variation"],status="integrated")]
        for variation in variants:
            if variation["status"] != "integrated":
                excluded.append(dict(task=row["task_id"],variation=variation["variation_id"],reason=variation.get("reason") or variation["status"]))
                continue
            for seed in seeds:
                item = dict(name=f'{row["task_id"].replace("_","-")}-{variation["variation_id"].replace("_","-")}-s{seed}',
                    instruction=GOALS[row["task_id"]], wall_clock_s=5400, replay_timeout_s=3600,
                    simulator=dict(task_id=row["task_id"],variation_id=variation["variation_id"],seed=seed,
                        control_mode="JOINT_ABS",max_physics_steps=None,history_storage="disk",enable_rgb=True,enable_depth=True,
                        enable_privileged=False,compute_backend="cuda",render_backend="nyx"))
                if task == "cube_pick_place":
                    item["fixture"] = task
                result.append(item)
    return result,excluded
