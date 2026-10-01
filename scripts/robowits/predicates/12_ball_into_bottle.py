def _check_success(self) -> torch.Tensor:
        """Check if task is successful: ball inside bottle."""
        objs_info = self.collect_objs_info()

        if not isinstance(objs_info, dict):
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        ball = objs_info.get("small ball")
        bottle = objs_info.get("red bottle")
        if ball is None or bottle is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        table_z = 0.76
        safe_margin = 0.002
        top_margin = 0.11

        def f(v):
            try:
                return float(v)
            except Exception:
                return None

        def point_in_polygon(px, py, poly):
            n = len(poly)
            if n < 3:
                return False
            inside = False
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                if (y1 > py) != (y2 > py):
                    x_int = (x2 - x1) * (py - y1) / (y2 - y1 + 1e-12) + x1
                    if px < x_int:
                        inside = not inside
            return inside

        def not_fallen(obj):
            b = obj.get("bounds")
            if b is not None:
                zmin = f(b[0][2])
            else:
                pos = obj.get("pos")
                zmin = f(pos[2]) if pos is not None else None
            if zmin is None:
                return False
            return zmin >= (table_z - 0.05)

        ball_pos = ball.get("pos")
        if ball_pos is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        bx, by, bz = f(ball_pos[0]), f(ball_pos[1]), f(ball_pos[2])
        if bx is None or by is None or bz is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        ball_bounds = ball.get("bounds")
        ball_radius = None
        if ball_bounds is not None:
            try:
                dx = f(ball_bounds[1][0]) - f(ball_bounds[0][0])
                dy = f(ball_bounds[1][1]) - f(ball_bounds[0][1])
                dz = f(ball_bounds[1][2]) - f(ball_bounds[0][2])
                ball_radius = 0.5 * min(abs(dx), abs(dy), abs(dz))
            except Exception:
                ball_radius = None
        if ball_radius is None or ball_radius <= 0:
            ball_radius = 0.01

        ball_bottom_z = bz - ball_radius
        if ball_bottom_z <= (table_z + safe_margin):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        bottle_poly = bottle.get("convex_hull_2d")
        if bottle_poly is not None:
            poly = [(f(p[0]), f(p[1])) for p in bottle_poly]
            poly = [(x, y) for (x, y) in poly if x is not None and y is not None]
        else:
            bnd = bottle.get("bounds")
            if bnd is None:
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            x0, y0 = f(bnd[0][0]), f(bnd[0][1])
            x1, y1 = f(bnd[1][0]), f(bnd[1][1])
            if None in (x0, y0, x1, y1):
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            poly = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

        bottle_bounds = bottle.get("bounds")
        if bottle_bounds is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        bottle_zmin = f(bottle_bounds[0][2])
        bottle_zmax = f(bottle_bounds[1][2])
        if bottle_zmin is None or bottle_zmax is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        inside_xy = point_in_polygon(bx, by, poly)

        ball_top_z = bz + ball_radius
        fully_below_mouth = ball_top_z < (bottle_zmax - top_margin)
        above_bottle_base = ball_bottom_z > (bottle_zmin + safe_margin)

        if not (not_fallen(ball) and not_fallen(bottle)):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        return torch.tensor(
            [inside_xy and fully_below_mouth and above_bottle_base], dtype=torch.bool, device=self._device
        )
