def _check_success(self) -> torch.Tensor:
        """Check if task is successful."""
        import numpy as np

        objs_info = self.collect_objs_info()

        TABLE_BOUNDS = {
            "x_min": 0.21,
            "x_max": 1.00,
            "y_min": -0.69,
            "y_max": 0.69,
            "z_surf": 0.76,
        }

        cube_names = [
            "first target cube",
            "second target cube",
            "third target cube",
        ]

        for n in cube_names:
            if n not in objs_info:
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        def get_xy(name):
            p = objs_info[name]["pos"]
            return np.array([p[0], p[1]], dtype=float)

        def pairwise_dists(pts):
            d01 = np.linalg.norm(pts[0] - pts[1])
            d12 = np.linalg.norm(pts[1] - pts[2])
            d02 = np.linalg.norm(pts[0] - pts[2])
            return [(d01, (0, 1)), (d12, (1, 2)), (d02, (0, 2))]

        def point_line_distance(p, a, b):
            v = b - a
            w = p - a
            v_norm = np.linalg.norm(v)
            if v_norm < 1e-9:
                return np.linalg.norm(p - a)
            cross_z = v[0] * w[1] - v[1] * w[0]
            return abs(cross_z) / (v_norm + 1e-12)

        def on_table_surface(name, z_tol=0.025):
            info = objs_info[name]
            b = info.get("bounds", None)
            if b is None:
                return True
            zmin = float(b[0][2])
            return abs(zmin - TABLE_BOUNDS["z_surf"]) <= z_tol

        margin = 0.03
        for name, info in objs_info.items():
            lname = name.lower()
            if "table" in lname or "robot" in lname:
                continue
            pos = info.get("pos", None)
            if pos is None:
                continue
            x, y = float(pos[0]), float(pos[1])
            if (
                x < TABLE_BOUNDS["x_min"] - margin
                or x > TABLE_BOUNDS["x_max"] + margin
                or y < TABLE_BOUNDS["y_min"] - margin
                or y > TABLE_BOUNDS["y_max"] + margin
            ):
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        for n in cube_names:
            if not on_table_surface(n, z_tol=0.025):
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        pts = [get_xy(n) for n in cube_names]

        dists = pairwise_dists(pts)
        max_pair = max(dists, key=lambda x: x[0])
        max_dist, (i, j) = max_pair
        if max_dist < 0.03:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        k = 3 - i - j
        line_tol = 0.010
        perp_dist = point_line_distance(pts[k], pts[i], pts[j])
        if perp_dist > line_tol:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        return torch.tensor([True], dtype=torch.bool, device=self._device)
