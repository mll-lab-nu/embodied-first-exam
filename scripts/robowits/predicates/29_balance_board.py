def _check_success(self) -> torch.Tensor:
        """Check if task is successful: board balanced on wall."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69

        board = objs_info.get("board")
        wall = objs_info.get("small wall")

        if board is None or wall is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if board.get("material") != "rigid" or wall.get("material") != "rigid":
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if board.get("bounds") is None or wall.get("bounds") is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def centroid_xy(hull, bounds):
            if hull is not None and isinstance(hull, np.ndarray) and hull.size >= 2:
                return np.mean(hull, axis=0)
            bmin, bmax = bounds
            return np.array([(bmin[0] + bmax[0]) / 2.0, (bmin[1] + bmax[1]) / 2.0])

        def horiz_extents(bounds):
            bmin, bmax = bounds
            return float(bmax[0] - bmin[0]), float(bmax[1] - bmin[1])

        def within_table(hull):
            if hull is None or not isinstance(hull, np.ndarray) or hull.size < 2:
                return False
            xs, ys = hull[:, 0], hull[:, 1]
            return (
                np.all(xs >= TABLE_X_MIN)
                and np.all(xs <= TABLE_X_MAX)
                and np.all(ys >= TABLE_Y_MIN)
                and np.all(ys <= TABLE_Y_MAX)
            )

        def angle_close_to_horizontal(euler, thr_deg=12.0):
            if euler is None:
                return True
            roll = float(euler[0]) * 180.0 / np.pi
            pitch = float(euler[1]) * 180.0 / np.pi

            def dist_to_0_or_180(a):
                a = a % 360.0
                return min(abs(a), abs(180.0 - a))

            return (dist_to_0_or_180(roll) <= thr_deg) and (dist_to_0_or_180(pitch) <= thr_deg)

        b_bounds = board["bounds"]
        w_bounds = wall["bounds"]
        bmin, bmax = b_bounds
        wmin, wmax = w_bounds

        board_hull = board.get("convex_hull_2d")
        wall_hull = wall.get("convex_hull_2d")

        if not (within_table(board_hull) and within_table(wall_hull)):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        wall_top_z = float(wmax[2])
        board_bottom_z = float(bmin[2])
        tol_z_contact = 0.02
        if abs(board_bottom_z - wall_top_z) > tol_z_contact:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if (board_bottom_z - self.TABLE_Z) <= 0.03:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        board_xy = centroid_xy(board_hull, b_bounds)
        wall_xy = centroid_xy(wall_hull, w_bounds)
        center_dist = float(np.linalg.norm(board_xy - wall_xy))

        wx_ext, wy_ext = horiz_extents(w_bounds)
        wall_foot_min = max(1e-6, min(wx_ext, wy_ext))
        center_tol = max(0.03, 0.5 * wall_foot_min)
        center_tol = min(center_tol, 0.05)

        if center_dist > center_tol:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        euler = board.get("euler")
        if not angle_close_to_horizontal(euler, thr_deg=12.0):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        vel = board.get("vel")
        if vel is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        vel = np.array(vel).astype(float)
        if np.linalg.norm(vel) > 0.05:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        if abs(vel[2]) > 0.04:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if check_being_held(board, self._robot):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        return torch.tensor([True], dtype=torch.bool, device=self._device)
