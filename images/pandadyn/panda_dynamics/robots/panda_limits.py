"""FER/Panda ceilings (not FR3); SI units, arm joint order panda_joint1..7."""

import numpy as np

LOWER = np.array([-2.8973, -1.7628, -2.8973, -3.0718, -2.8973, -0.0175, -2.8973])
UPPER = np.array([2.8973, 1.7628, 2.8973, -0.0698, 2.8973, 3.7525, 2.8973])
VELOCITY = np.array([2.175] * 4 + [2.61] * 3)
ACCELERATION = np.array([15, 7.5, 10, 12.5, 15, 20, 20])
JERK = np.array([7500, 3750, 5000, 6250, 7500, 10000, 10000])
TORQUE = np.array([87] * 4 + [12] * 3)
TORQUE_RATE = np.full(7, 1000.0)
FINGER_SPEED = 0.05
# Conservative engineering choice: 15 N each, 30 N sum. The manual's
# 30–70 N grasp force is NOT treated as a 70 N per-joint allowance.
FINGER_FORCE = 15.0
CART_SPEED, CART_OMEGA = 1.7, 2.5
CART_ACCELERATION, CART_ALPHA = 13.0, 25.0
