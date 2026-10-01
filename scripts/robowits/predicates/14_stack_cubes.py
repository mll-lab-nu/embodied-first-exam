def _check_success(self) -> torch.Tensor:
        """Check if task is successful."""
        objs_info = self.collect_objs_info()

        b1 = objs_info.get("base cube 1")
        b2 = objs_info.get("base cube 2")
        apex = objs_info.get("apex cube")
        target = objs_info.get("apex target")

        if any(x is None for x in [b1, b2, apex, target]):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def is_on_table_surface(bounds, table_z, tolerance=0.015):
            z_min = float(bounds[0][2])
            return abs(z_min - table_z) <= tolerance

        def objects_touching(b1, b2, tolerance=0.01):
            return all(not (b1[1][i] + tolerance < b2[0][i] or b2[1][i] + tolerance < b1[0][i]) for i in range(3))

        if not is_on_table_surface(b1["bounds"], self.TABLE_Z):
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        if not is_on_table_surface(b2["bounds"], self.TABLE_Z):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if not objects_touching(b1["bounds"], b2["bounds"], tolerance=0.01):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        apex_bottom = float(apex["bounds"][0, 2])
        b1_top = float(b1["bounds"][1, 2])
        if apex_bottom < b1_top - 0.01:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        apex_pos = apex["pos"][:2]
        target_pos = target["pos"][:2]
        dist = np.sqrt((apex_pos[0] - target_pos[0]) ** 2 + (apex_pos[1] - target_pos[1]) ** 2)
        if dist > 0.025:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if check_being_held(apex, self._robot):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        return torch.tensor([True], dtype=torch.bool, device=self._device)
