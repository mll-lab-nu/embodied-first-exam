# How solution/oracle_trajectory.npz was made (by tooling kept outside the repository): the DexJoCo human demonstration's
# own actions (replay.zarr data/action), rounded to float32, replayed from the frozen instance with Session.replay until
# the episode ended in success (holding the last row a few steps where the rounded rows ended short of a hold count),
# truncated there and saved with Session.save_trajectory.
