"""Episode-latched rejection of native gripper / fine-strand contacts."""
import numpy as np


FAILURE_REASON = "gripper_fine_strand_contact"


def _numpy(value):
    return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)


def gripper_link_names(robot):
    """Include the housing and linkage, not just the two fingertip pads.

    Robotiq is rooted at tool_mount; the original Panda tool is rooted at hand.
    IDs are global, like Genesis contact pairs and RigidLink.parent_idx.
    """
    links = {link.idx: link for link in robot.links}
    by_name = {link.name: link for link in robot.links}
    root = by_name.get("tool_mount", by_name.get("hand"))
    if root is None:
        raise ValueError("Cannot identify gripper subtree; refusing an unmonitored tool")
    selected = {}
    for link in robot.links:
        ancestor = link
        while ancestor is not None:
            if ancestor.idx == root.idx:
                selected[link.idx] = link.name
                break
            ancestor = links.get(ancestor.parent_idx)
    return selected


class GripperFineContactGuard:
    """Any reported contact fails, regardless of force, duration or finger command.

    This guard belongs to one episode. Separation and physics-state restoration
    cannot clear it; a new task instance creates a new episode.
    """

    def __init__(self, gripper_links, fine_links, substep_dt):
        if not gripper_links or not fine_links:
            raise ValueError("Contact guard requires both gripper and fine-strand links")
        self.gripper_links = dict(gripper_links)
        self.fine_links = dict(fine_links)
        self.substep_dt = float(substep_dt)
        self.observed_substeps = 0
        self.first_contact = None

    def observe(self, contacts):
        self.observed_substeps += 1
        if self.first_contact is not None:
            return
        a, b = (_numpy(contacts[key]).astype(int) for key in ("link_a", "link_b"))
        if a.ndim != 1 or b.shape != a.shape:
            raise ValueError("Fiber contact guard expects a single, non-batched scene")
        valid = _numpy(contacts.get("valid_mask", np.ones(a.shape, dtype=bool))).astype(bool)
        forward = np.isin(a, list(self.gripper_links)) & np.isin(b, list(self.fine_links))
        reverse = np.isin(b, list(self.gripper_links)) & np.isin(a, list(self.fine_links))
        hits = np.flatnonzero(valid & (forward | reverse))
        if not hits.size:
            return
        i = int(hits[0])
        gripper, fine = (a[i], b[i]) if forward[i] else (b[i], a[i])
        self.first_contact = dict(
            reason=FAILURE_REASON, substep=self.observed_substeps,
            time_s=self.observed_substeps*self.substep_dt,
            gripper_link=self.gripper_links[gripper], fine_link=self.fine_links[fine],
            position_m=_numpy(contacts["position"])[i].tolist(),
        )

    def install(self, solver):
        """Observe immediately after each native rigid substep, including scene.step.

        The task uses Genesis' rigid articulated cable. Leaving native collision
        and force resolution intact also preserves the contact diagnostic data.
        """
        physics_substep = solver.substep

        def tracked_substep(*args, **kwargs):
            result = physics_substep(*args, **kwargs)
            # This guard already filters global link IDs. Reading the collider
            # directly avoids many redundant GPU entity-mask kernels per substep.
            self.observe(solver.collider.get_contacts())
            return result

        solver.substep = tracked_substep

    def report(self):
        return dict(failed=self.first_contact is not None,
                    first_contact=self.first_contact,
                    observed_substeps=self.observed_substeps)
