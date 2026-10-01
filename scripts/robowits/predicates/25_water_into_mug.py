def _check_success(self) -> torch.Tensor:
        """Check if task is successful: mug contains water (particle-based)."""
        objs_info = self.collect_objs_info()

        def _is_completed(objs_info) -> bool:
            """Checks if the task is completed: The mug contains water (particle-based).
            Also ensures involved objects (mug and water) have not fallen off the table.
            """

            # Workspace/table bounds
            TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
            TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69
            EDGE_TOL = 0.02  # small tolerance for boundary checks

            # Required objects
            if "mug" not in objs_info or "water" not in objs_info:
                return False

            mug = objs_info["mug"]
            water = objs_info["water"]

            # Basic validity checks
            if mug.get("bounds") is None or water.get("pos") is None:
                return False

            # Derive a conservative approximation of the mug's interior:
            # - Use mug AABB to estimate a circular opening centered at the mug's xy center
            # - Radius is a fraction of the smallest xy extent to avoid counting handle/outside
            try:
                (xmin, ymin, zmin), (xmax, ymax, zmax) = mug["bounds"]
            except Exception:
                return False

            cx, cy = 0.5 * (xmin + xmax), 0.5 * (ymin + ymax)
            dx, dy = max(0.0, xmax - xmin), max(0.0, ymax - ymin)
            if dx <= 0.0 or dy <= 0.0:
                return False

            # Circular interior proxy to avoid including handle/outer hull
            r = 0.4 * min(dx, dy)
            if r <= 0:
                return False

            # Vertical bounds for being inside the mug (avoid counting below base or above rim)
            z_low = zmin + 0.01
            z_high = zmax - 0.005
            if z_high <= z_low:
                return False

            # Water particle positions
            wpos = np.array(water["pos"])
            if wpos.ndim != 2 or wpos.shape[1] != 3:
                return False
            N = wpos.shape[0]

            # Count water particles within the mug interior proxy
            if N > 0:
                dxv = wpos[:, 0] - cx
                dyv = wpos[:, 1] - cy
                radial_ok = (dxv * dxv + dyv * dyv) <= (r * r)
                vertical_ok = (wpos[:, 2] >= z_low) & (wpos[:, 2] <= z_high)
                in_mug = radial_ok & vertical_ok
                collected = int(np.count_nonzero(in_mug))
            else:
                collected = 0

            # Success threshold: some amount of water is in the mug
            threshold = 1
            collected_ok = collected >= threshold

            # Mug must remain within table xy bounds (via convex hull if available)
            hull = mug.get("convex_hull_2d", None)
            if hull is not None:
                hull = np.array(hull)
                if hull.ndim == 2 and hull.shape[1] == 2 and hull.shape[0] > 0:
                    mug_on_table = (
                        np.all(hull[:, 0] >= (TABLE_X_MIN - EDGE_TOL))
                        and np.all(hull[:, 0] <= (TABLE_X_MAX + EDGE_TOL))
                        and np.all(hull[:, 1] >= (TABLE_Y_MIN - EDGE_TOL))
                        and np.all(hull[:, 1] <= (TABLE_Y_MAX + EDGE_TOL))
                    )
                else:
                    mug_on_table = (
                        xmin >= (TABLE_X_MIN - EDGE_TOL)
                        and xmax <= (TABLE_X_MAX + EDGE_TOL)
                        and ymin >= (TABLE_Y_MIN - EDGE_TOL)
                        and ymax <= (TABLE_Y_MAX + EDGE_TOL)
                    )
            else:
                mug_on_table = (
                    xmin >= (TABLE_X_MIN - EDGE_TOL)
                    and xmax <= (TABLE_X_MAX + EDGE_TOL)
                    and ymin >= (TABLE_Y_MIN - EDGE_TOL)
                    and ymax <= (TABLE_Y_MAX + EDGE_TOL)
                )

            # Mug must be resting on (or near) the table surface, not floating
            TABLE_Z = 0.76
            MUG_FLOAT_TOL = 0.05  # allow up to 5 cm above table for physics settling
            mug_on_surface = zmin <= TABLE_Z + MUG_FLOAT_TOL

            # Majority of water particles should remain over the table xy region
            if N > 0:
                inside_x = (wpos[:, 0] >= (TABLE_X_MIN - EDGE_TOL)) & (wpos[:, 0] <= (TABLE_X_MAX + EDGE_TOL))
                inside_y = (wpos[:, 1] >= (TABLE_Y_MIN - EDGE_TOL)) & (wpos[:, 1] <= (TABLE_Y_MAX + EDGE_TOL))
                frac_on_table = float(np.count_nonzero(inside_x & inside_y)) / N
            else:
                frac_on_table = 1.0
            water_not_fallen = frac_on_table >= 0.7  # allow some spill but not majority off-table

            return bool(collected_ok and mug_on_table and mug_on_surface and water_not_fallen)

        return torch.tensor([_is_completed(objs_info)], dtype=torch.bool, device=self._device)
