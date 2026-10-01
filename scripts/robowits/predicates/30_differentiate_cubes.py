def _check_success(self) -> torch.Tensor:
        """Check if task is successful: wooden cube on target, metal cube in mug."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69

        def get_hull_xy(bounds, hull_2d):
            if hull_2d is not None and len(hull_2d) >= 3:
                return np.array([(float(p[0]), float(p[1])) for p in hull_2d])
            if bounds is None:
                return None
            xmin, ymin = float(bounds[0][0]), float(bounds[0][1])
            xmax, ymax = float(bounds[1][0]), float(bounds[1][1])
            return np.array([(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)])

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

        wood = objs_info.get("wooden cube")
        metal = objs_info.get("metal cube")
        mug = objs_info.get("mug")
        target = objs_info.get("target area")

        if wood is None or metal is None or mug is None or target is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        wood_hull = get_hull_xy(wood.get("bounds"), wood.get("convex_hull_2d"))
        metal_hull = get_hull_xy(metal.get("bounds"), metal.get("convex_hull_2d"))
        mug_hull = get_hull_xy(mug.get("bounds"), mug.get("convex_hull_2d"))
        target_hull = get_hull_xy(target.get("bounds"), target.get("convex_hull_2d"))

        if wood_hull is None or not is_within_table_bounds(wood_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        if metal_hull is None or not is_within_table_bounds(metal_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if target_hull is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        overlap = compute_overlap_ratio(wood_hull, target_hull)
        wood_on_target_ok = overlap >= 0.50

        if mug_hull is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        metal_in_xy = compute_overlap_ratio(metal_hull, mug_hull) >= 0.50
        wood_in_xy = compute_overlap_ratio(wood_hull, mug_hull) >= 0.50

        metal_bounds = metal.get("bounds")
        mug_bounds = mug.get("bounds")
        wood_bounds = wood.get("bounds")
        if metal_bounds is None or mug_bounds is None or wood_bounds is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        m_zmin, m_zmax = metal_bounds[0][2], metal_bounds[1][2]
        w_zmin, w_zmax = wood_bounds[0][2], wood_bounds[1][2]
        g_zmin, g_zmax = mug_bounds[0][2], mug_bounds[1][2]
        lower_margin = 0.005
        upper_margin = 0.005
        metal_in_z = (m_zmin >= g_zmin + lower_margin) and (m_zmax <= g_zmax - upper_margin)
        wood_in_z = (w_zmin >= g_zmin + lower_margin) and (w_zmax <= g_zmax - upper_margin)

        metal_in_mug_ok = metal_in_xy and metal_in_z
        wood_out_of_mug_ok = not (wood_in_xy and wood_in_z)

        return torch.tensor(
            [wood_on_target_ok and metal_in_mug_ok and wood_out_of_mug_ok], dtype=torch.bool, device=self._device
        )
