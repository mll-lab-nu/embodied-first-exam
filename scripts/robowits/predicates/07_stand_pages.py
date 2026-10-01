def _check_success(self) -> torch.Tensor:
        """Check if task is successful: both pages standing upright."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69

        def angle_close_to_right_angle(angle_deg: float) -> bool:
            a = angle_deg
            if a < 0:
                a += 360.0
            if a > 360:
                a -= 360.0
            d = min(abs(a), abs(180 - a), abs(360 - a))
            return d <= self.ANGLE_TOL_DEG

        def is_upright(euler) -> bool:
            if euler is None:
                return False
            ex = float(euler[0]) * 180.0 / np.pi
            ey = float(euler[1]) * 180.0 / np.pi
            return angle_close_to_right_angle(ex) and angle_close_to_right_angle(ey)

        def hull_within_table(hull2d) -> bool:
            if hull2d is None:
                return False
            for pt in hull2d:
                x, y = float(pt[0]), float(pt[1])
                if not (TABLE_X_MIN <= x <= TABLE_X_MAX and TABLE_Y_MIN <= y <= TABLE_Y_MAX):
                    return False
            return True

        def is_on_table(bounds) -> bool:
            if bounds is None:
                return False
            z_min = float(bounds[0][2])
            return abs(z_min - self.TABLE_Z) <= self.Z_CONTACT_TOL

        required_pages = ["page A with eyelets", "page B with eyelets"]

        for name in required_pages:
            info = objs_info.get(name)
            if info is None:
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            euler = info.get("euler")
            if not is_upright(euler):
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            hull = info.get("convex_hull_2d")
            if not hull_within_table(hull):
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            bounds = info.get("bounds")
            if not is_on_table(bounds):
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            if _utils.check_being_held(info, self._robot):
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        return torch.tensor([True], dtype=torch.bool, device=self._device)
