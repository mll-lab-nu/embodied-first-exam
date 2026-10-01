def _check_success(self) -> torch.Tensor:
        """Check if task is successful: water in perforated container."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69

        container = objs_info.get("perforated container")
        water = objs_info.get("water")

        if container is None or water is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        container_hull = container.get("convex_hull_2d")
        container_bounds = container.get("bounds")

        if container_hull is not None:
            container_poly = [(float(p[0]), float(p[1])) for p in container_hull]
        elif container_bounds is not None:
            xmin, ymin = container_bounds[0][0], container_bounds[0][1]
            xmax, ymax = container_bounds[1][0], container_bounds[1][1]
            container_poly = [
                (float(xmin), float(ymin)),
                (float(xmax), float(ymin)),
                (float(xmax), float(ymax)),
                (float(xmin), float(ymax)),
            ]
        else:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def polygon_within_table(poly):
            for x, y in poly:
                if x < TABLE_X_MIN - 1e-3 or x > TABLE_X_MAX + 1e-3:
                    return False
                if y < TABLE_Y_MIN - 1e-3 or y > TABLE_Y_MAX + 1e-3:
                    return False
            return True

        if not polygon_within_table(container_poly):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        container_bounds_for_z = container.get("bounds")
        if container_bounds_for_z is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        z_min = float(container_bounds_for_z[0][2])
        z_max = float(container_bounds_for_z[1][2])

        if water.get("material") != "particle":
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        water_pos = water.get("pos")
        if water_pos is None or np.size(water_pos) == 0:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        water_pos = np.asarray(water_pos)

        def point_in_polygon(px, py, polygon):
            inside = False
            n = len(polygon)
            if n < 3:
                return False
            for i in range(n):
                x1, y1 = polygon[i]
                x2, y2 = polygon[(i + 1) % n]
                if (y1 > py) != (y2 > py):
                    denom = y2 - y1
                    if abs(denom) < 1e-12:
                        continue
                    x_intersect = x1 + (py - y1) * (x2 - x1) / denom
                    if x_intersect >= px:
                        inside = not inside
            return inside

        total = len(water_pos)
        if total <= 0:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        inside_count = 0
        z_lo = z_min + 0.005
        z_hi = z_max + 0.02

        for i in range(total):
            px = float(water_pos[i][0])
            py = float(water_pos[i][1])
            pz = float(water_pos[i][2])
            if pz < z_lo or pz > z_hi:
                continue
            if point_in_polygon(px, py, container_poly):
                inside_count += 1

        frac_inside = inside_count / float(total)
        return torch.tensor([frac_inside > 0.10], dtype=torch.bool, device=self._device)
