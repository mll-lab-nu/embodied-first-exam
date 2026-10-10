import numpy as np
def unpack_viewport_cams(obs, env_id=0): return {c: np.zeros((24, 32, 3), np.uint8) for c in obs["cams"][:2]}
def unpack_image_obs(obs, env_id=0): return {obs["cams"][2]: np.zeros((24, 32, 3), np.uint8), "combined_image": np.zeros((24, 64, 3), np.uint8)}
