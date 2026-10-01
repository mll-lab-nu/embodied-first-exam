def _check_success(self) -> torch.Tensor:
        """Check if task is successful: ball on top of tower, stable, not held."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69
        TABLE_TOL = 1e-3

        base = objs_info.get("tower base")
        ball = objs_info.get("ball")

        if base is None or ball is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def in_table_xy(obj):
            hull = obj.get("convex_hull_2d")
            if hull is not None:
                for pt in hull:
                    x, y = float(pt[0]), float(pt[1])
                    if not (TABLE_X_MIN - TABLE_TOL <= x <= TABLE_X_MAX + TABLE_TOL):
                        return False
                    if not (TABLE_Y_MIN - TABLE_TOL <= y <= TABLE_Y_MAX + TABLE_TOL):
                        return False
                return True
            pos = obj.get("pos")
            if pos is None:
                return False
            x, y = float(pos[0]), float(pos[1])
            return (TABLE_X_MIN - TABLE_TOL <= x <= TABLE_X_MAX + TABLE_TOL) and (
                TABLE_Y_MIN - TABLE_TOL <= y <= TABLE_Y_MAX + TABLE_TOL
            )

        if not in_table_xy(base) or not in_table_xy(ball):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        vel = ball.get("vel")
        if vel is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        speed = math.sqrt(float(vel[0]) ** 2 + float(vel[1]) ** 2 + float(vel[2]) ** 2)
        stable_linear = speed < 0.05
        stable_vertical = abs(float(vel[2])) < 0.03
        stability_ok = stable_linear and stable_vertical

        base_bounds = base.get("bounds")
        ball_pos = ball.get("pos")
        if base_bounds is None or ball_pos is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        base_top_z = float(base_bounds[1][2])
        ball_center_z = float(ball_pos[2])
        height_ok = ball_center_z > base_top_z + 0.005

        base_hull = base.get("convex_hull_2d")
        ball_xy = (float(ball_pos[0]), float(ball_pos[1]))

        def point_in_polygon(pt, poly):
            x, y = pt
            inside = False
            n = len(poly)
            if n < 3:
                return False
            for i in range(n):
                x1, y1 = float(poly[i][0]), float(poly[i][1])
                x2, y2 = float(poly[(i + 1) % n][0]), float(poly[(i + 1) % n][1])
                if (y1 > y) != (y2 > y):
                    xinters = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-9) + x1
                    if x < xinters + 1e-12:
                        inside = not inside
            return inside

        if base_hull is not None and len(base_hull) >= 3:
            on_top_ok = point_in_polygon(ball_xy, base_hull)
        else:
            x_min, y_min = float(base_bounds[0][0]) - 0.005, float(base_bounds[0][1]) - 0.005
            x_max, y_max = float(base_bounds[1][0]) + 0.005, float(base_bounds[1][1]) + 0.005
            on_top_ok = (x_min <= ball_xy[0] <= x_max) and (y_min <= ball_xy[1] <= y_max)

        # Check ball is not being held by either gripper
        not_held = not check_being_held(ball, self._robot)

        return torch.tensor(
            [stability_ok and height_ok and on_top_ok and not_held], dtype=torch.bool, device=self._device
        )
