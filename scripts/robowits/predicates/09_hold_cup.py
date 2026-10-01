def _check_success(self) -> torch.Tensor:
        """Check if task is successful: cup on target, stable, upright, within bounds."""

        objs_info = self.collect_objs_info()

        TBL_X_MIN, TBL_X_MAX = 0.21, 1.00
        TBL_Y_MIN, TBL_Y_MAX = -0.69, 0.69
        UPRIGHT_TOLERANCE_DEG = 20.0  # Max tilt from vertical

        cup = objs_info.get("cup")
        target = objs_info.get("target area")

        if cup is None or target is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        def is_upright(obj, tolerance_deg: float) -> bool:
            """Check if object's local up vector is close to world up using euler angles."""
            euler = obj.get("euler")
            if euler is None:
                return False
            # euler values are in radians; convert to degrees
            roll_deg = abs(math.degrees(float(euler[0])))
            pitch_deg = abs(math.degrees(float(euler[1])))
            # Normalize to [-180, 180] range
            if roll_deg > 180:
                roll_deg = 360 - roll_deg
            if pitch_deg > 180:
                pitch_deg = 360 - pitch_deg
            return roll_deg <= tolerance_deg and pitch_deg <= tolerance_deg

        def get_poly(obj):
            ch = obj.get("convex_hull_2d", None)
            try:
                if ch is not None and len(ch) >= 3:
                    return [(float(p[0]), float(p[1])) for p in ch]
            except Exception:
                pass
            b = obj.get("bounds", None)
            if b is None:
                return None
            try:
                (xmin, ymin, _), (xmax, ymax, _) = b
                return [
                    (float(xmin), float(ymin)),
                    (float(xmax), float(ymin)),
                    (float(xmax), float(ymax)),
                    (float(xmin), float(ymax)),
                ]
            except Exception:
                return None

        def poly_area(poly):
            if poly is None or len(poly) < 3:
                return 0.0
            area = 0.0
            for i in range(len(poly)):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % len(poly)]
                area += x1 * y2 - x2 * y1
            return abs(area) * 0.5

        def signed_area(poly):
            s = 0.0
            for i in range(len(poly)):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % len(poly)]
                s += x1 * y2 - x2 * y1
            return 0.5 * s

        def line_intersection(p1, p2, p3, p4):
            x1, y1 = p1
            x2, y2 = p2
            x3, y3 = p3
            x4, y4 = p4
            denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(denom) < 1e-12:
                return ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)
            det1 = x1 * y2 - y1 * x2
            det2 = x3 * y4 - y3 * x4
            px = (det1 * (x3 - x4) - (x1 - x2) * det2) / denom
            py = (det1 * (y3 - y4) - (y1 - y2) * det2) / denom
            return (px, py)

        def clip_polygon(subject, clip):
            if subject is None or clip is None or len(subject) < 3 or len(clip) < 3:
                return []
            ori_sign = 1.0 if signed_area(clip) >= 0.0 else -1.0

            def inside(pt, a, b):
                cross = (b[0] - a[0]) * (pt[1] - a[1]) - (b[1] - a[1]) * (pt[0] - a[0])
                return ori_sign * cross >= -1e-9

            output = [(float(x), float(y)) for x, y in subject]
            cl = [(float(x), float(y)) for x, y in clip]
            for i in range(len(cl)):
                a = cl[i]
                b = cl[(i + 1) % len(cl)]
                input_list = output
                output = []
                if not input_list:
                    break
                s = input_list[-1]
                for e in input_list:
                    if inside(e, a, b):
                        if not inside(s, a, b):
                            output.append(line_intersection(s, e, a, b))
                        output.append(e)
                    elif inside(s, a, b):
                        output.append(line_intersection(s, e, a, b))
                    s = e
            return output

        cup_poly = get_poly(cup)
        target_poly = get_poly(target)

        if cup_poly is None or target_poly is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        inter_poly = clip_polygon(cup_poly, target_poly)
        cup_area = poly_area(cup_poly)
        inter_area = poly_area(inter_poly)

        if cup_area <= 0.0:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        overlap_ok = (inter_area / cup_area) >= 0.5

        vel = cup.get("vel")
        if vel is None:
            return torch.tensor([False], dtype=torch.bool, device=self._device)

        vnorm = math.sqrt(float(vel[0]) ** 2 + float(vel[1]) ** 2 + float(vel[2]) ** 2)
        stable_ok = vnorm <= 0.005

        upright_ok = is_upright(cup, UPRIGHT_TOLERANCE_DEG)

        cup_ok = True
        for pt in cup_poly:
            x, y = float(pt[0]), float(pt[1])
            if not (TBL_X_MIN - 1e-6 <= x <= TBL_X_MAX + 1e-6):
                cup_ok = False
                break
            if not (TBL_Y_MIN - 1e-6 <= y <= TBL_Y_MAX + 1e-6):
                cup_ok = False
                break

        not_held = not check_being_held(cup, self._robot)

        return torch.tensor(
            [overlap_ok and stable_ok and upright_ok and cup_ok and not_held], dtype=torch.bool, device=self._device
        )
