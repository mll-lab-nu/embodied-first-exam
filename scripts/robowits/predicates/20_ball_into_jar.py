def _check_success(self) -> torch.Tensor:
        """Check if task is successful: foam ball mostly inside the jar's AABB."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69
        Z_FLOOR_THRESH = self.TABLE_Z - 0.15
        PAD = 0.02

        jar = objs_info.get("glass jar")
        ball = objs_info.get("foam ball")

        if jar is None or ball is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def is_not_fallen(obj):
            x_min, x_max = TABLE_X_MIN - PAD, TABLE_X_MAX + PAD
            y_min, y_max = TABLE_Y_MIN - PAD, TABLE_Y_MAX + PAD

            mat = obj.get("material", "rigid")
            if mat == "rigid":
                hull = obj.get("convex_hull_2d")
                if hull is not None and np.size(hull) > 0:
                    xs, ys = hull[:, 0], hull[:, 1]
                    within_xy = (
                        np.all(xs >= x_min) and np.all(xs <= x_max) and np.all(ys >= y_min) and np.all(ys <= y_max)
                    )
                else:
                    b = obj.get("bounds")
                    if b is None:
                        p = obj.get("pos")
                        p = np.array([np.inf, np.inf, np.inf]) if p is None else p
                        within_xy = (x_min <= p[0] <= x_max) and (y_min <= p[1] <= y_max)
                    else:
                        within_xy = b[0][0] >= x_min and b[1][0] <= x_max and b[0][1] >= y_min and b[1][1] <= y_max
                b = obj.get("bounds")
                if b is not None:
                    min_z = float(b[0][2])
                else:
                    p = obj.get("pos")
                    p = np.array([0.0, 0.0, 10.0]) if p is None else p
                    min_z = float(p[2])
                return within_xy and (min_z > Z_FLOOR_THRESH)
            else:
                pos = obj.get("pos")
                if pos is None or np.size(pos) == 0:
                    return False
                pos = np.asarray(pos)
                xy = pos[:, :2]
                xs, ys = xy[:, 0], xy[:, 1]
                within = (xs >= x_min) & (xs <= x_max) & (ys >= y_min) & (ys <= y_max)
                frac_within = np.mean(within) if within.size > 0 else 0.0
                min_z = float(np.min(pos[:, 2])) if pos.size > 0 else 10.0
                return (frac_within >= 0.8) and (min_z > Z_FLOOR_THRESH)

        if not (is_not_fallen(jar) and is_not_fallen(ball)):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        jar_bounds = jar.get("bounds")
        if jar_bounds is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        jb = np.asarray(jar_bounds, dtype=float).reshape(2, 3)
        j_lo, j_hi = jb[0], jb[1]

        ball_mat = ball.get("material", "rigid")
        if ball_mat == "particle":
            ball_pos = ball.get("pos")
            if ball_pos is None or np.size(ball_pos) == 0:
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            ball_pos = np.asarray(ball_pos, dtype=float)
            inside = (
                (ball_pos[:, 0] >= j_lo[0])
                & (ball_pos[:, 0] <= j_hi[0])
                & (ball_pos[:, 1] >= j_lo[1])
                & (ball_pos[:, 1] <= j_hi[1])
                & (ball_pos[:, 2] >= j_lo[2])
                & (ball_pos[:, 2] <= j_hi[2])
            )
            frac_inside = float(np.mean(inside))
            return torch.tensor([frac_inside >= 0.90], dtype=torch.bool, device=self._device)

        b = ball.get("bounds")
        if b is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        bb = np.asarray(b, dtype=float).reshape(2, 3)
        b_lo, b_hi = bb[0], bb[1]
        ball_fully_inside = bool(np.all(b_lo >= j_lo) and np.all(b_hi <= j_hi))
        return torch.tensor([ball_fully_inside], dtype=torch.bool, device=self._device)
