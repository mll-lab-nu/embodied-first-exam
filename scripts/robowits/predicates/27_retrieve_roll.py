def _check_success(self) -> torch.Tensor:
        """Check if task is successful: roll on target area."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69

        def get_hull_xy(bounds, hull_2d):
            if hull_2d is not None and len(hull_2d) >= 3:
                return [(float(p[0]), float(p[1])) for p in hull_2d]
            if bounds is None:
                return None
            xmin, ymin = float(bounds[0][0]), float(bounds[0][1])
            xmax, ymax = float(bounds[1][0]), float(bounds[1][1])
            return [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]

        def is_within_table_bounds(poly):
            if poly is None:
                return False
            for x, y in poly:
                if x < TABLE_X_MIN - 1e-3 or x > TABLE_X_MAX + 1e-3:
                    return False
                if y < TABLE_Y_MIN - 1e-3 or y > TABLE_Y_MAX + 1e-3:
                    return False
            return True

        def polygon_area(poly):
            if poly is None or len(poly) < 3:
                return 0.0
            n = len(poly)
            area = 0.0
            for i in range(n):
                j = (i + 1) % n
                area += poly[i][0] * poly[j][1]
                area -= poly[j][0] * poly[i][1]
            return abs(area) / 2.0

        def compute_overlap_ratio(poly_a, poly_b):
            inter_area = _utils.intersection_area(poly_a, poly_b)
            a_area = polygon_area(poly_a)
            if a_area <= 1e-9:
                return 0.0
            return inter_area / a_area

        roll = objs_info.get("hollow roll")
        target = objs_info.get("green target area")

        if roll is None or target is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        roll_hull = get_hull_xy(roll.get("bounds"), roll.get("convex_hull_2d"))
        target_hull = get_hull_xy(target.get("bounds"), target.get("convex_hull_2d"))

        if roll_hull is None or target_hull is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if not is_within_table_bounds(roll_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        if not is_within_table_bounds(target_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        overlap = compute_overlap_ratio(roll_hull, target_hull)
        return torch.tensor([overlap >= 0.5], dtype=torch.bool, device=self._device)
