def _check_success(self) -> torch.Tensor:
        """Check if task is successful."""

        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69
        TABLE_Z = 0.76

        CUBE = "cube"
        TARGET = "target area"
        CONTAINERS = ["deep narrow container", "wide open container"]

        EPS_XY = 1e-2
        Z_TOL_BELOW = 0.01
        Z_TOL_ABOVE = 0.03
        AREA_EPS = 1e-8

        def get_hull_xy(obj_name):
            obj = objs_info.get(obj_name)
            if obj is None:
                return None
            hull = obj.get("convex_hull_2d")
            if hull is not None:
                try:
                    hull = np.asarray(hull, dtype=float)
                    if hull.ndim == 2 and hull.shape[1] == 2 and len(hull) >= 3:
                        return hull
                except Exception:
                    pass
            b = obj.get("bounds")
            if b is None:
                return None
            b = np.asarray(b, dtype=float)
            if b.shape != (2, 3):
                return None
            (x_min, y_min, _), (x_max, y_max, _) = b
            return np.array(
                [
                    [x_min, y_min],
                    [x_max, y_min],
                    [x_max, y_max],
                    [x_min, y_max],
                ],
                dtype=float,
            )

        def get_bounds(obj_name):
            obj = objs_info.get(obj_name)
            if obj is None:
                return None
            b = obj.get("bounds")
            if b is None:
                return None
            b = np.asarray(b, dtype=float)
            if b.shape != (2, 3):
                return None
            return b

        def polygon_signed_area(poly):
            if poly is None or len(poly) < 3:
                return 0.0
            x = poly[:, 0]
            y = poly[:, 1]
            return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

        def polygon_area(poly):
            return abs(polygon_signed_area(poly))

        def ensure_ccw(poly):
            if poly is None or len(poly) < 3:
                return poly
            if polygon_signed_area(poly) < 0:
                return np.flipud(poly.copy())
            return poly

        def sutherland_hodgman(subject_polygon, clip_polygon):
            if subject_polygon is None or clip_polygon is None:
                return np.zeros((0, 2), dtype=float)
            output_list = subject_polygon.tolist()
            if len(output_list) < 3 or len(clip_polygon) < 3:
                return np.zeros((0, 2), dtype=float)

            def is_inside(p, a, b):
                return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0.0

            def compute_intersection(p1, p2, p3, p4):
                x1, y1 = p1
                x2, y2 = p2
                x3, y3 = p3
                x4, y4 = p4
                denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
                if abs(denom) < 1e-12:
                    return [(p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0]
                px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
                py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
                return [px, py]

            clip_pts = clip_polygon.tolist()
            for i in range(len(clip_pts)):
                input_list = output_list
                output_list = []
                if not input_list:
                    break
                A = clip_pts[i]
                B = clip_pts[(i + 1) % len(clip_pts)]
                S = input_list[-1]
                for E in input_list:
                    if is_inside(E, A, B):
                        if not is_inside(S, A, B):
                            output_list.append(compute_intersection(S, E, A, B))
                        output_list.append(E)
                    elif is_inside(S, A, B):
                        output_list.append(compute_intersection(S, E, A, B))
                    S = E
            if not output_list or len(output_list) < 3:
                return np.zeros((0, 2), dtype=float)
            return np.array(output_list, dtype=float)

        def overlap_area(poly1, poly2):
            if poly1 is None or poly2 is None:
                return 0.0
            p1 = ensure_ccw(np.asarray(poly1, dtype=float))
            p2 = ensure_ccw(np.asarray(poly2, dtype=float))
            inter = sutherland_hodgman(p1, p2)
            if inter.size == 0 or len(inter) < 3:
                return 0.0
            return polygon_area(inter)

        def hull_inside_table(hull):
            if hull is None or len(hull) == 0:
                return False
            xs = hull[:, 0]
            ys = hull[:, 1]
            within_x = (xs >= (TABLE_X_MIN - EPS_XY)) & (xs <= (TABLE_X_MAX + EPS_XY))
            within_y = (ys >= (TABLE_Y_MIN - EPS_XY)) & (ys <= (TABLE_Y_MAX + EPS_XY))
            return bool(np.all(within_x & within_y))

        cube_hull = get_hull_xy(CUBE)
        target_hull = get_hull_xy(TARGET)
        cube_bounds = get_bounds(CUBE)

        # Get container hull (try both container types)
        container_hull = None
        for container_name in CONTAINERS:
            container_hull = get_hull_xy(container_name)
            if container_hull is not None:
                break

        if cube_hull is None or target_hull is None or cube_bounds is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        z_min = float(cube_bounds[0, 2])
        if z_min < (TABLE_Z - Z_TOL_BELOW) or z_min > (TABLE_Z + Z_TOL_ABOVE):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        if not hull_inside_table(cube_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        if not hull_inside_table(target_hull):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        cube_area = polygon_area(ensure_ccw(cube_hull))
        if cube_area <= AREA_EPS:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        # Check cube is outside container (overlap < 50%)
        if container_hull is not None:
            container_overlap = overlap_area(cube_hull, container_hull)
            container_overlap_ratio = container_overlap / cube_area
            if container_overlap_ratio >= 0.5:
                return torch.tensor([False], dtype=torch.bool, device=self._device)

        # Check cube overlaps target area by at least 50%
        inter_area = overlap_area(cube_hull, target_hull)
        overlap_ratio = inter_area / cube_area

        return torch.tensor([overlap_ratio >= 0.5], dtype=torch.bool, device=self._device)
