def _check_success(self) -> torch.Tensor:
        """Check if task is successful: bowls nested concentrically."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69
        TABLE_TOL = 0.01
        RADIAL_TOL = 0.01
        NUM_TOL = 1e-3

        def get_obj(name):
            obj = objs_info.get(name, None)
            if obj is None:
                return None
            return obj

        def get_center_2d(obj):
            hull = obj.get("convex_hull_2d", None)
            if hull is not None and isinstance(hull, np.ndarray) and hull.size >= 2:
                c = np.mean(hull, axis=0)
                if np.all(np.isfinite(c)):
                    return c
            bounds = obj.get("bounds", None)
            if bounds is not None and isinstance(bounds, np.ndarray) and bounds.shape == (2, 3):
                (xmin, ymin, _), (xmax, ymax, _) = bounds
                return np.array([(xmin + xmax) / 2.0, (ymin + ymax) / 2.0], dtype=float)
            pos = obj.get("pos", None)
            if pos is not None and isinstance(pos, np.ndarray) and pos.size >= 2:
                return pos[:2].astype(float)
            return None

        def is_on_table(obj):
            hull = obj.get("convex_hull_2d", None)
            if hull is not None and isinstance(hull, np.ndarray) and hull.size >= 2:
                xs = hull[:, 0]
                ys = hull[:, 1]
                if np.any(xs < TABLE_X_MIN - TABLE_TOL) or np.any(xs > TABLE_X_MAX + TABLE_TOL):
                    return False
                return not (np.any(ys < TABLE_Y_MIN - TABLE_TOL) or np.any(ys > TABLE_Y_MAX + TABLE_TOL))
            bounds = obj.get("bounds", None)
            if bounds is not None and isinstance(bounds, np.ndarray) and bounds.shape == (2, 3):
                (xmin, ymin, _), (xmax, ymax, _) = bounds
                if xmin < TABLE_X_MIN - TABLE_TOL or xmax > TABLE_X_MAX + TABLE_TOL:
                    return False
                return not (ymin < TABLE_Y_MIN - TABLE_TOL or ymax > TABLE_Y_MAX + TABLE_TOL)
            pos = obj.get("pos", None)
            if pos is not None and isinstance(pos, np.ndarray) and pos.size >= 2:
                x, y = float(pos[0]), float(pos[1])
                if x < TABLE_X_MIN - TABLE_TOL or x > TABLE_X_MAX + TABLE_TOL:
                    return False
                return not (y < TABLE_Y_MIN - TABLE_TOL or y > TABLE_Y_MAX + TABLE_TOL)
            return False

        large = get_obj("large bowl")
        medium = get_obj("medium bowl")
        if large is None or medium is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if not (is_on_table(large) and is_on_table(medium)):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        c_large = get_center_2d(large)
        c_medium = get_center_2d(medium)
        if c_large is None or c_medium is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        radial_offset = np.linalg.norm(c_large - c_medium)

        return torch.tensor([bool(radial_offset <= (RADIAL_TOL + NUM_TOL))], dtype=torch.bool, device=self._device)
