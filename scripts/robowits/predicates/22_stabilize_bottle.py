def _check_success(self) -> torch.Tensor:
        """Check if task is successful: tube standing upright in bowl."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69
        TILT_DEG_MAX = 5.0
        SPEED_MAX = 0.01
        MARGIN = 1e-3

        tube = objs_info.get("tube")
        bowl = objs_info.get("bowl")

        if tube is None or bowl is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def is_on_table(obj):
            hull = obj.get("convex_hull_2d")
            if hull is not None:
                xs = [float(p[0]) for p in hull]
                ys = [float(p[1]) for p in hull]
                return (
                    min(xs) >= TABLE_X_MIN - MARGIN
                    and max(xs) <= TABLE_X_MAX + MARGIN
                    and min(ys) >= TABLE_Y_MIN - MARGIN
                    and max(ys) <= TABLE_Y_MAX + MARGIN
                )
            bounds = obj.get("bounds")
            if bounds is not None:
                x_min, y_min = float(bounds[0][0]), float(bounds[0][1])
                x_max, y_max = float(bounds[1][0]), float(bounds[1][1])
                return (
                    x_min >= TABLE_X_MIN - MARGIN
                    and x_max <= TABLE_X_MAX + MARGIN
                    and y_min >= TABLE_Y_MIN - MARGIN
                    and y_max <= TABLE_Y_MAX + MARGIN
                )
            return False

        if not is_on_table(tube) or not is_on_table(bowl):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def point_in_polygon(pt, poly):
            if poly is None or len(poly) < 3:
                return False
            x, y = float(pt[0]), float(pt[1])
            inside = False
            n = len(poly)
            for i in range(n):
                x1, y1 = float(poly[i][0]), float(poly[i][1])
                x2, y2 = float(poly[(i + 1) % n][0]), float(poly[(i + 1) % n][1])
                if (y1 > y) != (y2 > y):
                    denom = y2 - y1
                    if abs(denom) < 1e-12:
                        continue
                    xinters = (x2 - x1) * (y - y1) / denom + x1
                    if x < xinters:
                        inside = not inside
            return inside

        bowl_hull = bowl.get("convex_hull_2d")
        tube_pos = tube.get("pos")
        if tube_pos is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if bowl_hull is not None and len(bowl_hull) >= 3:
            if not point_in_polygon((float(tube_pos[0]), float(tube_pos[1])), bowl_hull):
                return torch.tensor([False], dtype=torch.bool, device=self._device)
        else:
            bowl_bounds = bowl.get("bounds")
            if bowl_bounds is None:
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            x_min, y_min = float(bowl_bounds[0][0]), float(bowl_bounds[0][1])
            x_max, y_max = float(bowl_bounds[1][0]), float(bowl_bounds[1][1])
            if not (
                x_min + MARGIN <= float(tube_pos[0]) <= x_max - MARGIN
                and y_min + MARGIN <= float(tube_pos[1]) <= y_max - MARGIN
            ):
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        euler = tube.get("euler")
        if euler is not None:
            rx = float(euler[0])
            ry = float(euler[1])
            cx, _sx = math.cos(rx), math.sin(rx)
            cy, _sy = math.cos(ry), math.sin(ry)
            up_z = cy * cx
            up_z = max(-1.0, min(1.0, up_z))
            tilt = math.degrees(math.acos(up_z))
            if tilt > TILT_DEG_MAX:
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        tube_vel = tube.get("vel")
        if tube_vel is not None:
            speed = math.sqrt(float(tube_vel[0]) ** 2 + float(tube_vel[1]) ** 2 + float(tube_vel[2]) ** 2)
            if speed > SPEED_MAX:
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        bowl_vel = bowl.get("vel")
        if bowl_vel is not None:
            speed = math.sqrt(float(bowl_vel[0]) ** 2 + float(bowl_vel[1]) ** 2 + float(bowl_vel[2]) ** 2)
            if speed > SPEED_MAX:
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        return torch.tensor([True], dtype=torch.bool, device=self._device)
