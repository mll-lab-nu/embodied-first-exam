"""The fifty MetaWorld+ environments (all of Meta-World's v3 environments): name -> goal text and instance seed.

The goal texts are written for the task instructions; the success check itself is Meta-World's (`evaluate_state`).
"""

# Instance seed per environment (Meta-World's reset randomization). 0 everywhere except soccer and stick-pull: with
# seed 0 Meta-World's own scripted policy does not succeed on them (soccer: 500 actions without success), so there
# would be no oracle.
SEEDS = {"soccer": 1, "stick-pull": 1}

GOALS = {
    "assembly": "Place the nut onto the peg.",
    "basketball": "Pick up the ball and place it through the basketball hoop.",
    "bin-picking": "Pick up the object from its bin and move it to the target bin.",
    "box-close": "Move the lid onto the box to close it.",
    "button-press": "Press the button inward.",
    "button-press-topdown": "Press the button downward from above.",
    "button-press-topdown-wall": "Reach past the wall and press the button downward.",
    "button-press-wall": "Reach past the wall and press the button inward.",
    "coffee-button": "Press the coffee-machine button.",
    "coffee-pull": "Pull the mug away from the coffee machine to the target.",
    "coffee-push": "Push the mug into the target position at the coffee machine.",
    "dial-turn": "Rotate the dial to its target position.",
    "disassemble": "Lift the nut off the peg.",
    "door-close": "Push the hinged door closed.",
    "door-lock": "Move the door lock into its locked position.",
    "door-open": "Pull the hinged door open.",
    "door-unlock": "Move the door lock into its unlocked position.",
    "drawer-close": "Push the drawer closed.",
    "drawer-open": "Pull the drawer open.",
    "faucet-close": "Rotate the faucet handle to close the faucet.",
    "faucet-open": "Rotate the faucet handle to open the faucet.",
    "hammer": "Use the hammer to drive the nail into the block.",
    "hand-insert": "Move the object to the target inside the opening.",
    "handle-press": "Press the handle downward.",
    "handle-press-side": "Approach the handle from the side and press it downward.",
    "handle-pull": "Pull the handle upward.",
    "handle-pull-side": "Approach the handle from the side and pull it upward.",
    "lever-pull": "Pull the lever to its target position.",
    "peg-insert-side": "Insert the peg into the side-facing socket.",
    "peg-unplug-side": "Pull the peg out of the side-facing socket.",
    "pick-out-of-hole": "Pick the object out of the hole and lift it to the target.",
    "pick-place": "Pick up the object and move it to the target.",
    "pick-place-wall": "Pick up the object and move it over the wall to the target.",
    "plate-slide": "Slide the plate forward into the target position.",
    "plate-slide-back": "Slide the plate back out to the target position.",
    "plate-slide-back-side": "Slide the plate out sideways to the target position.",
    "plate-slide-side": "Slide the plate sideways into the target position.",
    "push": "Push the object to the target.",
    "push-back": "Push the object backward to the target.",
    "push-wall": "Push the object around the wall to the target.",
    "reach": "Move the gripper to the target position.",
    "reach-wall": "Move the gripper around the wall to the target position.",
    "shelf-place": "Pick up the object and place it on the shelf at the target.",
    "soccer": "Push the soccer ball into the goal.",
    "stick-pull": "Use the stick to pull the target object.",
    "stick-push": "Use the stick to push the target object.",
    "sweep": "Sweep the object to the target position.",
    "sweep-into": "Sweep the object into the opening.",
    "window-close": "Slide the window closed.",
    "window-open": "Slide the window open.",
}
