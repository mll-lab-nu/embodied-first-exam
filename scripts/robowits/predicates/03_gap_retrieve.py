def _check_success(self) -> torch.Tensor:
        """Check if task is successful: lemon on target with 80% overlap."""
        objs_info = self.collect_objs_info()

        TABLE_X_MIN, TABLE_X_MAX = 0.21, 1.00
        TABLE_Y_MIN, TABLE_Y_MAX = -0.69, 0.69
        TABLE_Z = 0.76
        Z_TOL = 0.02

        key_name = "lemon"
        target_name = "target area"

        if key_name not in objs_info or target_name not in objs_info:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        key = objs_info[key_name]
        target = objs_info[target_name]

        def get_hull2d(obj):
            hull = obj.get("convex_hull_2d", None)
            if hull is not None and len(hull) >= 3:
                pts = [(float(p[0]), float(p[1])) for p in hull]
                return pts
            b = obj.get("bounds", None)
            if b is None:
                return None
            (xmin, ymin, _), (xmax, ymax, _) = b
            return [
                (float(xmin), float(ymin)),
                (float(xmax), float(ymin)),
                (float(xmax), float(ymax)),
                (float(xmin), float(ymax)),
            ]

        def polygon_area(poly):
            if not poly or len(poly) < 3:
                return 0.0
            area = 0.0
            for i in range(len(poly)):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % len(poly)]
                area += x1 * y2 - x2 * y1
            return abs(area) * 0.5

        def ensure_ccw(poly):
            signed = 0.0
            for i in range(len(poly)):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % len(poly)]
                signed += x1 * y2 - x2 * y1
            if signed < 0:
                return list(reversed(poly))
            return poly

        def point_in_table_xy(p):
            x, y = p
            return (TABLE_X_MIN - 1e-4) <= x <= (TABLE_X_MAX + 1e-4) and (TABLE_Y_MIN - 1e-4) <= y <= (
                TABLE_Y_MAX + 1e-4
            )

        def hull_inside_table(poly):
            if not poly:
                return False
            return all(point_in_table_xy(p) for p in poly)

        def cross(ax, ay, bx, by):
            return ax * by - ay * bx

        def line_intersection(p, r, q, svec):
            rxs = cross(r[0], r[1], svec[0], svec[1])
            if abs(rxs) < 1e-12:
                return None
            qp = (q[0] - p[0], q[1] - p[1])
            t = cross(qp[0], qp[1], svec[0], svec[1]) / rxs
            return (p[0] + t * r[0], p[1] + t * r[1])

        def is_inside(p, a, b):
            return cross(b[0] - a[0], b[1] - a[1], p[0] - a[0], p[1] - a[1]) >= -1e-9

        def sutherland_hodgman(subject, clip):
            if not subject or not clip:
                return []
            output = subject[:]
            for i in range(len(clip)):
                cp1 = clip[i]
                cp2 = clip[(i + 1) % len(clip)]
                input_list = output
                output = []
                if not input_list:
                    break
                s = input_list[-1]
                for e in input_list:
                    if is_inside(e, cp1, cp2):
                        if not is_inside(s, cp1, cp2):
                            inter = line_intersection(
                                s, (e[0] - s[0], e[1] - s[1]), cp1, (cp2[0] - cp1[0], cp2[1] - cp1[1])
                            )
                            if inter is not None:
                                output.append(inter)
                        output.append(e)
                    elif is_inside(s, cp1, cp2):
                        inter = line_intersection(
                            s, (e[0] - s[0], e[1] - s[1]), cp1, (cp2[0] - cp1[0], cp2[1] - cp1[1])
                        )
                        if inter is not None:
                            output.append(inter)
                    s = e
            return output

        key_hull = get_hull2d(key)
        target_hull = get_hull2d(target)
        if key_hull is None or target_hull is None or len(key_hull) < 3 or len(target_hull) < 3:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        key_hull = ensure_ccw(key_hull)
        target_hull = ensure_ccw(target_hull)

        key_bounds = key.get("bounds", None)
        if key_bounds is None:
            kpos = key.get("pos", None)
            if kpos is None:
                return torch.tensor([False], dtype=torch.bool, device=self._device)
            on_table = (kpos[2] - TABLE_Z) <= 0.03
        else:
            z_min = float(key_bounds[0][2])
            on_table = abs(z_min - TABLE_Z) <= Z_TOL

        key_on_table_xy = hull_inside_table(key_hull)
        target_on_table_xy = hull_inside_table(target_hull)
        if not (key_on_table_xy and target_on_table_xy):
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        key_area = polygon_area(key_hull)
        if key_area <= 1e-8:
            return torch.tensor([False], dtype=torch.bool, device=self._device)
        inter_poly = sutherland_hodgman(key_hull, target_hull)
        overlap_area = polygon_area(inter_poly) if len(inter_poly) >= 3 else 0.0
        overlap_fraction = overlap_area / key_area

        lemon_not_held = not check_being_held(key, self._robot)

        return torch.tensor(
            [on_table and overlap_fraction >= 0.8 and lemon_not_held],
            dtype=torch.bool,
            device=self._device,
        )
