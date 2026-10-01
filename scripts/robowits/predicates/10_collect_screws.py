def _check_success(self, objs_info: dict | None = None) -> torch.Tensor:
        """Check if task is successful: screw in container."""
        if objs_info is None:
            objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69

        container = objs_info.get("container")

        if container is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        container_bounds = container.get("bounds")
        if container_bounds is None:
            ch = container.get("convex_hull_2d")
            if ch is None:
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            ch = np.array(ch).astype(float)
            x_min, y_min = np.min(ch[:, 0]), np.min(ch[:, 1])
            x_max, y_max = np.max(ch[:, 0]), np.max(ch[:, 1])
            z_min = self.TABLE_Z - 0.02
            z_max = self.TABLE_Z + 1.0
            cmin = np.array([x_min, y_min, z_min])
            cmax = np.array([x_max, y_max, z_max])
        else:
            cb = np.array(container_bounds).astype(float)
            cmin, cmax = cb[0], cb[1]

        eps = 1e-3

        screw = objs_info.get("screw")

        if screw is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        screw_pos = screw.get("pos")
        if screw_pos is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        screw_pos = np.asarray(screw_pos, dtype=float)

        if not (
            (TABLE_X_MIN - 0.02) <= screw_pos[0] <= (TABLE_X_MAX + 0.02)
            and (TABLE_Y_MIN - 0.02) <= screw_pos[1] <= (TABLE_Y_MAX + 0.02)
            and screw_pos[2] >= (self.TABLE_Z - 0.05)
        ):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        inside = (
            (cmin[0] - eps) <= screw_pos[0] <= (cmax[0] + eps)
            and (cmin[1] - eps) <= screw_pos[1] <= (cmax[1] + eps)
            and (cmin[2] - 0.02) <= screw_pos[2] <= (cmax[2] + 0.02)
        )
        return torch.tensor([bool(inside)], dtype=torch.bool, device=self._device)
