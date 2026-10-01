def _check_success(self) -> torch.Tensor:
        """Check if task is successful: dough forms a flat round shape."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69

        dough_info = objs_info.get("dough ball")

        if dough_info is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if dough_info.get("material") != "particle":
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        pos = dough_info.get("pos")
        if pos is None or len(pos) == 0:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        pos = np.asarray(pos)
        if pos.size == 0 or pos.ndim != 2 or pos.shape[1] != 3:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        x, y, z = pos[:, 0], pos[:, 1], pos[:, 2]

        eps_xy = 0.01
        inside_xy = (
            (x >= TABLE_X_MIN - eps_xy)
            & (x <= TABLE_X_MAX + eps_xy)
            & (y >= TABLE_Y_MIN - eps_xy)
            & (y <= TABLE_Y_MAX + eps_xy)
        )
        above_floor = z >= (self.TABLE_Z - 0.06)
        safe_ratio = np.mean(inside_xy & above_floor)

        if safe_ratio < 0.95:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        pts_xy = pos[:, :2]
        z_base = float(np.percentile(z, 5))
        z_top = z_base + 0.03 + 0.002

        center_xy = pts_xy.mean(axis=0)
        radial = np.linalg.norm(pts_xy - center_xy, axis=1)
        sphere_radius = 0.04
        target_height = 0.03
        R = np.sqrt((4.0 / 3.0) * sphere_radius**3 / target_height)  # volume conservation

        if R <= 0.0:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        # Dough must actually be flat: 95th-percentile height ≤ target + 5mm tolerance.
        # Without this, a sphere that merely settles under gravity (~5cm tall) passes the
        # frac_in check because 78% of its particles happen to sit in the bottom 3cm window.
        z_height = float(np.percentile(z, 95)) - z_base
        if z_height > target_height + 0.005:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        in_cyl = (radial <= R) & (z >= (z_base - 0.002)) & (z <= z_top)
        frac_in = np.mean(in_cyl)
        if frac_in < 0.70:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        # Check the XY outline is roughly circular via convex hull circularity.
        # circularity = 4π·Area / Perimeter² == 1 for a perfect circle, < 1 for elongated shapes.
        from scipy.spatial import ConvexHull

        try:
            hull = ConvexHull(pts_xy)
            circularity = 4.0 * np.pi * hull.volume / (hull.area**2)
        except Exception:
            circularity = 0.0

        return torch.tensor([circularity >= 0.85], dtype=torch.bool, device=self._device)
