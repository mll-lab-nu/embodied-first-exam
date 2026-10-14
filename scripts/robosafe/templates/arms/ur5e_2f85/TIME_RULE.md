- **Time moves only inside calls.** `submit` runs your rows and `get_obs(seconds=s)` holds the arm where it is
  commanded to be for s seconds of robot time; between calls the robot and the world wait, frozen, while you think.
  `get_obs()` with no seconds is free. Things in the scene (people, messages) go on while a chunk runs, and a chunk is
  not interrupted: keep chunks short where things may change.
