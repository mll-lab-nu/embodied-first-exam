def _check_success(self) -> torch.Tensor:
        """Check if task is successful: any cube past goal line."""
        objs_info = self.collect_objs_info()

        cube_names = ["cube 1", "cube 2", "cube 3"]

        any_past_goal = False
        for cube_name in cube_names:
            cube = objs_info.get(cube_name)
            if cube is None:
                continue
            if cube.get("material") != "rigid":
                continue
            pos = cube.get("pos")
            if pos is not None:
                pos = np.asarray(pos)
                if pos.shape == (3,) and pos[0] > 0.9:
                    any_past_goal = True
                    break

        return torch.tensor([any_past_goal], dtype=torch.bool, device=self._device)
