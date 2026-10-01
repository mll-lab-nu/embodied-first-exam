def _check_success(self) -> torch.Tensor:
        """Check if task is successful: tall object on target, upright, stable."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69
        VEL_THRESHOLD = 0.05
        OVERLAP_RATIO_REQ = 0.80
        TABLE_MARGIN = 1e-3

        def get_hull(obj):
            hull = obj.get("convex_hull_2d", None)
            if hull is not None and isinstance(hull, np.ndarray) and hull.shape[0] >= 3:
                return hull.copy()
            b = obj.get("bounds", None)
            if b is None:
                return None
            (xmin, ymin, _), (xmax, ymax, _) = b
            return np.array([[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]], dtype=float)

        def poly_area(poly):
            if poly is None or len(poly) < 3:
                return 0.0
            x = poly[:, 0]
            y = poly[:, 1]
            return 0.5 * float(np.abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))

        def ensure_ccw(poly):
            if poly is None or len(poly) < 3:
                return poly
            area_signed = 0.5 * float(
                np.dot(poly[:, 0], np.roll(poly[:, 1], -1)) - np.dot(poly[:, 1], np.roll(poly[:, 0], -1))
            )
            if area_signed < 0:
                return poly[::-1].copy()
            return poly

        def line_intersection(p1, p2, p3, p4):
            x1, y1 = p1
            x2, y2 = p2
            x3, y3 = p3
            x4, y4 = p4
            denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(denom) < 1e-12:
                return p2
            px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
            py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
            return np.array([px, py], dtype=float)

        def is_left(a, b, p):
            return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])

        def convex_polygon_intersection(subject, clip):
            if subject is None or clip is None or len(subject) < 3 or len(clip) < 3:
                return np.zeros((0, 2), dtype=float)
            output = subject.copy()
            clip = ensure_ccw(clip)
            for i in range(len(clip)):
                c1 = clip[i]
                c2 = clip[(i + 1) % len(clip)]
                input_list = output
                output = []
                if len(input_list) == 0:
                    return np.zeros((0, 2), dtype=float)
                S = input_list[-1]
                for E in input_list:
                    inside_E = is_left(c1, c2, E) >= 0
                    inside_S = is_left(c1, c2, S) >= 0
                    if inside_E:
                        if not inside_S:
                            inter_pt = line_intersection(S, E, c1, c2)
                            output.append(inter_pt)
                        output.append(E)
                    elif inside_S:
                        inter_pt = line_intersection(S, E, c1, c2)
                        output.append(inter_pt)
                    S = E
                if len(output) == 0:
                    return np.zeros((0, 2), dtype=float)
                output = np.array(output, dtype=float)
            return output

        def hull_within_table(hull):
            if hull is None or len(hull) == 0:
                return False
            xs = hull[:, 0]
            ys = hull[:, 1]
            return (
                np.all(xs >= TABLE_X_MIN - TABLE_MARGIN)
                and np.all(xs <= TABLE_X_MAX + TABLE_MARGIN)
                and np.all(ys >= TABLE_Y_MIN - TABLE_MARGIN)
                and np.all(ys <= TABLE_Y_MAX + TABLE_MARGIN)
            )

        tall_name = "tall object with curved bottom"
        patch_name = "target patch"
        if tall_name not in objs_info or patch_name not in objs_info:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        tall = objs_info[tall_name]
        patch = objs_info[patch_name]

        tall_hull = get_hull(tall)
        patch_hull = get_hull(patch)
        if tall_hull is None or patch_hull is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if not hull_within_table(tall_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        if not hull_within_table(patch_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        b = tall.get("bounds", None)
        is_upright = False
        if b is not None:
            (xmin, ymin, zmin), (xmax, ymax, zmax) = b
            z_ext = zmax - zmin
            xy_max = max(xmax - xmin, ymax - ymin)
            is_upright = z_ext > xy_max

        v = tall.get("vel", None)
        is_still = True
        if v is not None and isinstance(v, np.ndarray) and v.shape == (3,):
            is_still = float(np.linalg.norm(v)) <= VEL_THRESHOLD

        if not (is_upright and is_still):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        tall_hull = ensure_ccw(tall_hull)
        patch_hull = ensure_ccw(patch_hull)
        inter_poly = convex_polygon_intersection(tall_hull, patch_hull)
        inter_area = poly_area(inter_poly)
        tall_area = poly_area(tall_hull)
        if tall_area <= 1e-9:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        overlap_ratio = inter_area / tall_area

        if overlap_ratio + 1e-6 < OVERLAP_RATIO_REQ:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if check_being_held(tall, self._robot):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        return torch.tensor([True], dtype=torch.bool, device=self._device)
