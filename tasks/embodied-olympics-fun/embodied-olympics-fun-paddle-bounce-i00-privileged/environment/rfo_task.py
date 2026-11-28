"""Paddle bounce (table tennis ball control): a ball dropped above the paddle in your right hand kept bouncing on the
blade, every bounce back up to the height it was dropped from. The paddle is a free 0.14 kg table tennis racket held
only by the contact and friction of the right hand, the G1's own Dex3-1 three-finger hand: it can slip, turn in the
hand and be dropped.

The ball: the official 40 mm, 2.7 g ball with Google DeepMind's identified fluid coefficients and thin-shell inertia,
and Embodied Olympics' ball-blade contact pair (roboolympics/sports/tabletennis/sim/scene/tt_scene.xml, Apache-2.0;
hand-picked, not identified). The drop is a machine's: the ball rests in the cup of a dropper (the shared ball machine
block below, Dropper: a ring round the ball and two trapdoor leaves under it on force-limited slides, at the end of an
arm on a column); at drop_time_s the leaves slide apart and the ball falls from rest by gravity alone, and 0.15 s
later the cup, on a force-limited carriage, pulls 0.35 m back along the arm (+x), out of the ball's way. Nothing is
pinned or given a velocity.

The paddle (FREE_PADDLE; the block is shared, byte for byte, with table-tennis-return): a rigid 15 x 15 x 1.5 cm
blade, 0.09 kg, on a straight handle of a real racket's size, 100 mm long, 32 mm wide and 25 mm thick (ITTF Law 2.4
sets no size, shape or weight for the blade or the handle; a common "straight" handle is 100 x 30-34 x 23-26 mm), as a
free body. Its blade's centre is 0.175 m from the butt.

The hand: the G1's Dex3-1 (rfo.realhand "dex3": thumb 3 joints, index and middle 2 each, the device's torques), the
paddle held by contact and friction only, no weld: a shakehand grip, the handle across the palm (along the hand's
grasp frame's y, the blade beyond the index finger's side), the fingers and the thumb closed round it, the blade's
faces looking along the palm's normal; the butt GRIP["butt_out_m"] short of the grasp centre on the other side; the
closure command 1. "In the hand" = the handle touches the hand's fingers and its thumb or palm (the core's holding
rule).

Why the rule is "back up to the drop height": no passive rebound reaches the height the ball fell from; a bounce that
does has been given energy by the blade. Measured on this module: a ball dropped from
1.20 m onto the still, level blade held in the hand (its centre 0.87 m up) rises 0.25 m above it, to 1.15 m:
below the drop height, so the first passive rebound already fails.

The simulator's options: DeepMind's table-tennis model uses elliptic cones with impratio 10; a world with a real hand
needs impratio 100 (realhand.IMPRATIO: with 10 a clamped handle creeps under a steady torque), and this module leaves it at
100 (it is the real-hand worlds' setting for every contact; the ball-blade pair was hand-picked, not identified).
"""
import xml.etree.ElementTree as ET

import math

import mujoco
import numpy as np

from rfo.referee import Touch
from rfo.scene import HITTABLE, OFFICIAL
from rfo.task import TaskBase
# A rigid paddle (wooden blade and handle; the ball's own contact with the blade is the explicit pair)'s contact with
# the robot, the venue's fixtures and the other props (the ground keeps its own: rfo/world.py GROUND_SOLMIX): the
# stiff contact of the core's shells (rfo/world.py SHELL_CONTACT: solref 0.004 s, solimp 0.99 0.999 0.0005, from
# Embodied Olympics' weightlifting fix, a rigid prop on the robot's aluminium) with a solmix that wins over a default-
# contact geom; a ball (priority 1) keeps its own bounce. With MuJoCo's default soft contact (solref 0.02 1, solimp
# 0.9 0.95) it sank 48 mm into the floor and the robot (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402


# ===================================================================================== ball machine (shared block)
# A shared block: the same code in each family module that feeds a ball; a task directory holds one module.
#
# A physical ball machine in place of a ball that is pinned and then given a velocity. Real ball machines (tennis:
# Lobster, Spinshot; table tennis: two-wheel robots; baseball / softball: JUGS-type two-wheel pitching machines;
# volleyball and football: two-wheel launchers) throw the ball with two counter-rotating wheels driven by
# speed-controlled, torque-limited motors: the ball, fed from a hopper down a chute, is squeezed in the gap between the
# wheels (the gap is smaller than the ball) and leaves with about the wheels' mean surface speed; a difference between
# the two surface speeds rolls it, which gives the spin (Cross & Lindsey, "Ball machines", in Brody, Cross and Lindsey,
# The Physics and Technology of Tennis, 2002; Ferraresi et al., "Analysis of the throwing mechanism of a two-wheel
# pitching machine", Sports Engineering 2014). Here:
#
#   wheels   two solid discs on hinge joints in a fixed head, each driven by a MuJoCo velocity actuator (a speed loop,
#            gain kv) whose torque is limited to motor_torque_n_m (the motor's); their tread meets the ball in an
#            explicit contact pair: the series compliance of ball and tread (contact_k_n_m per contact, quasi-static,
#            the sources in PRESETS), the pinch's restitution, the tread's friction. The ball's own dynamic contact with
#            the wheels is excluded (the pair replaces it, it does not add to it).
#   aim      the head is fixed in the venue at the pose the launch needs (an operator aims a machine before a drill):
#            its axis L is the launch direction corrected by the calibrated deflection, the wheel pair is turned about
#            L so that the spin's axis is the one asked for (two wheels give spin about an axis across the flight
#            only: a component along the flight, gyro spin, is not made and is reported).
#   feed     the ball lies in the throat, a cradle of two steel rails along the head's axis behind the wheels (in
#            reality the end of the hopper's chute), between a gate in front and the feed ram behind; both are plates
#            on slide joints driven by force-limited position servos (the gate: gate_force_n, the class of a small
#            12 V push-pull solenoid; the ram: about 100 x the ball's weight in newtons, its speed limited by the
#            slide's damping to about 1.5 m/s, as a pneumatic or crank feeder). feed(t): the gate opens, then the
#            ram pushes the ball into the wheels. It works at any elevation from about -30 to +80 degrees (a gravity
#            chute alone cannot feed a ball that has to go up into the wheels). One ball per machine load.
#   dropper  Dropper below: a ball resting on two trapdoor leaves on force-limited slides, opened apart: a drop with
#            neither speed nor spin, by gravity only.
#
# calibration: the wheel surface speeds for a launch come from FIT, a table measured in simulation with this very
# block (calibrate() below; 1 ms steps, implicitfast, elliptic cones, impratio 100, the venue's air) for each preset:
# per mean surface speed V and relative difference q = D / V, the exit speed / V, the spin across the flight and the
# exit's turn towards the faster wheel; and a fitted droop (g0 + g1 cos(elevation) / speed^2, deg). solve() inverts
# the table (bilinear, Newton) and the head is aimed to cancel the turn and the droop. ACCURACY records what launches
# set from the table achieved in the standalone world, and the spread over 8 perturbations (the ball 1 mm off along
# and across the axis, the wheel speeds +-0.5 %). Football and volleyball: speed within 2 % (a slow 4.5 m/s lob: 7 %
# short), direction within 2 deg, spin within 10 %, spread under 0.6 % and 0.9 deg. The small balls are less
# regular: tennis within 2 % and 3 deg; baseball at 15 m/s within 1 %, but at 21 m/s / 45 deg 10 % fast with a
# large spin; table tennis within 2 % in speed but 7-14 deg off in direction (spread 3-4 deg); juggling 4-8 % slow.
# A family measures its own shot in its world and trims the launch it asks for (or the
# wheel speeds (BallMachine(..., rim=(v0, v1), deflect_deg=...)).
#
# Machine, not a person: wherever a family's rule book has a server, a pitcher, a tosser, the machine stands in its
# place (a declared deviation, worded by the family).
import math as _bm_math
import xml.etree.ElementTree as _bm_ET

import numpy as _bm_np

# Per-preset machine and ball-contact data. contact_k_n_m: the contact's stiffness per side (two in series across the
# ball give its diametral stiffness, so per side = 2 x the diametral value when the tread is much stiffer);
# contact_e: the restitution of that compression; squeeze_m: ball diameter minus the wheels' gap (a machine setting).
PRESETS = {
    # Tennis: ITF Appendix I forward deformation 5.6-7.4 mm under 8.165 kg (80 N): diametral 12.3 kN/m, per side 24.6;
    # rebound e 0.745 (ITF). Wheels 0.25 m across with a rubber tread on the felt, mu 1.0 (estimate; rubber on cloth
    # 0.8-1.2); 0.8 kg; motors 0.6 N m (a 150-200 W brushless drive at ~2500 rpm, the class of 24 V tennis machines).
    # Squeeze 20 mm (the gap 47 mm: about 30 % of the diameter).
    "tennis": dict(ball_radius_m=0.0335, ball_mass_kg=0.0577, contact_k_n_m=24600.0, contact_e=0.745, tread_mu=1.0,
                   wheel_radius_m=0.125, wheel_half_width_m=0.018, wheel_mass_kg=0.8, squeeze_m=0.020,
                   motor_torque_n_m=0.6, motor_kv=0.2, max_rim_speed_m_s=45.0),
    # Table tennis: 40 mm, 2.7 g (ITTF 2.3); e 0.9 (ITTF drop test). The contact's stiffness is limited by the 1 ms
    # physics step (its natural frequency at most about 650 rad/s, as the tennis ball's): 1.1 kN/m per side, softer
    # than a real ball's (estimated 10 kN/m); squeeze 4 mm. Wheels 50 mm across, rubber mu 0.9 (estimate), 20 g;
    # a small 12 V DC motor, 0.02 N m (two-wheel table-tennis robots).
    "tabletennis": dict(ball_radius_m=0.020, ball_mass_kg=0.0027, contact_k_n_m=1100.0, contact_e=0.9, tread_mu=0.9,
                        wheel_radius_m=0.025, wheel_half_width_m=0.011, wheel_mass_kg=0.02, squeeze_m=0.004,
                        motor_torque_n_m=0.02, motor_kv=0.007, max_rim_speed_m_s=30.0),
    # Baseball: JUGS-type pitching machine: pneumatic tyres about 0.26 m across; the tyre's compliance dominates
    # (about 30 kN/m, estimate for a 4.00-4 tyre at low pressure); e 0.6; rubber on leather mu 0.7; wheel 2.0 kg;
    # motors 1.5 N m (a 1/3 hp drive at ~1500 rpm). Squeeze 12 mm.
    "baseball": dict(ball_radius_m=0.0365, ball_mass_kg=0.145, contact_k_n_m=30000.0, contact_e=0.6, tread_mu=0.7,
                     wheel_radius_m=0.13, wheel_half_width_m=0.020, wheel_mass_kg=2.0, squeeze_m=0.012,
                     motor_torque_n_m=1.5, motor_kv=0.5, max_rim_speed_m_s=45.0),
    # An inflated ball pressed flat by d on one side pushes with its gauge pressure p over the flat (area 2 pi r d):
    # per side K = 2 pi r p (the membrane's own stiffness neglected).
    # Volleyball (FIVB: 65-67 cm, 260-280 g, 0.300-0.325 kg/cm2 = 29.4-31.9 kPa): K = 2 pi 0.105 m 30.6 kPa = 20.2 kN/m;
    # e 0.75; pneumatic wheels 0.40 m, rubber on PU mu 0.9 (estimate); 3 kg; geared motors, 10 N m at the wheel (a
    # 0.5 kW drive at ~500 rpm). Squeeze 35 mm.
    "volleyball": dict(ball_radius_m=0.105, ball_mass_kg=0.270, contact_k_n_m=20200.0, contact_e=0.75, tread_mu=0.9,
                       wheel_radius_m=0.20, wheel_half_width_m=0.057, wheel_mass_kg=3.0, squeeze_m=0.035,
                       motor_torque_n_m=10.0, motor_kv=3.0, max_rim_speed_m_s=40.0),
    # Football (IFAB Law 2: size 5, 68-70 cm, 410-450 g, 0.6-1.1 atm = 61-111 kPa): K = 2 pi 0.110 m 85 kPa =
    # 58.7 kN/m; e 0.85; wheels 0.40 m, rubber mu 0.9 (estimate); 3 kg; geared motors, 15 N m at the wheel (a
    # 0.75 kW drive at ~500 rpm; squeezing the ball takes K d^2 = 13 J per shot, given back as it leaves). Squeeze 30 mm.
    "football": dict(ball_radius_m=0.110, ball_mass_kg=0.430, contact_k_n_m=58700.0, contact_e=0.85, tread_mu=0.9,
                     wheel_radius_m=0.20, wheel_half_width_m=0.060, wheel_mass_kg=3.0, squeeze_m=0.030,
                     motor_torque_n_m=15.0, motor_kv=5.0, max_rim_speed_m_s=65.0),
    # A 70 mm, 130 g juggling ball (thud / beanbag: soft, dead): diametral about 3 kN/m (estimate), per side 6;
    # e 0.3; wheels 0.12 m, rubber mu 0.9; 0.3 kg; motors 0.5 N m. Squeeze 10 mm.
    "juggling": dict(ball_radius_m=0.035, ball_mass_kg=0.13, contact_k_n_m=6000.0, contact_e=0.3, tread_mu=0.9,
                     wheel_radius_m=0.06, wheel_half_width_m=0.019, wheel_mass_kg=0.3, squeeze_m=0.010,
                     motor_torque_n_m=0.5, motor_kv=0.15, max_rim_speed_m_s=15.0),
}

# FIT[preset]: the calibration table measured with calibrate(), elevation 20 deg; feed_s: from
# feed() to the ball leaving the wheels (mean).
FIT = {
    "tennis": dict(
        V=[8.0, 14.0, 20.0, 26.0, 32.0, 38.0, 44.0],
        q=[-0.2, -0.1, 0.0, 0.1, 0.2],
        ratio=[[0.91623, 0.91707, 0.91793, 0.91602, 0.91663], [0.8702, 0.87059, 0.87175, 0.8887, 0.88762], [0.84435, 0.84455, 0.84475, 0.84491, 0.83062], [0.79376, 0.7933, 0.79292, 0.79219, 0.80661], [0.76102, 0.75984, 0.7587, 0.7673, 0.76788], [0.73942, 0.73989, 0.74119, 0.743, 0.72845], [0.69262, 0.69456, 0.69352, 0.70631, 0.70683]],
        spin=[[-25.97, -13.644, -1.318, 10.959, 23.299], [-37.74, -16.686, 3.938, 23.836, 44.006], [-57.627, -28.785, 0.039, 28.883, 48.835], [-94.391, -57.283, -20.166, 17.183, 42.044], [-128.059, -82.187, -36.266, -3.865, 38.85], [-117.995, -68.475, -0.114, 49.272, 32.101], [-132.276, -90.158, -29.183, -3.797, 50.953]],
        du=[[0.365, 0.184, 0.0, 0.139, -0.006], [-0.314, -0.22, 0.0, 0.643, 0.811], [0.346, 0.168, 0.0, -0.171, -0.085], [0.868, 0.436, 0.0, -0.02, 1.33], [0.611, 0.304, 0.0, 2.184, 1.84], [-1.284, -1.537, 0.0, -0.046, 0.286], [1.852, -0.208, 0.0, 1.353, 1.49]],
        g0=0.9892,
        g1=-60.219,
        feed_s=0.0929,
    ),
    "tabletennis": dict(
        V=[2.0, 4.0, 7.0, 10.0, 14.0, 19.0, 25.0],
        q=[-0.2, -0.1, 0.0, 0.1, 0.2],
        ratio=[[1.05831, 1.05909, 1.05988, 1.07009, 1.07003], [0.76257, 0.76373, 0.76477, 0.76581, 0.76684], [0.60013, 0.59937, 0.59849, 0.59763, 0.59678], [0.51259, 0.51122, 0.51054, 0.45919, 0.45975], [0.42366, 0.44816, 0.42676, 0.42755, 0.43471], [0.35144, 0.33797, 0.33706, 0.34751, 0.35056], [0.28733, 0.28615, 0.28777, 0.28938, 0.2859]],
        spin=[[-4.761, -0.344, 4.072, 12.533, 16.859], [-21.701, -13.666, -5.607, 2.456, 10.518], [-49.463, -38.032, -26.632, -15.24, -3.844], [-53.624, -38.71, -23.727, -5.921, 8.416], [-46.411, -43.249, 31.84, 49.555, 49.778], [9.934, 16.026, 34.039, 69.943, 75.421], [6.402, 39.824, 60.534, 81.222, 83.448]],
        du=[[-0.312, -0.156, 0.0, -22.658, -22.985], [-0.262, -0.078, 0.0, 0.067, 0.135], [-0.79, -0.399, 0.0, 0.404, 0.809], [-0.593, -0.222, 0.0, 10.495, 10.597], [3.896, 0.409, 0.0, -0.492, 0.768], [0.741, 0.434, 0.0, -0.833, -1.089], [4.092, 0.208, 0.0, -0.211, 1.36]],
        g0=6.0715,
        g1=-70.955,
        feed_s=0.0759,
    ),
    "baseball": dict(
        V=[8.0, 14.0, 20.0, 26.0, 32.0, 40.0],
        q=[-0.2, -0.1, 0.0, 0.1, 0.2],
        ratio=[[0.92056, 0.91959, 0.91864, 0.92304, 0.92228], [0.87599, 0.87507, 0.87418, 0.87325, 0.87269], [0.81671, 0.81728, 0.81712, 0.81567, 0.81563], [0.75788, 0.75938, 0.76081, 0.76217, 0.7642], [0.67523, 0.70124, 0.70455, 0.70246, 0.70173], [0.59419, 0.59735, 0.61648, 0.63894, 0.63863]],
        spin=[[-20.183, -9.481, 1.217, 12.739, 23.981], [-39.248, -19.602, 0.018, 19.56, 38.099], [-50.564, -24.694, 0.513, 25.431, 54.326], [-42.041, -12.935, 14.535, 41.924, 36.839], [18.437, 21.829, 48.343, 15.758, 29.191], [86.407, 116.499, 29.989, 17.103, 33.422]],
        du=[[0.139, 0.07, 0.0, 0.632, 0.986], [0.233, 0.115, 0.0, -0.099, -0.055], [-0.8, -0.436, 0.0, 0.481, -0.96], [-1.137, -0.588, 0.0, 0.59, 0.393], [-2.162, -0.508, 0.0, -1.378, -1.183], [1.07, 1.626, 0.0, 1.42, 1.532]],
        g0=3.036,
        g1=-143.417,
        feed_s=0.106,
    ),
    "juggling": dict(
        V=[1.5, 2.5, 3.5, 5.0, 7.0, 10.0],
        q=[-0.2, -0.1, 0.0, 0.1, 0.2],
        ratio=[[0.98408, 0.9841, 0.98397, 0.98394, 0.98451], [0.94593, 0.94709, 0.94812, 0.94669, 0.94766], [0.87115, 0.87126, 0.87196, 0.86608, 0.87101], [0.80606, 0.8003, 0.79932, 0.79913, 0.79999], [0.75092, 0.75249, 0.74671, 0.74731, 0.74767], [0.70709, 0.70198, 0.70275, 0.70337, 0.70344]],
        spin=[[-4.335, -2.156, 0.018, 2.192, 4.399], [-6.734, -3.129, 0.468, 4.188, 7.754], [-6.834, -2.449, 2.166, 7.331, 11.122], [-11.877, -4.252, 2.088, 8.43, 14.851], [-15.309, -6.559, 3.428, 12.539, 21.656], [-19.394, -5.857, 6.817, 19.473, 32.16]],
        du=[[0.02, 0.005, 0.0, -0.018, -0.034], [0.109, 0.052, 0.0, -0.501, -0.539], [-0.172, 0.013, 0.0, -0.284, -0.316], [0.576, 0.168, 0.0, 0.229, 0.449], [0.372, 0.689, 0.0, 0.325, 0.657], [0.349, -0.296, 0.0, 0.294, 0.577]],
        g0=1.2974,
        g1=34.795,
        feed_s=0.1295,
    ),
    "football": dict(
        V=[5.0, 9.0, 14.0, 20.0, 27.0, 34.0, 42.0, 50.0, 58.0],
        q=[-0.35, -0.2, -0.1, 0.0, 0.1, 0.2, 0.35],
        ratio=[[1.01242, 1.01407, 1.01256, 1.01286, 1.01483, 1.01517, 1.01543], [0.88819, 0.88634, 0.88719, 0.88518, 0.8839, 0.88354, 0.88713], [0.7944, 0.79522, 0.79287, 0.79335, 0.7935, 0.79554, 0.79542], [0.7238, 0.72401, 0.72397, 0.72493, 0.72106, 0.72231, 0.7229], [0.65618, 0.6564, 0.65371, 0.65406, 0.65576, 0.65648, 0.65704], [0.60327, 0.60459, 0.60417, 0.60664, 0.60356, 0.60402, 0.60849], [0.56515, 0.56569, 0.56603, 0.56675, 0.56715, 0.56545, 0.56557], [0.52692, 0.53331, 0.53351, 0.52414, 0.53238, 0.53266, 0.52338], [0.5037, 0.50414, 0.5044, 0.49419, 0.50304, 0.5032, 0.50298]],
        spin=[[-7.09, -4.107, -1.667, 0.553, 2.555, 4.793, 8.112], [-12.396, -6.459, -2.63, 1.015, 4.405, 8.083, 13.956], [-17.108, -9.174, -3.461, 1.403, 6.148, 11.646, 19.677], [-23.514, -13.42, -6.558, 0.465, 9.102, 15.984, 26.36], [-28.086, -15.276, -8.721, -1.378, 12.453, 20.959, 32.445], [-29.467, -14.523, -5.31, -0.275, 17.095, 27.205, 39.937], [-34.561, -17.063, -5.394, 3.399, 13.193, 29.833, 47.24], [-48.875, -25.31, -11.862, 10.251, 15.468, 28.611, 57.933], [-49.058, -27.244, -12.707, 14.047, 18.204, 31.741, 53.192]],
        du=[[-0.474, 0.386, 0.004, 0.0, 0.443, 0.39, 0.471], [0.374, 0.011, -0.429, 0.0, 0.839, 1.042, -0.082], [-0.197, -0.183, -0.796, 0.0, 1.257, 0.635, 0.636], [-0.831, -0.332, -0.377, 0.0, -1.662, -1.456, -1.424], [-1.074, -1.336, -1.02, 0.0, -0.78, -1.117, -1.094], [0.142, -0.142, -0.604, 0.0, 0.634, 0.434, -0.24], [2.021, 1.835, 1.711, 0.0, 1.725, 1.744, 0.846], [2.407, 2.117, 2.095, 0.0, 1.443, 1.899, 1.32], [0.314, 0.468, 0.571, 0.0, -0.396, 0.175, 0.395]],
        g0=0.4902,
        g1=110.057,
        feed_s=0.2113,
    ),
    "volleyball": dict(
        V=[5.0, 8.0, 12.0, 16.0, 21.0, 27.0, 34.0],
        q=[-0.35, -0.2, -0.1, 0.0, 0.1, 0.2, 0.35],
        ratio=[[0.99432, 0.99469, 0.99297, 0.99325, 0.99349, 0.99416, 0.99458], [0.93254, 0.93261, 0.93265, 0.93268, 0.93278, 0.9327, 0.93307], [0.8762, 0.87621, 0.87625, 0.87629, 0.87632, 0.87639, 0.87644], [0.82348, 0.82618, 0.82661, 0.82702, 0.82741, 0.82756, 0.82712], [0.77312, 0.7734, 0.77361, 0.7738, 0.77395, 0.77423, 0.77446], [0.7257, 0.72542, 0.72519, 0.72476, 0.72426, 0.72313, 0.7228], [0.67668, 0.67647, 0.67613, 0.67575, 0.67528, 0.67468, 0.67393]],
        spin=[[-8.18, -4.59, -2.318, 0.08, 2.477, 4.983, 8.6], [-12.955, -7.384, -3.67, 0.044, 3.744, 7.491, 13.134], [-18.183, -10.277, -5.025, 0.227, 5.447, 10.722, 18.767], [-20.701, -11.958, -5.214, 1.53, 8.273, 14.809, 24.301], [-26.753, -14.181, -5.75, 2.683, 11.104, 19.174, 30.343], [-35.667, -20.226, -9.942, 0.319, 10.61, 24.251, 37.901], [-41.796, -23.684, -11.785, 0.092, 11.995, 23.938, 47.401]],
        du=[[-0.521, -0.585, 0.073, 0.0, -0.072, -0.564, -0.77], [0.248, 0.141, 0.07, 0.0, 0.047, -0.001, 0.059], [0.334, 0.194, 0.097, 0.0, 0.229, 0.122, 0.355], [-1.11, 0.323, 0.162, 0.0, -0.162, -0.137, 0.505], [0.975, 0.243, 0.122, 0.0, -0.124, -0.523, -0.677], [0.091, 0.036, 0.004, 0.0, -0.003, -0.202, -1.233], [-0.544, -0.358, -0.182, 0.0, 0.17, 0.322, -0.288]],
        g0=0.557,
        g1=96.301,
        feed_s=0.214,
    ),
}
ACCURACY = {   # measured, azimuth 30 deg, 8 perturbations per launch
    "tennis 30 m/s -2.2 deg spin 42": dict(speed_err_pct=-0.93, dir_err_deg=2.69, spin=87.2, sd_speed_pct=0.78, sd_dir_deg=0.77, sd_spin=16.9, feed_to_exit_s=0.085),
    "tennis 20 m/s 10 deg spin 0": dict(speed_err_pct=1.66, dir_err_deg=1.94, spin=3.8, sd_speed_pct=0.81, sd_dir_deg=0.35, sd_spin=5.5, feed_to_exit_s=0.09),
    "tennis 12 m/s 25 deg spin 0": dict(speed_err_pct=0.3, dir_err_deg=1.41, spin=-0.8, sd_speed_pct=0.6, sd_dir_deg=0.44, sd_spin=1.3, feed_to_exit_s=0.098),
    "tabletennis 5 m/s 5 deg spin -20": dict(speed_err_pct=0.78, dir_err_deg=14.13, spin=-55.9, sd_speed_pct=2.97, sd_dir_deg=4.44, sd_spin=8.6, feed_to_exit_s=0.074),
    "tabletennis 3 m/s 20 deg spin 0": dict(speed_err_pct=-0.94, dir_err_deg=6.81, spin=-3.4, sd_speed_pct=1.82, sd_dir_deg=3.34, sd_spin=1.7, feed_to_exit_s=0.082),
    "baseball 21.35 m/s 45 deg spin 0": dict(speed_err_pct=9.7, dir_err_deg=3.69, spin=-107.2, sd_speed_pct=3.14, sd_dir_deg=0.95, sd_spin=22.8, feed_to_exit_s=0.102),
    "baseball 15 m/s 20 deg spin 0": dict(speed_err_pct=0.54, dir_err_deg=0.44, spin=4.4, sd_speed_pct=0.45, sd_dir_deg=0.62, sd_spin=1.9, feed_to_exit_s=0.105),
    "juggling 2.6 m/s 70 deg spin 0": dict(speed_err_pct=-7.84, dir_err_deg=1.42, spin=-0.1, sd_speed_pct=1.0, sd_dir_deg=1.1, sd_spin=1.0, feed_to_exit_s=0.139),
    "juggling 3.5 m/s 60 deg spin 0": dict(speed_err_pct=-3.81, dir_err_deg=0.92, spin=-2.4, sd_speed_pct=1.72, sd_dir_deg=0.04, sd_spin=2.1, feed_to_exit_s=0.125),
    "football 4.5 m/s 78 deg spin 0": dict(speed_err_pct=-6.77, dir_err_deg=1.13, spin=-0.3, sd_speed_pct=0.47, sd_dir_deg=0.93, sd_spin=0.2, feed_to_exit_s=0.294),
    "football 8 m/s -3 deg spin 15": dict(speed_err_pct=1.58, dir_err_deg=0.9, spin=15.0, sd_speed_pct=0.42, sd_dir_deg=0.28, sd_spin=0.3, feed_to_exit_s=0.228),
    "football 15 m/s 30 deg spin -30": dict(speed_err_pct=-1.08, dir_err_deg=1.82, spin=-27.4, sd_speed_pct=0.31, sd_dir_deg=0.62, sd_spin=1.3, feed_to_exit_s=0.208),
    "football 22 m/s 5 deg spin 0": dict(speed_err_pct=-0.54, dir_err_deg=1.08, spin=2.2, sd_speed_pct=0.25, sd_dir_deg=0.31, sd_spin=0.7, feed_to_exit_s=0.192),
    "football 25 m/s 20 deg spin 0": dict(speed_err_pct=-1.1, dir_err_deg=0.76, spin=1.0, sd_speed_pct=0.59, sd_dir_deg=0.29, sd_spin=3.2, feed_to_exit_s=0.193),
    "football 10 m/s 15 deg spin 0": dict(speed_err_pct=-0.42, dir_err_deg=0.43, spin=-0.2, sd_speed_pct=0.13, sd_dir_deg=0.47, sd_spin=0.2, feed_to_exit_s=0.221),
    "volleyball 14 m/s 25 deg spin 0": dict(speed_err_pct=-0.42, dir_err_deg=0.84, spin=2.0, sd_speed_pct=0.36, sd_dir_deg=0.39, sd_spin=1.0, feed_to_exit_s=0.206),
    "volleyball 9 m/s 60 deg spin 0": dict(speed_err_pct=-1.49, dir_err_deg=0.83, spin=-0.1, sd_speed_pct=0.13, sd_dir_deg=0.14, sd_spin=0.2, feed_to_exit_s=0.227),
    "volleyball 8 m/s 57 deg spin 0": dict(speed_err_pct=-1.99, dir_err_deg=0.67, spin=0.3, sd_speed_pct=0.27, sd_dir_deg=0.22, sd_spin=0.2, feed_to_exit_s=0.234),
    "volleyball 10 m/s 10 deg spin 0": dict(speed_err_pct=0.35, dir_err_deg=0.31, spin=0.6, sd_speed_pct=0.24, sd_dir_deg=0.19, sd_spin=0.3, feed_to_exit_s=0.214),
    "volleyball 12 m/s 5 deg spin 0": dict(speed_err_pct=0.5, dir_err_deg=0.1, spin=0.2, sd_speed_pct=0.3, sd_dir_deg=0.45, sd_spin=0.6, feed_to_exit_s=0.205),
}


def _bm_unit(v):
    v = _bm_np.asarray(v, float)
    return v / _bm_np.linalg.norm(v)


def _bm_mat2quat(R):
    """A rotation matrix (columns: the frame's axes in world coordinates) as a quaternion w x y z."""
    R = _bm_np.asarray(R, float)
    t = R[0, 0] + R[1, 1] + R[2, 2]
    if t > 0:
        s = _bm_math.sqrt(t + 1.0) * 2
        q = (0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s)
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = _bm_math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        q = ((R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s)
    elif R[1, 1] > R[2, 2]:
        s = _bm_math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        q = ((R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s)
    else:
        s = _bm_math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        q = ((R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s)
    q = _bm_np.array(q)
    return q / _bm_np.linalg.norm(q)


def _bm_fmt(v):
    return " ".join(f"{float(x):.6g}" for x in v)


def launch_dir(elevation_deg, azimuth_deg):
    """The unit vector of a launch: azimuth from +x towards +y (counter-clockwise seen from above), elevation above
    the horizontal."""
    e, a = _bm_math.radians(elevation_deg), _bm_math.radians(azimuth_deg)
    return _bm_np.array([_bm_math.cos(e) * _bm_math.cos(a), _bm_math.cos(e) * _bm_math.sin(a), _bm_math.sin(e)])


def _bm_fit_eval(f, V, D):
    """The measured exit speed (m/s), spin across the flight (rad/s) and deflection towards the faster wheel (deg) of
    wheel surface speeds V + D/2 and V - D/2: bilinear in the table FIT[preset] over V and q = D / V (extrapolated
    linearly beyond it)."""
    q = D / max(V, 1e-6)
    Vs, qs = f["V"], f["q"]

    def seg(xs, x):
        k = max(0, min(len(xs) - 2, int(_bm_np.searchsorted(xs, x)) - 1))
        return k, (x - xs[k]) / (xs[k + 1] - xs[k])
    i, s = seg(Vs, V)
    j, t = seg(qs, q)

    def at(T):
        return ((1 - s) * (1 - t) * T[i][j] + s * (1 - t) * T[i + 1][j] + (1 - s) * t * T[i][j + 1]
                + s * t * T[i + 1][j + 1])
    return V * at(f["ratio"]), at(f["spin"]), at(f["du"])


def sag_deg(preset, speed, elevation_deg):
    """The fitted droop of the exit below the head's axis (deg): gravity during the passage, and the feed."""
    f = FIT[preset]
    return f["g0"] + f["g1"] * _bm_math.cos(_bm_math.radians(elevation_deg)) / max(speed, 0.5) ** 2


def solve(preset, speed, spin_rad_s=0.0):
    """The wheels' surface speeds (V + D/2, V - D/2) whose fitted exit speed and spin are the ones asked for, and the
    fitted deflection of the exit from the head's axis (deg, towards wheel 0). spin_rad_s >= 0: wheel 0 is the one on
    the side the spin's surface motion is forward (see BallMachine)."""
    f, r = FIT[preset], PRESETS[preset]["ball_radius_m"]
    V, D = speed / max(f["ratio"][0][len(f["q"]) // 2], 0.3), 0.0
    for _ in range(60):                                   # Newton on the fitted map (smooth, monotone)
        s, w, _ = _bm_fit_eval(f, V, D)
        e1, e2 = s - speed, w - spin_rad_s
        h = 1e-4 * max(V, 1.0)
        s1, w1, _ = _bm_fit_eval(f, V + h, D)
        s2, w2, _ = _bm_fit_eval(f, V, D + h)
        J = _bm_np.array([[(s1 - s) / h, (s2 - s) / h], [(w1 - w) / h, (w2 - w) / h]])
        dV, dD = _bm_np.linalg.solve(J, [-e1, -e2])
        V, D = V + dV, D + dD
        if abs(e1) < 1e-7 and abs(e2) < 1e-7:
            break
    return V + D / 2, V - D / 2, _bm_fit_eval(f, V, D)[2]


def _bm_aim(L, u, du_deg, sag):
    """The head's axis that sends the ball along L: turned away from u by du_deg and up by sag (deg)."""
    z = _bm_np.array([0.0, 0.0, 1.0])
    up = z - L * float(z @ L)
    up = up / _bm_np.linalg.norm(up) if _bm_np.linalg.norm(up) > 1e-6 else u
    return _bm_unit(L - _bm_math.tan(_bm_math.radians(du_deg)) * u + _bm_math.tan(_bm_math.radians(sag)) * up)


class BallMachine:
    """A two-wheel ball machine at a fixed pose in the venue.

    name     prefix of every body, joint, actuator and geom it adds
    preset   a PRESETS key (the wheels, motors, contact)
    exit     the nip's centre in the world (where the ball leaves the wheels)
    speed_m_s, elevation_deg, azimuth_deg: the launch asked for; spin: the spin asked for (world rad/s, a vector)
    ball     the name of the free ball it throws (the family creates it with Scene.ball at rest_pos())
    rim      optional (v0, v1) wheel surface speeds overriding the fit (m/s); deflect_deg optional override
    The head's axis is the launch direction turned by the fitted deflection; the wheel pair is turned about it so that
    the spin's axis (its part across the flight) comes from the speed difference. With no spin the wheels are one
    above the other.

    The feed: the ball lies in the throat, a cradle of two rails along the head's axis behind the wheels (the rails
    run on past the treads, beside them), between a gate in front (a plate on a slide across the axis) and the feed
    ram behind (a plate on a slide along the axis). feed(t): at t the gate opens; ram_delay_s later the ram, a
    force-limited position servo (ram_force_n, its speed limited by the slide's damping to about ram_speed_m_s),
    pushes the ball into the wheels, which take it. The cradle along the axis works at any elevation from -30 to
    +80 degrees (on a rising axis the ball rests on the ram). One ball per machine load; a family that throws several
    balls builds several machines (or loads one per attempt)."""

    def __init__(self, name, preset, exit, speed_m_s, elevation_deg, azimuth_deg, spin=(0.0, 0.0, 0.0),
                 ball="ball", rim=None, deflect_deg=None, gate_force_n=20.0, ram_force_n=None, ram_speed_m_s=1.5,
                 ram_delay_s=0.03, base=True, overrides=None, pair="auto"):
        self.name, self.preset = name, preset
        self.P = dict(PRESETS[preset], **(overrides or {}))
        P = self.P
        self.ball = ball
        self.balls = [ball]
        self.N = _bm_np.asarray(exit, float)
        self.speed = float(speed_m_s)
        L = launch_dir(elevation_deg, azimuth_deg)
        w = _bm_np.asarray(spin, float)
        w_perp = w - L * float(w @ L)
        self.spin_gyro = float(w @ L)                     # not made by two wheels (reported)
        Om = float(_bm_np.linalg.norm(w_perp))
        R_, h_ = P["wheel_radius_m"], P["wheel_radius_m"] + (2 * P["ball_radius_m"] - P["squeeze_m"]) / 2
        if Om > 1e-6:
            u = _bm_np.cross(L, w_perp / Om)              # spin = Om (u x L): wheel 0 on +u is the faster one
        else:
            hz = _bm_np.array([0.0, 0.0, 1.0])
            u = hz - L * float(hz @ L)
            u = u / _bm_np.linalg.norm(u) if _bm_np.linalg.norm(u) > 1e-6 else _bm_np.array([1.0, 0.0, 0.0])
            # no spin asked: the wheels one above the other ("stacked"), or side by side ("side"; "auto": side by
            # side when stacked wheels would not clear the floor by 2 cm)
            if pair == "side" or (pair == "auto" and float(exit[2]) - h_ * abs(float(u[2])) - R_ < 0.02):
                s_ = _bm_np.cross(_bm_np.array([0.0, 0.0, 1.0]), L)
                if _bm_np.linalg.norm(s_) > 1e-6:
                    u = s_ / _bm_np.linalg.norm(s_)
        self.Om = Om
        if rim is None:
            v0, v1, du = solve(preset, self.speed, Om)
        else:
            v0, v1 = rim
            du = 0.0
        sag = sag_deg(preset, self.speed, elevation_deg) if rim is None else 0.0
        if deflect_deg is not None:
            du, sag = deflect_deg, 0.0
        self.rim = (float(v0), float(v1))
        self.sag = sag
        Lh = _bm_aim(L, u, du, sag)                       # the head's axis
        uh = _bm_unit(u - Lh * float(u @ Lh))
        self.L, self.uh = Lh, uh
        self.a = _bm_np.cross(Lh, uh)                    # the wheels' axis direction (wheel 0 turns about +a)
        self.L_target = L
        self.deflect_deg = du
        self.gate_force = gate_force_n
        self.ram_force = ram_force_n if ram_force_n is not None else max(20.0, 100.0 * P["ball_mass_kg"])
        self.ram_speed, self.ram_delay = ram_speed_m_s, ram_delay_s
        self.base = base
        self.feed_t = None                                # control time of the feed (gate opens; the ram follows)
        rb, R = P["ball_radius_m"], P["wheel_radius_m"]
        h = R + (2 * rb - P["squeeze_m"]) / 2             # wheel centre from the nip's centre
        x0 = _bm_math.sqrt(max((R + rb) ** 2 - h * h, 0.0))  # the ball's centre where it first touches both wheels
        self.h, self.x_touch = h, x0
        self.x_rest = -(x0 + 1.5 * rb)                     # the ball's centre at rest, along the axis from the nip
        self.stroke = (-x0 + 0.3 * rb) - self.x_rest       # the ram pushes it 0.3 radii into the grip
        self.rest = [self.N + self.x_rest * Lh]
        diag = [(sa * self.a + su * self.uh) / _bm_math.sqrt(2) for sa in (1, -1) for su in (1, -1)]
        diag.sort(key=lambda v: float(v[2]))
        self.rails_dir = [_bm_unit(diag[0]), _bm_unit(diag[1])]   # the two lowest diagonals: the cradle's rails

    def rest_pos(self, k=0):
        """Where the ball's centre rests at t = 0 (in the cradle, between gate and ram)."""
        return tuple(float(x) for x in self.rest[0])

    def build(self, sc, rgba=(0.25, 0.27, 0.30, 1)):
        """Add the machine to a rfo.scene.Scene: wheels (hinges, velocity motors), cradle rails, gate, ram, shroud,
        base; the ball-wheel pairs and exclusions (the ball itself: the family's, at rest_pos())."""
        P, nm, L = self.P, self.name, self.L
        rb, R, hw = P["ball_radius_m"], P["wheel_radius_m"], P["wheel_half_width_m"]
        if hw > 0.62 * rb:
            raise ValueError("ball machine: the treads must be narrower than 1.24 ball radii (the rails pass them)")
        HIT = dict(contype="1", conaffinity="13")
        self.rail_r = max(0.003, 0.15 * rb)
        root = sc.root
        # the calibration's contact options: elliptic friction cones and impratio 100 (as in every world with a real
        # hand; set here if the family has not set them; a family that set others gets an error, not a silent change)
        opt = root.find("option")
        if opt.get("cone", "elliptic") != "elliptic" or float(opt.get("impratio", "100")) != 100.0:
            raise ValueError("ball machine: calibrated with cone='elliptic', impratio=100; the scene sets "
                             f"cone={opt.get('cone')!r}, impratio={opt.get('impratio')!r}")
        opt.set("cone", "elliptic")
        opt.set("impratio", "100")
        # the floor: every wheel and the cradle at least 2 cm above it
        low = min(float(self.N[2] + s * self.h * self.uh[2]) - R * _bm_math.sqrt(max(0.0, 1 - float(self.a[2]) ** 2))
                  - hw * abs(float(self.a[2])) for s in (1, -1))
        low = min(low, float(self.N[2] + self.x_rest * L[2]) - 1.3 * rb)
        if low < 0.02:
            raise ValueError(f"ball machine {nm!r}: its head reaches {low:.3f} m above the floor (at least 0.02 m): "
                             f"raise the exit by {0.02 - low:.3f} m, or ask for no spin (the wheels then go side by side)")
        act, contact = root.find("actuator"), root.find("contact")
        mach = sc.body(nm, (0, 0, 0))
        self.wheel_names = []
        for k, s in ((0, 1.0), (1, -1.0)):
            c = self.N + s * self.h * self.uh
            wn = f"{nm}_wheel{k}"
            b = sc.body(wn, tuple(c), parent=mach)
            ax = s * self.a
            m = P["wheel_mass_kg"]
            Ia, Ip = 0.5 * m * R * R, 0.25 * m * R * R + m * (2 * hw) ** 2 / 12
            I = Ip * _bm_np.eye(3) + (Ia - Ip) * _bm_np.outer(ax, ax)
            _bm_ET.SubElement(b, "inertial", pos="0 0 0", mass=f"{m:.6g}",
                              fullinertia=_bm_fmt((I[0, 0], I[1, 1], I[2, 2], I[0, 1], I[0, 2], I[1, 2])))
            _bm_ET.SubElement(b, "joint", name=wn, type="hinge", axis=_bm_fmt(ax), damping="1e-05",
                              armature=f"{0.2 * Ia:.6g}")
            sc.geom(b, wn, type="cylinder", fromto=tuple(-hw * ax) + tuple(hw * ax), size=(R,), mass=0,
                    rgba=(0.12, 0.12, 0.13, 1), friction=(P["tread_mu"], 0.005, 0.0001), **HIT)
            sc.geom(b, f"{wn}_hub", type="box", pos=tuple(0.6 * R * L), size=(0.2 * R, 0.2 * R, hw * 1.02),
                    quat=tuple(_bm_mat2quat(_bm_np.c_[L, s * self.uh, ax])),
                    rgba=(0.85, 0.85, 0.2, 1), mass=0, contype="0", conaffinity="0")
            _bm_ET.SubElement(act, "velocity", name=wn, joint=wn, kv=f"{P['motor_kv']:.6g}", forcelimited="true",
                              forcerange=f"{-P['motor_torque_n_m']:.6g} {P['motor_torque_n_m']:.6g}")
            _bm_ET.SubElement(contact, "exclude", body1=nm, body2=wn)    # (the frame does not touch its wheels)
            self.wheel_names.append(wn)
        # the ball-wheel contact: an explicit pair per wheel (the ball's own contact with the wheels excluded)
        e = min(max(P["contact_e"], 0.02), 0.98)
        ln = _bm_math.log(e)
        zeta = -ln / _bm_math.sqrt(_bm_math.pi ** 2 + ln ** 2)
        # MuJoCo's soft contact (direct solref -k -b, impedance d = 0.5 at solimp "0.5 0.5") squeezed to a depth r
        # (the ball is held between two surfaces, so its acceleration along the normal is about zero) pushes with
        # f = m d / (1 - d) (k r + b v): k and b are set so that this is the ball's own spring-damper, f = K r + C v,
        # K = contact_k_n_m, C = 2 zeta sqrt(K m) with zeta from contact_e (measured: the static force is K r within
        # 1 %). (d = 0.5: k, b are then the spring and damper per unit mass in an impact too; a high impedance with
        # the stiff friction of a real-hand world made MuJoCo's solver inflate a slipping contact's normal force.)
        m_b, K, dd = P["ball_mass_kg"], P["contact_k_n_m"], 0.5
        C = 2 * zeta * _bm_math.sqrt(K * m_b)
        g = (1 - dd) / (dd * m_b)
        self.solref = f"{-K * g:.6g} {-C * g:.6g}"
        for wn in self.wheel_names:
            _bm_ET.SubElement(contact, "exclude", body1=self.ball, body2=wn)
            _bm_ET.SubElement(contact, "pair", name=f"{self.ball}_{wn}", geom1=self.ball, geom2=wn, condim="3",
                              friction=f"{P['tread_mu']:.6g} {P['tread_mu']:.6g} 0.005 0.0001 0.0001",
                              solref=self.solref, solimp="0.5 0.5 0.001")
        # the head's shroud (drawn) round the wheels
        sc.geom(mach, f"{nm}_shroud", type="box", pos=tuple(self.N), size=(R + 0.02, self.h + R + 0.02, hw + 0.02),
                rgba=(rgba[0], rgba[1], rgba[2], 0.35), quat=tuple(_bm_mat2quat(_bm_np.c_[L, self.uh, self.a])),
                contype="0", conaffinity="0")
        # the cradle: two steel rails along the axis, from behind the ram to beyond the wheels (priority 2, condim 3:
        # the ball rolls on them without the rolling and torsional resistance of a court)
        c = rb + self.rail_r
        x_back = self.x_rest - rb - 0.03
        p0, p1 = self.N + x_back * L, self.N.copy()            # (they end at the nip: the ball leaves free)
        for j in range(2):
            sc.geom(mach, f"{nm}_rail{j}", type="capsule", fromto=tuple(p0 + c * self.rails_dir[j]) + tuple(p1 + c * self.rails_dir[j]),
                    size=(self.rail_r,), rgba=(0.6, 0.62, 0.65, 1), friction=(0.3, 0.0, 0.0), condim=3, priority=2, **HIT)
        frame = _bm_np.c_[L, self.uh, self.a]
        q = tuple(_bm_mat2quat(frame))
        # the gate: a plate across the axis in front of the ball, sliding along the wheels' axis direction (a) out of
        # the way; force-limited position servo, 0 = closed
        self.gate_open = 2.6 * rb
        gn = f"{nm}_gate"
        b = sc.body(gn, tuple(self.N + (self.x_rest + rb + 0.004) * L), parent=mach)
        _bm_ET.SubElement(b, "joint", name=gn, type="slide", axis=_bm_fmt(self.a), range=f"0 {self.gate_open + 0.01:.6g}",
                          damping="2", armature="0.01")
        sc.geom(b, gn, type="box", size=(0.003, 1.1 * rb, 1.1 * rb), quat=q, mass=0.03, rgba=(0.85, 0.25, 0.2, 1),
                friction=(0.3, 0.0, 0.0), condim=3, priority=2, **HIT)     # (a dead stop: no rattle)
        _bm_ET.SubElement(act, "position", name=gn, joint=gn, kp=f"{20 * self.gate_force / self.gate_open:.6g}",
                          forcelimited="true", forcerange=f"{-self.gate_force:.6g} {self.gate_force:.6g}",
                          ctrllimited="true", ctrlrange=f"0 {self.gate_open:.6g}")
        _bm_ET.SubElement(contact, "exclude", body1=nm, body2=gn)
        # the ram: a plate behind the ball on a slide along the axis; its servo saturates at ram_force, the slide's
        # damping limits its speed to about ram_speed
        rn = f"{nm}_ram"
        b = sc.body(rn, tuple(self.N + (self.x_rest - rb - 0.004) * L), parent=mach)
        _bm_ET.SubElement(b, "joint", name=rn, type="slide", axis=_bm_fmt(L), range=f"0 {self.stroke + 0.005:.6g}",
                          damping=f"{self.ram_force / self.ram_speed:.6g}", armature="0.02")
        sc.geom(b, rn, type="box", size=(0.003, 0.7 * rb, 0.7 * rb), quat=q, mass=0.05, rgba=(0.2, 0.45, 0.85, 1),
                friction=(0.3, 0.0, 0.0), condim=3, priority=2, **HIT)
        sc.geom(b, f"{rn}_rod", type="cylinder", fromto=tuple(-0.004 * L) + tuple(-0.15 * L), size=(0.006,), mass=0.01,
                rgba=(0.6, 0.62, 0.65, 1), contype="0", conaffinity="0")
        _bm_ET.SubElement(act, "position", name=rn, joint=rn, kp=f"{50 * self.ram_force / self.stroke:.6g}",
                          forcelimited="true", forcerange=f"{-self.ram_force:.6g} {self.ram_force:.6g}",
                          ctrllimited="true", ctrlrange=f"0 {self.stroke:.6g}")
        _bm_ET.SubElement(contact, "exclude", body1=nm, body2=rn)
        _bm_ET.SubElement(contact, "exclude", body1=gn, body2=rn)
        for wn in self.wheel_names:
            _bm_ET.SubElement(contact, "exclude", body1=rn, body2=wn)   # (the ram's plate stops short of the treads)
        self.gate_names, self.ram_name = [gn], rn
        # the base: a column from the floor to under the head (solid)
        if self.base:
            lo = float(self.N[2]) - (self.h + R) - 0.05
            if lo > 0.05:
                cx = self.N - 0.5 * R * L
                sc.geom(mach, f"{nm}_column", type="box", pos=(float(cx[0]), float(cx[1]), lo / 2),
                        size=(0.04, 0.04, lo / 2), rgba=rgba, **HIT)
                sc.geom(mach, f"{nm}_foot", type="box", pos=(float(cx[0]), float(cx[1]), 0.01), size=(0.25, 0.25, 0.01),
                        rgba=rgba, **HIT)

    # ------------------------------------------------------------------ running
    def reset(self, w):
        """The machine is running at t = 0 (switched on before the attempt): the wheels at their set speeds."""
        m, d = w.m, w.d
        self.jid = [m.joint(n).id for n in self.wheel_names]
        self.aid = [m.actuator(n).id for n in self.wheel_names]
        self.gid = m.actuator(self.gate_names[0]).id
        self.rid = m.actuator(self.ram_name).id
        R = self.P["wheel_radius_m"]
        self.omega = [v / R for v in self.rim]
        for j, om in zip(self.jid, self.omega):
            d.qvel[m.jnt_dofadr[j]] = om
        self.write(w, 0.0)

    def feed(self, t):
        """Feed the ball at control time t (the gate opens; the ram pushes ram_delay_s later)."""
        self.feed_t = t

    def schedule(self, k, t):                             # (calibrate's name for feed)
        self.feed(t)

    def write(self, w, t):
        """The machine's controller (call every control step, e.g. from before_step, with w.t): wheel speed
        setpoints, the gate and the ram."""
        d = w.d
        for a, om in zip(self.aid, self.omega):
            d.ctrl[a] = om
        f = self.feed_t
        d.ctrl[self.gid] = self.gate_open if (f is not None and t >= f - 1e-9) else 0.0
        d.ctrl[self.rid] = self.stroke if (f is not None and t >= f + self.ram_delay - 1e-9) else 0.0

    def wheel_speeds(self, w):
        """The wheels' surface speeds now (m/s)."""
        R = self.P["wheel_radius_m"]
        return [float(w.d.qvel[w.m.jnt_dofadr[j]]) * R for j in self.jid]

    def past_wheels(self, pos):
        """Has a ball at pos just left the wheels: its centre a wheel radius beyond the nip along the head's axis, and
        still in front of the machine's mouth (within 0.5 m beyond that and a wheel radius of the axis; a ball
        elsewhere has not come out of this machine)?"""
        r = _bm_np.asarray(pos) - self.N
        x = float(r @ self.L)
        lat = float(_bm_np.linalg.norm(r - x * self.L))
        x0 = self.P["wheel_radius_m"] + self.P["ball_radius_m"]
        return x0 < x < x0 + 0.5 and lat < self.P["wheel_radius_m"]

    def facts(self):
        """The machine's numbers, for a family's texts and privileged state."""
        P = self.P
        return {"preset": self.preset, "exit": [round(float(x), 4) for x in self.N],
                "axis": [round(float(x), 5) for x in self.L], "wheel_axis": [round(float(x), 5) for x in self.a],
                "wheel_surface_speeds_m_s": [round(v, 4) for v in self.rim], "wheel_radius_m": P["wheel_radius_m"],
                "gap_m": round(2 * P["ball_radius_m"] - P["squeeze_m"], 4), "motor_torque_n_m": P["motor_torque_n_m"],
                "gate_force_n": self.gate_force, "ram_force_n": round(self.ram_force, 2),
                "rest": [round(float(x), 4) for x in self.rest[0]], "spin_gyro_not_made_rad_s": round(self.spin_gyro, 3)}


class Dropper:
    """A ball dropper: the ball rests in a cup (a ring round it, two trapdoor leaves under it) on a carriage at the end
    of an arm. At open_t the leaves slide apart (force-limited position servos) and the ball falls from rest, by
    gravity alone (no speed, no spin); retract_s later the carriage, on a slide along `retract` (a unit vector, the
    arm's direction) driven by a force-limited servo, pulls the cup retract_m back out of the ball's way. centre: the
    ball's centre at rest (world). The arm's column stands on the floor at the carriage's retracted end plus 0.1 m."""

    def __init__(self, name, centre, ball_radius_m, ball="ball", leaf_force_n=10.0, retract=(1.0, 0.0, 0.0),
                 retract_m=0.35, retract_s=0.15, carriage_force_n=30.0, arm_offset_m=0.12):
        self.name, self.c, self.rb, self.ball = name, _bm_np.asarray(centre, float), ball_radius_m, ball
        self.force, self.cforce = leaf_force_n, carriage_force_n
        self.dir = _bm_unit(retract)
        self.retract_m, self.retract_s = retract_m, retract_s
        self.arm_off = arm_offset_m                     # the arm starts this far from the ball (a bracket to the cup)
        self.open_t = None

    def rest_pos(self):
        return tuple(float(x) for x in self.c)

    def build(self, sc, rgba=(0.25, 0.27, 0.30, 1)):
        nm, rb, c, u = self.name, self.rb, self.c, self.dir
        HIT = dict(contype="1", conaffinity="13")
        act, contact = sc.root.find("actuator"), sc.root.find("contact")
        side = _bm_unit(_bm_np.cross([0.0, 0.0, 1.0], u))
        frame = sc.body(nm, (0, 0, 0))                    # the fixed part: column and arm
        zarm = c[2] + 0.3 * rb + 0.012                    # the arm runs above the cup's rim
        far = c + u * (self.retract_m + self.arm_off + 0.1)
        sc.geom(frame, f"{nm}_arm", type="capsule", fromto=(c[0] + u[0] * self.arm_off, c[1] + u[1] * self.arm_off, zarm,
                                                            far[0], far[1], zarm), size=(0.008,), rgba=rgba, **HIT)
        sc.geom(frame, f"{nm}_column", type="cylinder", pos=(far[0], far[1], zarm / 2), size=(0.015, zarm / 2),
                rgba=rgba, **HIT)
        car = sc.body(f"{nm}_carriage", tuple(c), parent=frame)
        _bm_ET.SubElement(car, "joint", name=f"{nm}_carriage", type="slide", axis=_bm_fmt(u),
                          range=f"0 {self.retract_m + 0.01:.6g}", damping=f"{self.cforce / 1.5:.6g}", armature="0.05")
        _bm_ET.SubElement(car, "inertial", pos="0 0 0", mass="0.15", diaginertia="1e-4 1e-4 1e-4")
        _bm_ET.SubElement(act, "position", name=f"{nm}_carriage", joint=f"{nm}_carriage",
                          kp=f"{20 * self.cforce / self.retract_m:.6g}", forcelimited="true",
                          forcerange=f"{-self.cforce:.6g} {self.cforce:.6g}", ctrllimited="true",
                          ctrlrange=f"0 {self.retract_m:.6g}")
        _bm_ET.SubElement(contact, "exclude", body1=nm, body2=f"{nm}_carriage")
        n, rr = 8, rb + 0.008                              # the ring, 8 mm clear of the ball, at its lower half
        for k in range(n):
            a0, a1 = 2 * _bm_math.pi * k / n, 2 * _bm_math.pi * (k + 1) / n
            p0 = (rr * _bm_math.cos(a0), rr * _bm_math.sin(a0), -0.3 * rb)
            p1 = (rr * _bm_math.cos(a1), rr * _bm_math.sin(a1), -0.3 * rb)
            sc.geom(car, f"{nm}_ring{k}", type="capsule", fromto=p0 + p1, size=(0.002,), rgba=rgba, **HIT)
        sc.geom(car, f"{nm}_bracket", type="capsule", fromto=((rr + 0.004) * u[0], (rr + 0.004) * u[1], -0.3 * rb,
                                                             self.arm_off * u[0], self.arm_off * u[1], -0.3 * rb),
                size=(0.004,), rgba=rgba, **HIT)
        sc.geom(car, f"{nm}_post", type="capsule", fromto=(self.arm_off * u[0], self.arm_off * u[1], -0.3 * rb,
                                                          self.arm_off * u[0], self.arm_off * u[1], zarm - c[2]),
                size=(0.004,), rgba=rgba, **HIT)
        zt = -rb                                           # the leaves' top face, under the ball (touching it)
        self.travel = 1.6 * rb
        self.leaf_names = []
        for k, s in ((0, 1.0), (1, -1.0)):
            ln = f"{nm}_leaf{k}"
            b = sc.body(ln, tuple(s * 0.6 * rb * side + _bm_np.array([0, 0, zt - 0.002])), parent=car)
            _bm_ET.SubElement(b, "joint", name=ln, type="slide", axis=_bm_fmt(s * side),
                              range=f"0 {self.travel + 0.005:.6g}", damping=f"{self.force / 0.5:.6g}", armature="0.005")
            # (the leaves open at about 0.5 m/s; PTFE-faced, friction 0.1: PTFE on plastics 0.05-0.1)
            sc.geom(b, ln, type="box", size=(1.2 * rb, 0.6 * rb, 0.002), mass=0.02, rgba=(0.85, 0.25, 0.2, 1),
                    quat=tuple(_bm_mat2quat(_bm_np.c_[u, side, [0.0, 0.0, 1.0]])), friction=(0.1, 0.005, 0.0001),
                    priority=2, **HIT)
            _bm_ET.SubElement(act, "position", name=ln, joint=ln, kp=f"{20 * self.force / self.travel:.6g}",
                              forcelimited="true", forcerange=f"{-self.force:.6g} {self.force:.6g}",
                              ctrllimited="true", ctrlrange=f"0 {self.travel:.6g}")
            _bm_ET.SubElement(contact, "exclude", body1=f"{nm}_carriage", body2=ln)
            _bm_ET.SubElement(contact, "exclude", body1=nm, body2=ln)
            self.leaf_names.append(ln)

    def reset(self, w):
        self.aid = [w.m.actuator(n).id for n in self.leaf_names]
        self.cid = w.m.actuator(f"{self.name}_carriage").id
        self.write(w, 0.0)

    def write(self, w, t):
        """The dropper's controller: call every control step (before_step) with w.t."""
        op = self.open_t is not None and t >= self.open_t - 1e-9
        for a in self.aid:
            w.d.ctrl[a] = self.travel if op else 0.0
        back = self.open_t is not None and t >= self.open_t + self.retract_s - 1e-9
        w.d.ctrl[self.cid] = self.retract_m if back else 0.0


# ----------------------------------------------------------------------------- calibration (standalone, no robot)
class _BMWorld:
    """The bare minimum a BallMachine needs of a World (m, d) for calibrate()."""

    def __init__(self, m, d):
        self.m, self.d = m, d


def standalone(machine, ball_kw=None, real_hand_options=True):
    """A venue with only the floor, air and this machine with its balls (rfo.scene.Scene), the same options as a
    family world (1 ms, implicitfast; with a real hand: elliptic cones, impratio 100). Returns (m, d, world)."""
    import mujoco
    from rfo.scene import Scene
    sc = Scene()
    machine.build(sc)
    P = machine.P
    for k, b in enumerate(machine.balls):
        kw = dict(radius=P["ball_radius_m"], mass=P["ball_mass_kg"])
        kw.update(ball_kw or {})
        kind = kw.pop("kind", "tennis")
        sc.ball(b, kind, machine.rest_pos(), **kw)
    if real_hand_options:
        opt = sc.root.find("option")
        opt.set("cone", "elliptic")
        opt.set("impratio", "100")
    m = mujoco.MjModel.from_xml_string(_bm_ET.tostring(sc.root, encoding="unicode"))
    d = mujoco.MjData(m)
    w = _BMWorld(m, d)
    mujoco.mj_forward(m, d)
    machine.reset(w)
    return m, d, w


def shoot(machine, ball_kw=None, open_at=0.1, t_max=4.0, k=0, real_hand_options=True, settle=None):
    """One shot of ball k in a standalone world: the exit state when its centre is past the wheels (world frame:
    position, velocity, spin), the time from the gate's opening, the wheels' surface speeds before and the dip."""
    import mujoco
    m, d, w = standalone(machine, ball_kw, real_hand_options)
    machine.schedule(k, open_at)
    bid = m.body(machine.balls[k]).id
    ja = m.jnt_dofadr[m.body_jntadr[bid]]
    t, dip = 0.0, [1e9, 1e9]
    while d.time < t_max:
        if abs(d.time / 0.01 - round(d.time / 0.01)) < 1e-6:
            machine.write(w, d.time)
        mujoco.mj_step(m, d)
        ws = machine.wheel_speeds(w)
        dip = [min(a, b) for a, b in zip(dip, ws)]
        p = d.xpos[bid]
        if machine.past_wheels(p):
            Rm = d.xmat[bid].reshape(3, 3)
            return dict(t=d.time - open_at, pos=p.copy(), vel=d.qvel[ja:ja + 3].copy(), spin=Rm @ d.qvel[ja + 3:ja + 6],
                        rim_dip=[a - b for a, b in zip(machine.rim, dip)])
    return None


def analyse(machine, shot):
    """Exit speed, spin across the flight (about u x L, the sign as asked), and the deflection (deg) from the head's
    axis towards wheel 0 (u) and along the wheels' axis (a)."""
    v = shot["vel"]
    sp = float(_bm_np.linalg.norm(v))
    vh = v / sp
    du = _bm_math.degrees(_bm_math.atan2(float(vh @ machine.uh), float(vh @ machine.L)))
    da = _bm_math.degrees(_bm_math.atan2(float(vh @ machine.a), float(vh @ machine.L)))
    spin = float(shot["spin"] @ _bm_np.cross(machine.uh, machine.L))
    return sp, spin, du, da


def calibrate(preset, speeds, qs=(-0.2, -0.1, 0.0, 0.1, 0.2), ball_kw=None):
    """Measure the exit over a grid of mean surface speeds V and relative differences q = D / V (elevation 20 deg),
    plus D = 0 at elevations -5 and 60 deg, and fit FIT's model by least squares. Returns (fit, rows); rows: (V, D,
    elevation, speed, spin, deflection towards wheel 0, deflection along the axis, feed time)."""
    rows = []
    for el, qq in ((20.0, qs), (-5.0, (0.0,)), (60.0, (0.0,))):
        for V in speeds:
            for q in qq:
                D = q * V
                bm = BallMachine("cal", preset, (0, 0, 1.5), V, el, 0.0, rim=(V + D / 2, V - D / 2), deflect_deg=0.0,
                                 base=False)
                s = shoot(bm, ball_kw)
                if s is not None:
                    rows.append((V, D, el) + analyse(bm, s) + (s["t"],))
    lst = _bm_np.linalg.lstsq
    tab = {(r[0], round(r[1] / r[0], 6)): r for r in rows if r[2] == 20.0}
    Vs, qq = sorted(set(k[0] for k in tab)), sorted(set(k[1] for k in tab))
    T = {n: [[tab[(V, q)][c] / (V if n == "ratio" else 1.0) for q in qq] for V in Vs]
         for n, c in (("ratio", 3), ("spin", 4), ("du", 5))}
    z = [r for r in rows if abs(r[1]) <= 1e-9]                 # no spin: u is "up", the deflection is the droop
    g = lst(_bm_np.array([[1.0, _bm_math.cos(_bm_math.radians(r[2])) / r[3] ** 2] for r in z]),
            _bm_np.array([-r[5] for r in z]), rcond=None)[0]
    du0 = {V: tab[(V, 0.0)][5] for V in Vs}                     # the table's du: the spin's part (droop removed)
    T["du"] = [[T["du"][a][b] - du0[V] for b, q in enumerate(qq)] for a, V in enumerate(Vs)]
    fit = dict(V=[float(v) for v in Vs], q=[float(q) for q in qq],
               ratio=[[round(float(x), 5) for x in row] for row in T["ratio"]],
               spin=[[round(float(x), 3) for x in row] for row in T["spin"]],
               du=[[round(float(x), 3) for x in row] for row in T["du"]],
               g0=round(float(g[0]), 4), g1=round(float(g[1]), 3), feed_s=round(float(_bm_np.mean([r[7] for r in rows])), 4))
    return fit, rows
# ===================================================================================== (end of the ball machine block)

BALL = OFFICIAL["tabletennis"]

# ------------------------------------------------------------------------------- the free paddle (ITTF Law 2.4)
# A free body "paddle" in its own frame: the butt at the origin, +z along the handle to the blade's far edge, the
# blade's faces look along the body's +-x (the handle's thickness is along x, its width along y). Shared, identically,
# by paddle-bounce and table-tennis-return.
FREE_PADDLE = dict(blade_m=0.15, blade_thickness_m=0.015, blade_kg=0.09, blade_centre_from_butt_m=0.175,
                   handle_length_m=0.10, handle_width_m=0.032, handle_thickness_m=0.025, handle_kg=0.05, mass_kg=0.14,
                   handle_friction=0.8)


def build_free_paddle(sc, pos, quat=(1, 0, 0, 0), name="paddle"):
    """The paddle as a free body at pos/quat (its butt). Geoms <name>_handle (a box) and <name>_blade (a box), both
    colliding like a prop (HITTABLE): with the hands, the robot, the floor, the table, the net, the ball."""
    P = FREE_PADDLE
    b = sc.body(name, pos, quat=quat, free=True)
    L = P["handle_length_m"]
    sc.geom(b, f"{name}_handle", type="box", pos=(0, 0, L / 2),
            size=(P["handle_thickness_m"] / 2, P["handle_width_m"] / 2, L / 2), mass=P["handle_kg"],
            rgba=(0.55, 0.38, 0.2, 1), friction=(P["handle_friction"], 0.005, 0.0001), **HITTABLE, **RIGID)
    B = P["blade_m"] / 2
    sc.geom(b, f"{name}_blade", type="box", pos=(0, 0, P["blade_centre_from_butt_m"]),
            size=(P["blade_thickness_m"] / 2, B, B), mass=P["blade_kg"], rgba=(0.8, 0.1, 0.1, 1), **HITTABLE, **RIGID)
    return b
# ------------------------------------------------------------------------------- (end of the shared paddle)


BLADE_PAIR = dict(solref="-600000 -12", friction="0.8 0.8 0.005 0.0001 0.0001", solimp="0.98 0.99 0.001 0.5 2",
                  solreffriction="-0.0 -200.0")
SIDE = "right"
# where the handle sits in the hand (the grasp frame, rfo.realhand: x out of the palm, z along the fingers, y = z x x,
# on the right hand towards the index finger): the handle's axis along y, the butt butt_out_m before the grasp centre,
# the handle's centre palm_off_m out of the palm and finger_off_m along the fingers from it (a search for the hold)
GRIP = dict(butt_out_m=0.05, palm_off_m=0.005, finger_off_m=0.0)

EARLY = "the ball was touched before it was dropped"
OTHER = "the ball touched something other than the paddle's blade"
FLOOR = "the ball touched the floor"
LOW = "the ball came back to the blade without having risen enough"
REST = "the ball rested on the blade"
LEFT_HAND = "the paddle left your hand"
HELD_ELSE = "the paddle touched a part of you other than your right hand"
PADDLE_FLOOR = "the paddle touched the floor"


class Task(TaskBase):
    name = "paddle-bounce"
    title = "Table tennis: keep the ball bouncing on a paddle"
    category = "basketball-and-rackets"
    robot = "unitree_g1"
    rulebook = ("ITTF Handbook 2024, The Laws of Table Tennis, for the equipment: 2.3 (the ball), 2.4 (the racket), "
                "2.5.5 (the racket hand: the hand carrying the racket). Bouncing the ball on the racket is a "
                "ball-control drill, not an event with a rule book: the number of consecutive bounces asked for is "
                "this benchmark's line")
    deviations = [
        "2.4 (the racket): the blade is a rigid 15 cm square, 1.5 cm thick, on a straight handle {handle_length_m} m "
        "long, {handle_width_m} m wide and {handle_thickness_m} m thick, {paddle_mass_kg} kg in all (legal: the Laws "
        "set no size, shape or weight); its covering is one contact law on both faces (Embodied Olympics' ball-paddle pair, "
        "hand-picked, not identified)",
        "2.5.5 (the hand carrying the racket): the hand is the G1's own Dex3-1 three-finger hand (a thumb, an index "
        "and a middle finger, at the device's joint torques), closed round the handle in a shakehand grip; the paddle "
        "is held by contact and friction alone; \"in the hand\" is defined by contact: the handle touches the hand's "
        "fingers and its thumb or palm, and a break of up to {out_of_hand_s} s is not a release",
        "the start: nobody drops the ball for the robot; a machine does: the ball rests in the cup of a dropper on an "
        "arm in front of the robot, whose two trapdoor leaves slide apart at {drop_time_s} s (the ball falls from "
        "rest); {retract_after_s} s later the cup pulls {retract_m} m back along the arm, away from the robot",
        "a bounce is a hit: so that the rebounds of one strong hit off a still blade are not counted, the ball must "
        "leave a counted bounce with at least {hit_gain} of the speed it reached the blade with (both taken at the "
        "height of the touch; a still blade returns about 0.95); a bounce that does not is not counted, and is not "
        "a fault",
    ]
    time_limit_s = 20.0
    start = (0.0, 0.0, 0.0)
    stages = [f"bounce {i + 1}" for i in range(20)]            # one per bounce of params["bounces"]
    params = dict(bounces=20, min_rise_m=0.15, max_touch_s=0.02, touch_gap_s=0.02,
                  hit_gain=0.98, drop_x_m=0.36, drop_y_m=-0.20, drop_z_m=1.20, drop_time_s=2.0, fall_height_m=0.35,
                  paddle_mass_kg=FREE_PADDLE["mass_kg"], handle_length_m=FREE_PADDLE["handle_length_m"],
                  handle_width_m=FREE_PADDLE["handle_width_m"], handle_thickness_m=FREE_PADDLE["handle_thickness_m"],
                  blade_centre_m=FREE_PADDLE["blade_centre_from_butt_m"], out_of_hand_s=0.05, retract_after_s=0.15,
                  retract_m=0.35, dropper_free_s=0.1)

    sentence = ("Bounce the table-tennis ball on the paddle in your right hand 20 times, each a hit that sends it back "
                "up to the height it was dropped from, without letting go of the paddle.")
    rules = ("A table tennis racket (a rigid square blade 0.15 m wide and 0.015 m thick on a straight handle "
             "{handle_length_m} m long, {handle_width_m} m wide and {handle_thickness_m} m thick; {paddle_mass_kg} kg; "
             "the blade's centre {blade_centre_m} m from the butt) is a separate body; at the start its handle is "
             "closed in your right hand (three fingers: a thumb, an index and a middle finger), which holds it by "
             "contact and friction only: it can slip, turn in the hand and fall. The paddle is in your hand while its "
             "handle touches the hand's fingers and its thumb or palm; it has left your hand when for more than "
             "{out_of_hand_s} s it has not. The paddle may touch nothing of you but your right hand. The official ball "
             "(40 mm, 2.7 g; it flies in air, with drag) rests in a dropper's cup, its centre {drop_z_m} m above the "
             "floor, until {drop_time_s} s after the start, when the cup's floor opens and it falls; {retract_after_s} s "
             "later the cup moves {retract_m} m away from you along its arm. You succeed after {bounces} bounces on the "
             "blade (either face; the faces need not alternate). A bounce is a touch of the blade after which, before "
             "the ball touches the blade again, the ball's centre rises at least {min_rise_m} m above the height at "
             "which it left the blade and reaches at least the height it was dropped from, {drop_z_m} m above the "
             "floor, and which the ball leaves with at least {hit_gain} of the speed it reached the blade with (both "
             "speeds taken at the height where the touch began). On a still blade every bounce is lower than the one "
             "before (the ball keeps about nine tenths of its height, 0.95 of its speed), so each bounce needs a hit "
             "of the blade; a rebound that rises enough but was not hit is not counted, and is not a fault. A touch "
             "is all contact of the ball with the blade from the first contact on, with breaks shorter than "
             "{touch_gap_s} s; a bounce's own contact lasts about a millisecond. You fail if the paddle leaves your "
             "hand at any time (dropped, thrown or slipped out of the hand); if the paddle touches any part of you "
             "other than your right hand; if the ball comes back to the blade after a touch without having risen that "
             "much; if a touch lasts longer than {max_touch_s} s from its first contact to its last (the ball rests, "
             "rolls or is carried on the blade); if the ball touches the floor or anything other than the blade (the "
             "paddle's handle, your hand, arm or body included, and the dropper from {dropper_free_s} s after "
             "the drop on); if you or the paddle touch the ball before it is dropped; if you fall; or after {time_limit_s} s. A fall is your pelvis lower than {fall_height_m} m "
             "above the floor, or any part of you other than your feet touching the floor; the paddle touching the "
             "floor is a fall too.")
    venue = ("You stand on a level floor facing +x, your arms hanging. The paddle's handle lies across your right "
             "palm in a shakehand grip, the fingers and the thumb closed round it, the blade beyond the index "
             "finger's side and its faces looking the way your palm does (forehand) and the back of your hand "
             "(backhand). The "
             "ball rests in the cup of a dropper {drop_x_m} m ahead of your pelvis and {drop_y_m} m to your left "
             "(negative: to your right), its centre {drop_z_m} m above the floor: a ring round it and two leaves under "
             "it, on a carriage that hangs from an arm reaching towards you from a column further ahead (+x). At "
             "{drop_time_s} s the leaves slide apart and the ball falls, with no speed and no spin; the cup then moves "
             "{retract_m} m back along the arm. There is no wind.")
    difficulty = ("Every bounce needs an upward hit of the right strength at the right instant, with the blade level "
                  "and under a 40 mm ball: a tilt of a degree sends the ball off the 15 cm blade within a few "
                  "bounces, and the arm that holds the blade gives way a little at every hit. The paddle sits in a "
                  "three-finger hand with small finger motors, so the blade is where the fingers hold it, not where "
                  "the arm was told to put it, and it has to go right twenty times in a row.")

    def __init__(self):
        super().__init__()
        self._set_stages()

    def configure(self, params):
        super().configure(params)
        self._set_stages()

    def _set_stages(self):
        self.stages = [f"bounce {i + 1}" for i in range(int(self.p["bounces"]))]
        self.fall_z = float(self.p["fall_height_m"])

    def build(self, sc):
        p = self.p
        sc.box("mat", (0.3, 0, 0.0003), (1.5, 1.5, 0.0003), rgba=(0.45, 0.25, 0.25, 1))
        sc.real_hands[SIDE] = "dex3"
        # the dropper (the shared ball machine block); the ball rests in its cup
        self.dropper = Dropper("dropper", (p["drop_x_m"], p["drop_y_m"], p["drop_z_m"]), BALL["radius"],
                               retract=(1.0, 0.0, 0.0), retract_m=p["retract_m"], retract_s=p["retract_after_s"])
        self.dropper.build(sc)
        sc.ball("ball", "tabletennis", self.dropper.rest_pos())
        build_free_paddle(sc, pos=(0.5, -0.6, 0.05))
        # DeepMind's table-tennis physics (as in paddle_bounce.py): elliptic cones, thin-shell inertia, the blade
        # pair; impratio is left to the real hand's 100 (see the docstring)
        opt = sc.root.find("option")
        opt.set("cone", "elliptic")
        body = next(b for b in sc.wb.iter("body") if b.get("name") == "ball")
        i = 2.0 / 3.0 * BALL["mass"] * BALL["radius"] ** 2
        ET.SubElement(body, "inertial", pos="0 0 0", mass=repr(BALL["mass"]), diaginertia=f"{i:.6g} {i:.6g} {i:.6g}")
        ET.SubElement(sc.root.find("contact"), "pair", name="ball_paddle_blade", geom1="ball", geom2="paddle_blade",
                      **BLADE_PAIR)
        sc.camera("venue", (1.7, -1.8, 1.45), (0.2, -0.1, 0.9), fovy=42)

    def reset(self, w):
        """The paddle's handle across the right palm (GRIP: its axis the grasp frame's y, the blade's normal the
        palm's), then the hand closes on it (the full command) and the grasp settles."""
        p = self.p
        self.dropper.reset(w)
        self.dropper.open_t = p["drop_time_s"]
        c, R = w.grasp_frame(SIDE)
        Rp = np.c_[R[:, 0], -R[:, 2], R[:, 1]]              # paddle x = the palm's normal, z = the handle = grasp y
        q = np.zeros(4)
        mujoco.mju_mat2Quat(q, Rp.ravel())
        w.put("paddle", c - GRIP["butt_out_m"] * R[:, 1] + GRIP["palm_off_m"] * R[:, 0] + GRIP["finger_off_m"] * R[:, 2],
              quat=q)
        self.grasp = w.close_on(SIDE, "paddle")

    def referee_reset(self, w, ref):
        p = self.p
        self.ball = ref.geoms(body="ball")
        self.blade = ref.geoms(names=["paddle_blade"])
        self.handle = ref.geoms(names=["paddle_handle"])
        self.paddle = self.blade | self.handle
        self.dropper_g = ref.geoms(prefix="dropper")
        self.other = ref.robot_mask | self.handle
        self.right_hand = ref.part(f"{SIDE}_hand")
        ng = w.m.ngeom
        self.grips = tuple(np.isin(np.arange(ng), w.hands.group_geoms(w, SIDE, g)) for g in ("fingers", "thumb_palm"))
        self.trackers = {"blade": Touch(ref, self.ball, self.blade, gap=p["touch_gap_s"]), "dropped": False,
                         "left_z": None, "apex_z": None, "risen": True, "bounces": 0, "speed": 0.0, "v_in": 0.0,
                         "z_in": 0.0, "in_hand_t": 0.0}

    def before_step(self, w):
        p = self.p
        self.dropper.write(w, w.t)
        if not self.trackers["dropped"] and w.k >= int(round(p["drop_time_s"] / w.CONTROL_DT)):
            self.trackers["dropped"] = True
            w.ref.event("drop")

    def in_hand(self, ref) -> bool:
        return ref.touching(self.handle, self.grips[0]) and ref.touching(self.handle, self.grips[1])

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        if self.in_hand(ref):
            tr["in_hand_t"] = round(ref.time, 4)
        else:
            gap = round(ref.time - tr["in_hand_t"], 4)
            if gap > ref.metrics.get("grip_break_max_s", 0.0):
                ref.metrics["grip_break_max_s"] = gap       # (reported: the longest break of the hand's hold)
            if gap > p["out_of_hand_s"] + 1e-9:
                return ref.fail(LEFT_HAND, out_s=gap)
        if ref.touching(self.paddle, ref.robot_mask & ~self.right_hand):
            return ref.fail(HELD_ELSE, parts=sorted(ref.parts_touching(self.paddle) - {f"{SIDE}_hand"}))
        if ref.touching(self.paddle, ref.ground):
            return ref.fail(PADDLE_FLOOR)
        if not tr["dropped"]:
            if ref.touching(self.ball, self.other | self.blade):
                ref.fail(EARLY, parts=sorted(ref.parts_touching(self.ball)),
                         paddle=ref.touching(self.ball, self.paddle))
            return
        if ref.touching(self.ball, self.other):
            return ref.fail(OTHER, parts=sorted(ref.parts_touching(self.ball)),
                            handle=ref.touching(self.ball, self.handle))
        if ref.touching(self.ball, ref.ground):
            return ref.fail(FLOOR)
        if ref.time > p["drop_time_s"] + p["dropper_free_s"] and ref.touching(self.ball, self.dropper_g):
            return ref.fail(OTHER, parts=["dropper"])
        t = tr["blade"]
        z = float(w.pos("ball")[2])
        speed, tr["speed"] = tr["speed"], float(np.linalg.norm(w.vel("ball")))     # speed: one physics step ago
        if t.update():
            if not tr["risen"]:
                return ref.fail(LOW, rise_m=round(tr["apex_z"] - tr["left_z"], 3), apex_m=round(tr["apex_z"], 3))
            tr["risen"], tr["v_in"], tr["z_in"] = False, speed, z
        if ref.touching(self.ball, self.blade):
            tr["left_z"] = tr["apex_z"] = z
            if t.duration > p["max_touch_s"]:
                return ref.fail(REST, touch_s=round(t.duration, 3))
        elif t.count and not tr["risen"]:
            tr["apex_z"] = max(tr["apex_z"], z)
            if z - tr["left_z"] >= p["min_rise_m"] and z >= p["drop_z_m"]:
                tr["risen"] = True
                # the speed the ball left the blade with, at the touch's height (from its energy now: free flight)
                v_out = math.sqrt(max(0.0, tr["speed"] ** 2 + 2 * 9.81 * (z - tr["z_in"])))
                if v_out < p["hit_gain"] * tr["v_in"]:     # a rebound, not a hit: not counted
                    ref.event("rebound", speed_in=round(tr["v_in"], 3), speed_out=round(v_out, 3))
                    return
                tr["bounces"] += 1
                n = tr["bounces"]
                ref.metrics["bounces"] = n
                if ref.stage(f"bounce {n}", left_z=round(tr["left_z"], 3)) and n >= int(p["bounces"]):
                    ref.succeed()

    def step(self, w, ref):
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)

    def privileged(self, w):
        g = w.m.geom("paddle_blade").id
        n = np.asarray(w.d.geom_xmat[g]).reshape(3, 3)[:, 0]         # the blade's normal; reported as the face looking up
        _, va = w.free["ball"]
        _, pv = w.free["paddle"]
        R = w.d.xmat[w.m.body("ball").id].reshape(3, 3)
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "ball_spin": (R @ w.d.qvel[va + 3:va + 6]).tolist(),
                "dropped": bool(self.trackers.get("dropped")), "drop_time_s": self.p["drop_time_s"],
                "blade_centre": w.d.geom_xpos[g].tolist(), "blade_normal": (n if n[2] >= 0 else -n).tolist(),
                "paddle_pos": w.pos("paddle").tolist(), "paddle_quat": w.d.xquat[w.m.body("paddle").id].tolist(),
                "paddle_velocity": w.d.qvel[pv:pv + 3].tolist(), "paddle_angvel": w.d.qvel[pv + 3:pv + 6].tolist(),
                "paddle_in_hand_t": self.trackers.get("in_hand_t", 0.0),
                "bounces": int(self.trackers.get("bounces", 0)), "paddle": FREE_PADDLE}
