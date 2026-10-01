def _check_success(self) -> torch.Tensor:
        """Check if task is successful: exactly one lid covers pot correctly."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69
        OVERLAP_RATIO_MIN = 0.80
        SIZE_RATIO_MIN = 0.85
        SIZE_RATIO_MAX = 1.40
        Z_ABOVE_EPS = 0.01

        def get_hull(obj):
            hull = obj.get("convex_hull_2d", None)
            if hull is not None and isinstance(hull, np.ndarray) and hull.shape[0] >= 3:
                return hull.copy()
            b = obj.get("bounds", None)
            if b is None:
                return None
            (xmin, ymin, _), (xmax, ymax, _) = b
            return np.array([[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]], dtype=float)

        def is_within_table_bounds(hull):
            if hull is None or len(hull) == 0:
                return False
            xs = hull[:, 0]
            ys = hull[:, 1]
            return (
                np.all(xs >= TABLE_X_MIN - 1e-3)
                and np.all(xs <= TABLE_X_MAX + 1e-3)
                and np.all(ys >= TABLE_Y_MIN - 1e-3)
                and np.all(ys <= TABLE_Y_MAX + 1e-3)
            )

        def compute_overlap_ratio(hull1, hull2):
            if hull1 is None or hull2 is None:
                return 0.0
            area1 = self._polygon_area(hull1)
            if area1 <= 1e-9:
                return 0.0
            inter_area = _utils.intersection_area(hull1, hull2)
            return inter_area / area1

        pot = objs_info.get("pot without lid")
        if pot is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        pot_hull = get_hull(pot)
        if pot_hull is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if not is_within_table_bounds(pot_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        pot_area = self._polygon_area(pot_hull)
        if pot_area <= 1e-6:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        pot_z = float(pot["pos"][2])

        lid_names = ["small lid", "lid medium", "lid large"]
        valid_candidates = []

        for lname in lid_names:
            lid = objs_info.get(lname)
            if lid is None:
                continue

            lid_hull = get_hull(lid)
            if lid_hull is None:
                continue

            if not is_within_table_bounds(lid_hull):
                continue

            lid_area = self._polygon_area(lid_hull)
            if lid_area <= 1e-6:
                continue

            lid_z = float(lid["pos"][2])
            if not (lid_z > pot_z + Z_ABOVE_EPS):
                continue

            size_ratio = lid_area / pot_area
            if size_ratio < SIZE_RATIO_MIN or size_ratio > SIZE_RATIO_MAX:
                continue

            overlap = compute_overlap_ratio(lid_hull, pot_hull)
            if overlap < OVERLAP_RATIO_MIN - 1e-6:
                continue

            valid_candidates.append(lname)

        return torch.tensor([len(valid_candidates) == 1], dtype=torch.bool, device=self._device)
