"""Connect a measured rigid grasp through independently supplied object hints.

Hints only guide search. Every accepted segment is checked against the current
ball and attached-tool surfaces, including continuous bounds between poses.
"""
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.feedback import body_pose
from topogym.planning.rigid_reference.geometry import interpolate, pose_dict
from topogym.planning.rigid_reference.rrt import connect_search


def connect_object_hints(checker, start, goal, hints, *, rng, iterations, progress=None):
    """Return a geometric candidate only; robot IK and execution remain separate."""
    poses = []
    for row in hints:
        p = np.asarray(row["position_m"], float)
        q = np.asarray(row["quaternion_wxyz"], float)
        if (p.shape != (3,) or q.shape != (4,) or not np.isfinite(p).all()
                or not np.isfinite(q).all() or not np.isclose(np.linalg.norm(q), 1.)):
            raise ValueError("Object hints must contain finite positions and unit wxyz quaternions")
        poses.append(body_pose(row))
    evidence = dict(connected=False, frame="hedgehog_cage", hint_count=len(poses),
                    physical_execution_verified=False, stages=[], rejected_hints=[])
    free = []
    for index, pose in enumerate(poses):
        gap = checker.clearance(pose)
        if gap > checker.margin+checker.error:
            free.append((index, pose))
        else:
            evidence["rejected_hints"].append(dict(index=index, clearance_m=gap))
    remaining = max(0, int(iterations))
    stage_budget = max(1, int(iterations)//6)
    path = [start]

    def connect(a, b, label):
        nonlocal remaining
        direct = checker.edge(a, b)
        if direct["passed"]:
            evidence["stages"].append(dict(label=label, mode="direct", certificate=direct))
            return [a, b]
        if remaining <= 0:
            return None
        budget = min(remaining, stage_budget)
        lower = np.minimum(a[0], b[0])-[.06, .06, .04]
        upper = np.maximum(a[0], b[0])+[.06, .06, .06]

        def sample(random):
            if random.random() < .8:
                p, r = interpolate(a, b, random.uniform())
                return (p+random.normal(0., [.012, .012, .018]),
                        Rotation.from_rotvec(random.normal(0., .25, 3))*r)
            return (random.uniform(lower, upper),
                    Rotation.from_rotvec(random.normal(0., .7, 3))*a[1])

        def local(random, pose):
            p, r = pose
            axis = np.eye(3)[int(random.integers(3))]
            if random.random() < .5:
                return p+axis*random.normal(0., .005), r
            return p, Rotation.from_rotvec(axis*random.normal(0., .06))*r

        route, result = connect_search(checker, a, b, sample, rng=rng,
            iterations=budget, step_m=.006, metric_radius_m=.09, local_sample=local,
            progress=None if progress is None else lambda data: progress(dict(stage=label, **data)))
        remaining -= result["iterations"]
        evidence["stages"].append(dict(label=label, mode="local_search", **result,
                                      direct_rejection=direct))
        return route

    for index, pose in free:
        joined = connect(path[-1], pose, f"object_hint_{index}")
        if joined is None:
            evidence.update(failed_hint=index, remaining_iterations=remaining,
                            reached_poses=[pose_dict(p) for p in path])
            return None, evidence
        path.extend(joined[1:])
        radial = np.linalg.norm(pose[0][:2])
        if .045 <= radial <= .12:
            # Once the payload is near a side opening, check whether a fixed
            # orientation withdrawal can avoid unnecessary later rotations.
            outward = pose[0].copy()
            outward[:2] += .18*pose[0][:2]/radial
            end = (outward, pose[1])
            certificate = checker.edge(pose, end)
            if certificate["passed"]:
                tail = connect(end, goal, f"withdraw_hint_{index}_to_goal")
                if tail is not None:
                    evidence.update(connected=True, withdrawal_hint=index,
                                    withdrawal_certificate=certificate,
                                    remaining_iterations=remaining)
                    return path+[end]+tail[1:], evidence
    tail = connect(path[-1], goal, "object_hints_to_goal")
    evidence.update(connected=tail is not None, remaining_iterations=remaining)
    return (None if tail is None else path+tail[1:]), evidence
